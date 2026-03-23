from fastapi import FastAPI, Depends, HTTPException, status, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session, joinedload
import joblib
import pandas as pd
import uvicorn
import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

import models
import schemas
from database import engine, get_db
from auth import (
    hash_password, verify_password,
    create_access_token, get_current_user,
)

# ── App setup ─────────────────────────────────────────────────
models.Base.metadata.create_all(bind=engine)
app = FastAPI(title="Employee Attrition API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# ── Model load ────────────────────────────────────────────────
MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "model.pkl")
model = None

@app.on_event("startup")
def load_model():
    global model
    if os.path.exists(MODEL_PATH):
        model = joblib.load(MODEL_PATH)
        print("Model loaded.")
    else:
        print(f"Warning: model not found at {MODEL_PATH}")

# ══════════════════════════════════════════════════════════════
# PUBLIC ROUTES — no auth needed
# ══════════════════════════════════════════════════════════════

@app.get("/")
def root():
    return {"message": "Employee Attrition API"}


@app.post("/auth/register", response_model=schemas.AuthResponse, status_code=201)
def register(payload: schemas.RegisterRequest, db: Session = Depends(get_db)):
    # Check slug is unique
    if db.query(models.Organization).filter(models.Organization.slug == payload.org_slug).first():
        raise HTTPException(status_code=400, detail="Organisation slug already taken.")
    # Check email is unique
    if db.query(models.User).filter(models.User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered.")

    org  = models.Organization(name=payload.org_name, slug=payload.org_slug)
    db.add(org); db.flush()  # flush to get org.id

    user = models.User(
        organization_id=org.id,
        name=payload.name,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role="admin",
    )
    db.add(user); db.commit(); db.refresh(user)

    token = create_access_token({"sub": user.email, "org_id": org.id, "role": user.role})
    return {"access_token": token, "token_type": "bearer",
            "user": {"id": user.id, "name": user.name, "email": user.email,
                     "role": user.role, "org_name": org.name, "org_slug": org.slug}}


@app.post("/auth/login", response_model=schemas.AuthResponse)
def login(form: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form.email).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    org = db.query(models.Organization).filter(models.Organization.id == user.organization_id).first()
    token = create_access_token({"sub": user.email, "org_id": user.organization_id, "role": user.role})
    return {"access_token": token, "token_type": "bearer",
            "user": {"id": user.id, "name": user.name, "email": user.email,
                     "role": user.role, "org_name": org.name if org else "", "org_slug": org.slug if org else ""}}


@app.get("/auth/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = db.query(models.Organization).filter(models.Organization.id == current_user.organization_id).first()
    return {"id": current_user.id, "name": current_user.name, "email": current_user.email,
            "role": current_user.role, "org_name": org.name if org else "", "org_slug": org.slug if org else ""}


import json

def generate_reasons(emp, risk: bool, prob: float) -> str:
    factors = []
    
    # Negative factors
    if emp.overtime: factors.append({"metric": "Overtime", "impact": "negative", "desc": "Working overtime increases burnout risk"})
    if getattr(emp, 'salary', getattr(emp, 'MonthlyIncome', 0)) < 4000: factors.append({"metric": "Salary", "impact": "negative", "desc": "Salary is below average thresholds"})
    if emp.job_satisfaction <= 2: factors.append({"metric": "Job Satisfaction", "impact": "negative", "desc": "Low reported job satisfaction"})
    if emp.work_life_balance <= 2: factors.append({"metric": "Work-Life", "impact": "negative", "desc": "Poor reported work-life balance"})
    if emp.years_at_company < 2: factors.append({"metric": "Tenure", "impact": "negative", "desc": "High turnover rate in early years"})
    if emp.last_promotion_years > 3: factors.append({"metric": "Promotion", "impact": "negative", "desc": "No recent promotions"})
    
    # Positive factors
    if not emp.overtime: factors.append({"metric": "Overtime", "impact": "positive", "desc": "No overtime recorded"})
    if getattr(emp, 'salary', getattr(emp, 'MonthlyIncome', 0)) >= 6000: factors.append({"metric": "Salary", "impact": "positive", "desc": "Competitive salary package"})
    if emp.job_satisfaction >= 3: factors.append({"metric": "Job Satisfaction", "impact": "positive", "desc": "Good job satisfaction"})
    if emp.work_life_balance >= 3: factors.append({"metric": "Work-Life", "impact": "positive", "desc": "Healthy work-life balance"})
    if emp.years_at_company >= 5: factors.append({"metric": "Tenure", "impact": "positive", "desc": "Established tenure indicates stability"})
    if emp.last_promotion_years <= 1: factors.append({"metric": "Promotion", "impact": "positive", "desc": "Recently promoted"})
    
    if risk:
        factors.sort(key=lambda x: 0 if x["impact"] == "negative" else 1)
        # Keep only the top 4 negative factors if risk is high
        factors = [f for f in factors if f["impact"] == "negative"][:4]
    else:
        factors.sort(key=lambda x: 0 if x["impact"] == "positive" else 1)
        # Keep only the top 4 positive factors if risk is low
        factors = [f for f in factors if f["impact"] == "positive"][:4]
        
    return json.dumps(factors)
# ══════════════════════════════════════════════════════════════
# PROTECTED ROUTES — require valid JWT
# ══════════════════════════════════════════════════════════════

@app.post("/predict", response_model=schemas.Prediction)
def predict_attrition(
    employee_data: schemas.EmployeeCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if model is None:
        raise HTTPException(status_code=500, detail="Model is not loaded.")

    if employee_data.email:
        existing = db.query(models.Employee).filter(models.Employee.email == employee_data.email).first()
        if existing:
            raise HTTPException(status_code=400, detail="An employee with this email already exists.")

    db_emp = models.Employee(
        organization_id=current_user.organization_id,
        name=employee_data.name,
        email=employee_data.email,
        age=employee_data.age,
        gender=employee_data.gender,
        department=employee_data.department,
        job_role=employee_data.job_role,
        salary=employee_data.salary,
        years_at_company=employee_data.years_at_company,
        job_satisfaction=employee_data.job_satisfaction,
        work_life_balance=employee_data.work_life_balance,
        overtime=employee_data.overtime,
        performance_rating=employee_data.performance_rating,
        last_promotion_years=employee_data.last_promotion_years,
    )
    db.add(db_emp); db.commit(); db.refresh(db_emp)

    input_df = pd.DataFrame([{
        'Age': employee_data.age,
        'Gender': employee_data.gender,
        'Department': employee_data.department,
        'JobRole': employee_data.job_role,
        'MonthlyIncome': employee_data.salary,
        'YearsAtCompany': employee_data.years_at_company,
        'JobSatisfaction': employee_data.job_satisfaction,
        'WorkLifeBalance': employee_data.work_life_balance,
        'overtime': 1 if employee_data.overtime else 0,
        'PerformanceRating': employee_data.performance_rating,
        'YearsSinceLastPromotion': employee_data.last_promotion_years,
    }])

    prediction_val  = model.predict(input_df)[0]
    attr_prob       = float(model.predict_proba(input_df)[0][1])
    attrition_risk  = bool(prediction_val)
    reasons         = generate_reasons(db_emp, attrition_risk, attr_prob)

    db_pred = models.Prediction(
        employee_id=db_emp.id,
        attrition_risk=attrition_risk,
        probability=attr_prob,
        reasons=reasons,
    )
    db.add(db_pred); db.commit(); db.refresh(db_pred)
    return db_pred


@app.post("/predict/bulk")
async def predict_bulk(
    file: UploadFile,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Accept a CSV, run model on each row, save employees + predictions,
    return a list of results with attrition risk and probability.

    Expected CSV columns (case-insensitive, flexible naming):
      Name, Email, Age, Gender, Department, JobRole,
      MonthlyIncome (or Salary), YearsAtCompany, JobSatisfaction,
      WorkLifeBalance, OverTime (Yes/No or True/False or 1/0),
      PerformanceRating, YearsSinceLastPromotion
    """
    if model is None:
        raise HTTPException(status_code=500, detail="Model is not loaded.")
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted.")

    content = await file.read()
    try:
        df = pd.read_csv(pd.io.common.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {e}")

    # Normalise column names
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    ALIASES = {
        "monthlyincome": "salary", "monthly_income": "salary",
        "jobrole": "job_role", "job_role": "job_role",
        "yearsatcompany": "years_at_company",
        "jobsatisfaction": "job_satisfaction",
        "worklifebalance": "work_life_balance",
        "overtime": "overtime", "overTime": "overtime",
        "performancerating": "performance_rating",
        "yearssincelastpromotion": "last_promotion_years",
        "years_since_last_promotion": "last_promotion_years",
    }
    df.rename(columns={k: v for k, v in ALIASES.items() if k in df.columns}, inplace=True)

    REQUIRED = ["age", "gender", "department", "job_role", "salary",
                "years_at_company", "job_satisfaction", "work_life_balance",
                "overtime", "performance_rating", "last_promotion_years"]
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise HTTPException(status_code=400,
            detail=f"CSV is missing required columns: {', '.join(missing)}")

    results = []
    errors  = []

    for idx, row in df.iterrows():
        try:
            # Parse overtime — can be Yes/No, True/False, 1/0
            ot_raw = str(row["overtime"]).strip().lower()
            overtime = ot_raw in ("yes", "true", "1")

            email = str(row.get("email", "")).strip() or None
            if email:
                existing = db.query(models.Employee).filter(models.Employee.email == email).first()
                if existing:
                    raise Exception(f"Employee with email {email} already exists.")

            db_emp = models.Employee(
                organization_id=current_user.organization_id,
                name=str(row.get("name", "")) or None,
                email=email,
                age=int(row["age"]),
                gender=str(row["gender"]),
                department=str(row["department"]),
                job_role=str(row["job_role"]),
                salary=float(row["salary"]),
                years_at_company=int(row["years_at_company"]),
                job_satisfaction=int(row["job_satisfaction"]),
                work_life_balance=int(row["work_life_balance"]),
                overtime=overtime,
                performance_rating=int(row["performance_rating"]),
                last_promotion_years=int(row["last_promotion_years"]),
            )
            db.add(db_emp); db.flush()

            input_df = pd.DataFrame([{
                "Age": db_emp.age, "Gender": db_emp.gender,
                "Department": db_emp.department, "JobRole": db_emp.job_role,
                "MonthlyIncome": db_emp.salary, "YearsAtCompany": db_emp.years_at_company,
                "JobSatisfaction": db_emp.job_satisfaction,
                "WorkLifeBalance": db_emp.work_life_balance,
                "overtime": 1 if overtime else 0,
                "PerformanceRating": db_emp.performance_rating,
                "YearsSinceLastPromotion": db_emp.last_promotion_years,
            }])

            prob = float(model.predict_proba(input_df)[0][1])
            risk = bool(model.predict(input_df)[0])
            reasons = generate_reasons(db_emp, risk, prob)

            db_pred = models.Prediction(
                employee_id=db_emp.id,
                attrition_risk=risk,
                probability=prob,
                reasons=reasons,
            )
            db.add(db_pred)

            results.append({
                "row": idx + 2,   # 1-based + header offset
                "name": db_emp.name or f"Row {idx+2}",
                "department": db_emp.department,
                "job_role": db_emp.job_role,
                "attrition_risk": risk,
                "probability": round(prob * 100, 1),
                "reasons": reasons,
            })
        except Exception as e:
            errors.append({"row": idx + 2, "error": str(e)})

    db.commit()

    high = sum(1 for r in results if r["attrition_risk"])
    return {
        "processed": len(results),
        "errors": len(errors),
        "high_risk": high,
        "low_risk": len(results) - high,
        "results": results,
        "error_details": errors,
    }



@app.get("/employees", response_model=list[schemas.EmployeeWithPrediction])
def get_employees(
    skip: int = 0,
    limit: int = 500,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.Employee)
        .options(joinedload(models.Employee.predictions))
        .filter(models.Employee.organization_id == current_user.organization_id)
        .order_by(models.Employee.id.desc())
        .offset(skip).limit(limit)
        .all()
    )


@app.get("/stats")
def get_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    employees = (
        db.query(models.Employee)
        .options(joinedload(models.Employee.predictions))
        .filter(models.Employee.organization_id == current_user.organization_id)
        .all()
    )

    total = len(employees)
    if total == 0:
        return {"total_employees": 0, "high_risk_count": 0, "high_risk_percent": 0,
                "departments": [], "genders": [], "age_groups": [], "satisfaction": [],
                "overtime": [], "roles": [], "scatter": []}

    high_risk = 0
    dept_counts  = {}
    gender_counts= {}
    age_groups   = {"18-25": 0, "26-35": 0, "36-45": 0, "46-55": 0, "56+": 0}
    satisfaction_counts = {1: {"Low": 0, "High": 0}, 2: {"Low": 0, "High": 0},
                           3: {"Low": 0, "High": 0}, 4: {"Low": 0, "High": 0}}
    overtime_risk = {"Yes": {"High Risk": 0, "Low Risk": 0}, "No": {"High Risk": 0, "Low Risk": 0}}
    role_counts  = {}
    scatter_data = []

    for e in employees:
        risk = e.predictions[-1].attrition_risk if e.predictions else False
        if risk: high_risk += 1

        dept_counts[e.department]  = dept_counts.get(e.department, 0) + 1
        gender_counts[e.gender]    = gender_counts.get(e.gender, 0) + 1
        role_counts[e.job_role]    = role_counts.get(e.job_role, 0) + 1

        if e.age <= 25:   age_groups["18-25"] += 1
        elif e.age <= 35: age_groups["26-35"] += 1
        elif e.age <= 45: age_groups["36-45"] += 1
        elif e.age <= 55: age_groups["46-55"] += 1
        else:             age_groups["56+"] += 1

        sat_key = e.job_satisfaction if e.job_satisfaction in satisfaction_counts else 3
        if risk: satisfaction_counts[sat_key]["High"] += 1
        else:    satisfaction_counts[sat_key]["Low"]  += 1

        ot_key = "Yes" if e.overtime else "No"
        if risk: overtime_risk[ot_key]["High Risk"] += 1
        else:    overtime_risk[ot_key]["Low Risk"]  += 1

        scatter_data.append({"salary": e.salary, "tenure": e.years_at_company, "risk": 1 if risk else 0})

    return {
        "total_employees":  total,
        "high_risk_count":  high_risk,
        "high_risk_percent": round((high_risk / total) * 100, 1),
        "departments":   [{"name": k, "value": v} for k, v in dept_counts.items()],
        "genders":       [{"name": k, "value": v} for k, v in gender_counts.items()],
        "age_groups":    [{"name": k, "value": v} for k, v in age_groups.items()],
        "roles":         [{"name": k, "value": v} for k, v in sorted(role_counts.items(), key=lambda x: x[1], reverse=True)],
        "satisfaction":  [{"name": f"Rating {k}", "High Risk": v["High"], "Low Risk": v["Low"]} for k, v in satisfaction_counts.items()],
        "overtime":      [{"name": f"Overtime: {k}", "High Risk": v["High Risk"], "Low Risk": v["Low Risk"]} for k, v in overtime_risk.items()],
        "scatter":       scatter_data,
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

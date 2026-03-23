import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import joblib
import pandas as pd
from database import SessionLocal
import models

def predict_all():
    session = SessionLocal()
    employees = session.query(models.Employee).all()
    
    # Load model
    model = joblib.load("model.pkl")

    print(f"Running predictions for {len(employees)} employees...")
    
    count = 0
    for emp in employees:
        # Check if prediction already exists
        existing = session.query(models.Prediction).filter(models.Prediction.employee_id == emp.id).first()
        if existing:
            continue

        input_df = pd.DataFrame([{
            'Age': emp.age,
            'Gender': emp.gender,
            'Department': emp.department,
            'JobRole': emp.job_role,
            'MonthlyIncome': emp.salary,
            'YearsAtCompany': emp.years_at_company,
            'JobSatisfaction': emp.job_satisfaction,
            'WorkLifeBalance': emp.work_life_balance,
            'overtime': 1 if emp.overtime else 0,
            'PerformanceRating': emp.performance_rating,
            'YearsSinceLastPromotion': emp.last_promotion_years
        }])

        prediction_val = model.predict(input_df)[0]
        prob = model.predict_proba(input_df)[0][1]

        attrition_risk = bool(prediction_val)
        reasons = "Probability over threshold" if attrition_risk else "Normal"

        pred = models.Prediction(
            employee_id=emp.id,
            attrition_risk=attrition_risk,
            probability=float(prob),
            reasons=reasons
        )
        session.add(pred)
        count += 1
        
        if count % 100 == 0:
            session.commit()
            print(f"Processed {count} records...")

    session.commit()
    session.close()
    print(f"Done! Created predictions for {count} employees.")

if __name__ == "__main__":
    predict_all()

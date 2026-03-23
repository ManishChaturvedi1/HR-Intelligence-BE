import sys
import os
import pandas as pd
from sqlalchemy import create_engine, text
from database import engine, Base, SessionLocal, db_url
import urllib
import models

# Path mapping for IBM dataset
DATASET_PATH = "data/WA_Fn-UseC_-HR-Employee-Attrition.csv"

def create_database_if_not_exists():
    try:
        # Connect to master to create DB
        master_odbc = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER=ALOK-PC\\SQLEXPRESS;DATABASE=master;Trusted_Connection=yes;autocommit=True"
        master_url = f"mssql+pyodbc:///?odbc_connect={urllib.parse.quote_plus(master_odbc)}"
        master_engine = create_engine(master_url, isolation_level="AUTOCOMMIT")
        
        with master_engine.connect() as conn:
            res = conn.execute(text("SELECT name FROM sys.databases WHERE name = 'EmpAttrition'"))
            if not res.fetchone():
                print("Database 'EmpAttrition' not found. Creating it...")
                conn.execute(text("CREATE DATABASE EmpAttrition"))
                print("Database created.")
            else:
                print("Database 'EmpAttrition' already exists.")
    except Exception as e:
        print(f"Could not connect or create database. Ensure SQL Server is running: {e}")

def get_gender(gender_str):
    return gender_str

def get_boolean(val):
    return True if val == 'Yes' else False

def seed_data():
    create_database_if_not_exists()
    
    # Create tables
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    
    # Load dataset
    print(f"Loading dataset from {DATASET_PATH}...")
    if not os.path.exists(DATASET_PATH):
        print(f"Dataset not found at {DATASET_PATH}")
        return

    df = pd.read_csv(DATASET_PATH)
    
    session = SessionLocal()
    
    # Check if data already exists
    existing = session.query(models.Employee).first()
    if existing:
        print("Data already seeded.")
        return

    print("Seeding initial data...")
    count = 0
    # Map dataset to our DB Schema
    # Database schema matches: age, gender, department, job_role, salary (MonthlyIncome), 
    # years_at_company(YearsAtCompany), job_satisfaction(JobSatisfaction),
    # work_life_balance(WorkLifeBalance), overtime(OverTime), performance_rating(PerformanceRating),
    # last_promotion_years(YearsSinceLastPromotion)
    
    for _, row in df.iterrows():
        emp = models.Employee(
            name=f"Emp_{row['EmployeeNumber']}",
            email=f"emp_{row['EmployeeNumber']}@company.com",
            age=row['Age'],
            gender=row['Gender'],
            department=row['Department'],
            job_role=row['JobRole'],
            salary=float(row['MonthlyIncome']),
            years_at_company=int(row['YearsAtCompany']),
            job_satisfaction=int(row['JobSatisfaction']),
            work_life_balance=int(row['WorkLifeBalance']),
            overtime=get_boolean(row['OverTime']),
            performance_rating=int(row['PerformanceRating']),
            last_promotion_years=int(row['YearsSinceLastPromotion'])
        )
        session.add(emp)
        count += 1
        
        # Commit in batches of 100 for performance
        if count % 100 == 0:
            session.commit()
    
    session.commit()
    session.close()
    print(f"Successfully seeded {count} employees.")

if __name__ == '__main__':
    seed_data()

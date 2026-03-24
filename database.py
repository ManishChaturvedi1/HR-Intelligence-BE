from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import urllib

import os

# Connect to the local SQL Server using Windows Authentication.
# The server name is usually "localhost" or a named instance like "localhost\SQLEXPRESS".
SERVER = os.getenv("DB_SERVER", "ALOK-PC\\SQLEXPRESS")
DATABASE = os.getenv("DB_NAME", "EmpAttrition")
DRIVER = "ODBC Driver 17 for SQL Server"

# Construct ODBC connection string
odbc_str = f"DRIVER={{{DRIVER}}};SERVER={SERVER};DATABASE={DATABASE};Trusted_Connection=yes;"
local_url = f"mssql+pyodbc:///?odbc_connect={urllib.parse.quote_plus(odbc_str)}"

# Use DATABASE_URL from .env if provided (e.g., matching a deployed PostgreSQL/MySQL instance)
db_url = os.getenv("DATABASE_URL")

if db_url:
    # Fix Render issue where they provide 'postgres://' instead of 'postgresql://'
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
else:
    # Fallback to local SQL server if no environment variable is set
    db_url = local_url

engine = create_engine(db_url, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

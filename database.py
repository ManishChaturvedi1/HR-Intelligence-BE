from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import urllib

# Connect to the local SQL Server using Windows Authentication.
# The server name is usually "localhost" or a named instance like "localhost\SQLEXPRESS".
SERVER = "ALOK-PC\\SQLEXPRESS"
DATABASE = "EmpAttrition"
DRIVER = "ODBC Driver 17 for SQL Server"

# Construct ODBC connection string
odbc_str = f"DRIVER={{{DRIVER}}};SERVER={SERVER};DATABASE={DATABASE};Trusted_Connection=yes;"
db_url = f"mssql+pyodbc:///?odbc_connect={urllib.parse.quote_plus(odbc_str)}"

engine = create_engine(db_url, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

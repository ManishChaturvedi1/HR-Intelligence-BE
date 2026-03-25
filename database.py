from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import urllib.parse
import os

# Load environment variables from .env
load_dotenv()

# ── Build connection from individual env vars (Supabase recommended) ────────
DB_USER     = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST     = os.getenv("DB_HOST")
DB_PORT     = os.getenv("DB_PORT", "5432")
DB_NAME     = os.getenv("DB_NAME", "postgres")

# Fallback: DATABASE_URL (if individual vars not set)
DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip() or None

if DB_USER and DB_PASSWORD and DB_HOST:
    # URL-encode credentials so special chars don't break the URL
    _user     = urllib.parse.quote_plus(DB_USER)
    _password = urllib.parse.quote_plus(DB_PASSWORD)
    DATABASE_URL = (
        f"postgresql+psycopg2://{_user}:{_password}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?sslmode=require"
    )
    print(f"DEBUG [db]: Using individual vars → {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

elif DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    if DATABASE_URL.startswith("postgresql://") and "+psycopg2" not in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
    if "sslmode" not in DATABASE_URL:
        DATABASE_URL += "?sslmode=require" if "?" not in DATABASE_URL else "&sslmode=require"
    print("DEBUG [db]: Using DATABASE_URL from environment.")

else:
    print("WARNING [db]: No database credentials found.")
    DATABASE_URL = None

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 10},
) if DATABASE_URL else None

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) if engine else None
Base = declarative_base()


def get_db():
    if SessionLocal is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Database not configured.")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

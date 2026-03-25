from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import urllib.parse
import os

# Load environment variables from .env
load_dotenv()

# ── Strategy 1: individual Supabase vars (local .env) ──────────────────────
DB_USER     = os.getenv("user")
DB_PASSWORD = os.getenv("password")
DB_HOST     = os.getenv("host")
DB_PORT     = os.getenv("port", "6543")
DB_NAME     = os.getenv("dbname")

# ── Strategy 2: DATABASE_URL (Render / other hosting) ──────────────────────
DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip() or None

if DB_USER and DB_PASSWORD and DB_HOST and DB_NAME:
    # URL-encode credentials so special chars like @, %, # don't break the URL
    _user     = urllib.parse.quote_plus(DB_USER)
    _password = urllib.parse.quote_plus(DB_PASSWORD)
    DATABASE_URL = (
        f"postgresql+psycopg2://{_user}:{_password}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?sslmode=require"
    )
    print(f"DEBUG: Using individual env vars → {DB_HOST}:{DB_PORT}/{DB_NAME}")

elif DATABASE_URL:
    # Fix Render's legacy 'postgres://' prefix
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    # Ensure psycopg2 driver is specified
    if DATABASE_URL.startswith("postgresql://") and "+psycopg2" not in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
    # Supabase requires SSL — add if missing
    if "sslmode" not in DATABASE_URL:
        DATABASE_URL += "?sslmode=require" if "?" not in DATABASE_URL else "&sslmode=require"
    print("DEBUG: Using DATABASE_URL from environment.")

else:
    # Don't crash at import time — server must start to bind the port.
    # Routes that need DB will return 503 via get_db().
    print("WARNING: No database credentials found. Set DATABASE_URL or individual DB vars.")
    DATABASE_URL = None

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    # sslmode is already embedded in DATABASE_URL — don't pass it again in
    # connect_args or SQLAlchemy raises SAWarning: Duplicate query string key
    connect_args={"connect_timeout": 10},
) if DATABASE_URL else None

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) if engine else None
Base = declarative_base()


def get_db():
    if SessionLocal is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Database not configured. Set DATABASE_URL on the server.")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

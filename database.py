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

# DEBUG: Show which env vars are detected (mask passwords)
print(f"DEBUG [db]: DB_USER={DB_USER!r}, DB_HOST={DB_HOST!r}, DB_NAME={DB_NAME!r}, DB_PASSWORD={'SET' if DB_PASSWORD else 'NOT SET'}")
if DATABASE_URL:
    # Show URL with password masked
    _masked = DATABASE_URL
    try:
        _at = _masked.index("@")
        _colon = _masked.index(":", _masked.index("//") + 2)
        _masked = _masked[:_colon+1] + "****" + _masked[_at:]
    except ValueError:
        pass
    print(f"DEBUG [db]: DATABASE_URL = {_masked}")
else:
    print("DEBUG [db]: DATABASE_URL = NOT SET")

if DB_USER and DB_PASSWORD and DB_HOST and DB_NAME:
    # URL-encode credentials so special chars like @, %, # don't break the URL
    _user     = urllib.parse.quote_plus(DB_USER)
    _password = urllib.parse.quote_plus(DB_PASSWORD)
    DATABASE_URL = (
        f"postgresql+psycopg2://{_user}:{_password}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?sslmode=require"
    )
    print(f"DEBUG [db]: *** Using STRATEGY 1 (individual vars) → {DB_HOST}:{DB_PORT}/{DB_NAME}")

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
    print("DEBUG [db]: *** Using STRATEGY 2 (DATABASE_URL)")

else:
    print("WARNING [db]: No database credentials found. Set DATABASE_URL on the server.")
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
        raise HTTPException(status_code=503, detail="Database not configured. Set DATABASE_URL on the server.")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

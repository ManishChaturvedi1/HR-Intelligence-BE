from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import urllib.parse
import os

# Load environment variables from .env
load_dotenv()

# Supabase / PostgreSQL connection details from environment
DB_USER = os.getenv("user")
DB_PASSWORD = os.getenv("password")
DB_HOST = os.getenv("host")
DB_PORT = os.getenv("port", "6543")
DB_NAME = os.getenv("dbname")

# URL-encode credentials so special chars like @, %, # don't break the URL
_user = urllib.parse.quote_plus(DB_USER or "")
_password = urllib.parse.quote_plus(DB_PASSWORD or "")

# Build SQLAlchemy connection URL
DATABASE_URL = (
    f"postgresql+psycopg2://{_user}:{_password}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?sslmode=require"
)

print(f"DEBUG: Connecting to {DB_HOST}:{DB_PORT}/{DB_NAME} as {DB_USER}")

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 10},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

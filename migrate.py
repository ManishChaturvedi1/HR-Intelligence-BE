"""
migrate.py — Adds new columns to existing tables for the multi-tenant auth upgrade.
Run once: venv\Scripts\python.exe backend\migrate.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import text
from database import engine

migrations = [
    # Create organizations table if not exists
    """
    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='organizations' AND xtype='U')
    CREATE TABLE organizations (
        id         INT IDENTITY(1,1) PRIMARY KEY,
        name       NVARCHAR(100) NOT NULL,
        slug       NVARCHAR(60)  NOT NULL UNIQUE,
        created_at DATETIME2 DEFAULT GETUTCDATE()
    )
    """,

    # Add organization_id to users if missing
    """
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME='users' AND COLUMN_NAME='organization_id'
    )
    ALTER TABLE users ADD organization_id INT NULL
    """,

    # Add hashed_password to users if missing
    """
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME='users' AND COLUMN_NAME='hashed_password'
    )
    ALTER TABLE users ADD hashed_password NVARCHAR(255) NULL
    """,

    # Add created_at to users if missing
    """
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME='users' AND COLUMN_NAME='created_at'
    )
    ALTER TABLE users ADD created_at DATETIME2 DEFAULT GETUTCDATE()
    """,

    # Add organization_id to employees if missing
    """
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME='employees' AND COLUMN_NAME='organization_id'
    )
    ALTER TABLE employees ADD organization_id INT NULL
    """,

    # Rename old 'password' column to avoid clash (if it still exists)
    """
    IF EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME='users' AND COLUMN_NAME='password'
    )
    EXEC sp_rename 'users.password', 'password_old', 'COLUMN'
    """,
]

print("Running migrations against SQL Server...")
with engine.connect() as conn:
    for i, stmt in enumerate(migrations, 1):
        conn.execute(text(stmt.strip()))
        conn.commit()
        print(f"  [{i}/{len(migrations)}] OK")

print("\nAll migrations applied successfully!")
print("You can now restart the backend server.")

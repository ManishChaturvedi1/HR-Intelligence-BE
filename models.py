from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base


class Organization(Base):
    """One row per tenant (company). The isolation boundary."""
    __tablename__ = "organizations"

    id   = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(60), unique=True, index=True, nullable=False)  # e.g. "acme-corp"
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    users     = relationship("User",     back_populates="organization")
    employees = relationship("Employee", back_populates="organization")


class User(Base):
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True, index=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    name            = Column(String(100))
    email           = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role            = Column(String(10), default="hr")   # "admin" | "hr"
    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    organization = relationship("Organization", back_populates="users")


class Employee(Base):
    __tablename__ = "employees"

    id              = Column(Integer, primary_key=True, index=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    name            = Column(String(100), nullable=True)
    email           = Column(String(100), nullable=True)
    age             = Column(Integer)
    gender          = Column(String(10))
    department      = Column(String(50))
    job_role        = Column(String(50))
    salary          = Column(Float)
    years_at_company    = Column(Integer)
    job_satisfaction    = Column(Integer)
    work_life_balance   = Column(Integer)
    overtime            = Column(Boolean)
    performance_rating  = Column(Integer)
    last_promotion_years= Column(Integer)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    predictions  = relationship("Prediction", back_populates="employee")
    organization = relationship("Organization", back_populates="employees")


class Prediction(Base):
    __tablename__ = "predictions"

    id              = Column(Integer, primary_key=True, index=True, autoincrement=True)
    employee_id     = Column(Integer, ForeignKey("employees.id"))
    attrition_risk  = Column(Boolean)
    probability     = Column(Float)
    reasons         = Column(String(1000), nullable=True)
    predicted_at    = Column(DateTime(timezone=True), server_default=func.now())

    employee = relationship("Employee", back_populates="predictions")

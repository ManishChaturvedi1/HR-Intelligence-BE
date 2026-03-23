from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# ── Employee ──────────────────────────────────────────────────
class EmployeeBase(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    age: int
    gender: str
    department: str
    job_role: str
    salary: float
    years_at_company: int
    job_satisfaction: int
    work_life_balance: int
    overtime: bool
    performance_rating: int
    last_promotion_years: int

class EmployeeCreate(EmployeeBase):
    pass

class Employee(EmployeeBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ── Prediction ────────────────────────────────────────────────
class PredictionBase(BaseModel):
    attrition_risk: bool
    probability: float
    reasons: Optional[str] = None

class PredictionCreate(PredictionBase):
    employee_id: int

class Prediction(PredictionBase):
    id: int
    employee_id: int
    predicted_at: datetime

    class Config:
        from_attributes = True

class EmployeeWithPrediction(Employee):
    predictions: list[Prediction] = []

    class Config:
        from_attributes = True


# ── Auth ──────────────────────────────────────────────────────
from pydantic import BaseModel, Field, field_validator
import re

class RegisterRequest(BaseModel):
    org_name:  str   # e.g. "Acme Corp"
    org_slug:  str   # e.g. "acme-corp"  (unique per tenant)
    name:      str   # admin user's display name
    email:     str
    password:  str = Field(..., min_length=8)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not re.search(r"[A-Za-z]", v):
            raise ValueError("Password must contain at least one letter.")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one number.")
        return v

class LoginRequest(BaseModel):
    email:    str
    password: str

class UserOut(BaseModel):
    id:       int
    name:     str
    email:    str
    role:     str
    org_name: str
    org_slug: str

class AuthResponse(BaseModel):
    access_token: str
    token_type:   str
    user:         UserOut

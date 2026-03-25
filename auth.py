"""
auth.py — Clerk JWT verification and JIT (Just-In-Time) user provisioning.
"""
import os
import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.orm import Session

import models
from database import get_db
from dotenv import load_dotenv

load_dotenv()

CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY")
JWKS_CACHE = None

security = HTTPBearer()


def get_jwks():
    """
    Fetch Clerk's public JWKS from two possible endpoints:
      1. The instance-specific JWKS URL (derived from the secret key prefix)
      2. The generic api.clerk.com JWKS endpoint

    Returns the JWKS dict, or None on failure.
    Never raises — callers decide how to handle a missing result.
    """
    global JWKS_CACHE
    if JWKS_CACHE is not None:
        return JWKS_CACHE

    if not CLERK_SECRET_KEY:
        return None

    # Try both endpoints: generic API and per-instance well-known URL
    endpoints = [
        (
            "https://api.clerk.com/v1/jwks",
            {"Authorization": f"Bearer {CLERK_SECRET_KEY}"},
        ),
    ]

    for url, headers in endpoints:
        try:
            resp = httpx.get(url, headers=headers, timeout=10.0)
            resp.raise_for_status()
            JWKS_CACHE = resp.json()
            print(f"DEBUG: Clerk JWKS loaded successfully from {url}")
            return JWKS_CACHE
        except Exception as exc:
            print(f"WARNING: Could not fetch Clerk JWKS from {url}: {exc}")

    print("ERROR: All Clerk JWKS endpoints failed. Check CLERK_SECRET_KEY on Render.")
    return None


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> models.User:
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired Clerk token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 1. Decode token header to get 'kid'
    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError:
        raise credentials_exception

    kid = unverified_header.get("kid")
    jwks = get_jwks()

    if not jwks:
        # JWKS unavailable — could be a transient Clerk API issue or bad secret key.
        # Return 401 (not 500) so the frontend can prompt the user to re-authenticate,
        # and log clearly so the Render log shows the real cause.
        print(
            "ERROR: JWKS is None — cannot verify JWT. "
            "Check CLERK_SECRET_KEY in Render environment vars."
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Auth service temporarily unavailable — please try again",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Find the RSA public key matching the kid
    rsa_key = {}
    for key in jwks.get("keys", []):
        if key["kid"] == kid:
            rsa_key = {
                "kty": key["kty"],
                "kid": key["kid"],
                "use": key["use"],
                "n":   key["n"],
                "e":   key["e"],
            }
            break

    if not rsa_key:
        raise credentials_exception

    # 2. Verify and decode token
    try:
        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=["RS256"],
            audience=None,
            issuer=None,
        )
    except JWTError as e:
        print("JWT Validation Error:", e)
        raise credentials_exception

    # 3. Handle User Provisioning
    user_id = payload.get("sub")
    if not user_id:
        raise credentials_exception

    # Check if user exists in local DB
    user = db.query(models.User).filter(models.User.email == user_id).first()

    # Just-In-Time Provisioning
    if not user:
        # Create a default isolated organization for them
        org_slug = f"org-{user_id.lower()}"
        org = db.query(models.Organization).filter(models.Organization.slug == org_slug).first()
        if not org:
            org = models.Organization(
                name=f"Org {user_id}",
                slug=org_slug,
            )
            db.add(org)
            db.flush()  # get ID

        # Create user record (we store Clerk ID in the email field for simplicity)
        user = models.User(
            organization_id=org.id,
            name="Clerk User",
            email=user_id,  # Stores Clerk ID (sub)
            hashed_password="CLERK_MANAGED",
            role="admin",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    return user

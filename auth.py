"""
auth.py — Clerk JWT verification and JIT (Just-In-Time) user provisioning.

Every failure path logs clearly so you can diagnose from Render logs.
"""
import os
import traceback
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
    Fetch Clerk JWKS (public keys for JWT verification).
    Returns the JWKS dict or None. Never raises.
    """
    global JWKS_CACHE
    if JWKS_CACHE is not None:
        return JWKS_CACHE

    if not CLERK_SECRET_KEY:
        print("ERROR [auth]: CLERK_SECRET_KEY is not set!")
        return None

    try:
        resp = httpx.get(
            "https://api.clerk.com/v1/jwks",
            headers={"Authorization": f"Bearer {CLERK_SECRET_KEY}"},
            timeout=10.0,
        )
        resp.raise_for_status()
        JWKS_CACHE = resp.json()
        print(f"DEBUG [auth]: JWKS loaded — {len(JWKS_CACHE.get('keys', []))} keys")
        return JWKS_CACHE
    except Exception as exc:
        print(f"ERROR [auth]: JWKS fetch failed: {exc}")
        return None


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> models.User:
    token = credentials.credentials

    def _fail(detail="Invalid or expired Clerk token"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 1. Decode header
    try:
        unverified_header = jwt.get_unverified_header(token)
    except Exception as e:
        print(f"ERROR [auth]: Cannot decode JWT header: {e}")
        _fail()

    kid = unverified_header.get("kid")

    # 2. Get JWKS
    jwks = get_jwks()
    if not jwks:
        print("ERROR [auth]: JWKS unavailable — cannot verify token")
        _fail("Auth service temporarily unavailable — please retry")

    # 3. Find matching RSA key
    rsa_key = None
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            rsa_key = {
                "kty": key["kty"],
                "kid": key["kid"],
                "use": key["use"],
                "n":   key["n"],
                "e":   key["e"],
            }
            break

    if not rsa_key:
        print(f"ERROR [auth]: No JWKS key matches kid={kid}")
        _fail()

    # 4. Verify & decode
    try:
        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=["RS256"],
            options={"verify_aud": False},   # Clerk tokens don't always set aud
        )
    except JWTError as e:
        print(f"ERROR [auth]: JWT decode failed: {e}")
        _fail()
    except Exception as e:
        print(f"ERROR [auth]: Unexpected error decoding JWT: {e}")
        print(traceback.format_exc())
        _fail()

    # 5. Extract user identity
    user_id = payload.get("sub")
    if not user_id:
        print("ERROR [auth]: JWT has no 'sub' claim")
        _fail()

    # 6. Look up or provision user (JIT)
    try:
        user = db.query(models.User).filter(models.User.email == user_id).first()

        if not user:
            org_slug = f"org-{user_id.lower()}"
            org = db.query(models.Organization).filter(
                models.Organization.slug == org_slug
            ).first()
            if not org:
                org = models.Organization(name=f"Org {user_id}", slug=org_slug)
                db.add(org)
                db.flush()

            user = models.User(
                organization_id=org.id,
                name="Clerk User",
                email=user_id,
                hashed_password="CLERK_MANAGED",
                role="admin",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"DEBUG [auth]: JIT-provisioned user {user_id} in org {org.slug}")

        return user

    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR [auth]: DB error during user lookup/provision: {e}")
        print(traceback.format_exc())
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Database error during authentication: {str(e)}",
        )

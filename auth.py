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
    global JWKS_CACHE
    if JWKS_CACHE is None and CLERK_SECRET_KEY:
        try:
            resp = httpx.get(
                "https://api.clerk.com/v1/jwks",
                headers={"Authorization": f"Bearer {CLERK_SECRET_KEY}"}
            )
            resp.raise_for_status()
            JWKS_CACHE = resp.json()
        except httpx.HTTPError:
            print("Failed to fetch Clerk JWKS. Check your CLERK_SECRET_KEY.")
            return None
    return JWKS_CACHE

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
        # If we failed to load JWKS (e.g. key missing in dev), we optionally allow mock decoding
        # WARNING: In production, this should fail hard.
        if not CLERK_SECRET_KEY:
            try:
                payload = jwt.get_unverified_claims(token)
            except JWTError:
                raise credentials_exception
        else:
            raise HTTPException(status_code=500, detail="Failed to load auth keys from Clerk")
    else:
        # Find the RSA public key matching the kid
        rsa_key = {}
        for key in jwks.get("keys", []):
            if key["kid"] == kid:
                rsa_key = {
                    "kty": key["kty"],
                    "kid": key["kid"],
                    "use": key["use"],
                    "n": key["n"],
                    "e": key["e"]
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
                issuer=None
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
                slug=org_slug
            )
            db.add(org)
            db.flush() # get ID
        
        # Create user record (we store Clerk ID in the email field for simplicity right now)
        user = models.User(
            organization_id=org.id,
            name="Clerk User",
            email=user_id, # Stores Clerk ID (sub)
            hashed_password="CLERK_MANAGED",
            role="admin"
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    return user

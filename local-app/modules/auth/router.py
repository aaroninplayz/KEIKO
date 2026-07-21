import os
import shutil
import logging
import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from core.database import get_db
from .models_db import User
from .utils import hash_password, verify_password, create_access_token
from .dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

SESSIONS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "sessions"))

class SignupRequest(BaseModel):
    email: str
    name: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class GoogleLoginRequest(BaseModel):
    email: str
    name: str
    google_token: str

@router.post("/auth/signup", status_code=201)
def signup(request: SignupRequest, db: Session = Depends(get_db)):
    """
    Registers a new user in the system with privacy_consent set to False.
    """
    existing_user = db.query(User).filter(User.email == request.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    hashed_pwd = hash_password(request.password)
    new_user = User(
        email=request.email,
        full_name=request.name,
        hashed_password=hashed_pwd,
        privacy_consent=False
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {"status": "success", "message": "User registered successfully"}

@router.post("/auth/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """
    Authenticates a user and returns a JWT access token.
    """
    user = db.query(User).filter(User.email == request.email).first()
    if not user or not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    if not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/auth/google-login")
def google_login(request: GoogleLoginRequest, db: Session = Depends(get_db)):
    """
    Simulates Google OAuth. Automatically registers the user if they don't exist.
    """
    if not request.google_token.startswith("mock-"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Google token"
        )
    
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        user = User(
            email=request.email,
            full_name=request.name,
            privacy_consent=False,
            oauth_provider="google",
            oauth_id=request.google_token
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/auth/consent")
def update_consent(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Allows a candidate to accept the privacy policy.
    """
    current_user.privacy_consent = True
    current_user.consent_date = datetime.datetime.now(datetime.timezone.utc)
    db.commit()
    return {"status": "success", "message": "Privacy consent accepted"}

@router.delete("/auth/account")
def delete_account(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Deletes the candidate's account and all associated sessions and physical files.
    """
    # Track the session IDs to delete directories later
    session_ids = [s.session_id for s in current_user.sessions]
    
    # Delete the user from the database. Cascading delete-orphan handles cascading to interview sessions.
    db.delete(current_user)
    db.commit()
    
    # Remove physical directories on disk
    for session_id in session_ids:
        sess_path = os.path.join(SESSIONS_DIR, session_id)
        if os.path.exists(sess_path):
            try:
                shutil.rmtree(sess_path)
            except Exception as e:
                logger.error(f"Failed to delete session directory {sess_path}: {e}")
                
    return {"status": "success", "message": "Account and all associated session data deleted successfully"}

@router.get("/history")
def get_history(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Retrieves all past interview sessions, final reports, and metrics associated with the authenticated user.
    """
    from modules.interview.models_db import InterviewSession
    
    sessions = db.query(InterviewSession).filter(
        InterviewSession.user_id == current_user.id
    ).order_by(InterviewSession.created_at.desc()).all()
    
    history_list = []
    for s in sessions:
        history_list.append({
            "session_id": s.session_id,
            "interview_type": s.interview_type,
            "difficulty_mode": s.difficulty_mode,
            "duration_type": s.duration_type,
            "duration_value": s.duration_value,
            "phase": s.phase,
            "status": s.status,
            "final_report": s.final_report,
            "created_at": s.created_at.isoformat() if s.created_at else None
        })
        
    return history_list

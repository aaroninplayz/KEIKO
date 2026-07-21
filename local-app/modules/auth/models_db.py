import datetime
from sqlalchemy import Column, String, Integer, Boolean, DateTime
from sqlalchemy.orm import relationship
from core.database import Base

class User(Base):
    """
    SQLAlchemy model representing a candidate user in the system.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=True)
    full_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    privacy_consent = Column(Boolean, default=False, nullable=False)
    consent_date = Column(DateTime, nullable=True)
    oauth_provider = Column(String(50), nullable=True)
    oauth_id = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc), nullable=False)

    # Relationships
    sessions = relationship(
        "InterviewSession",
        back_populates="user",
        cascade="all, delete-orphan"
    )

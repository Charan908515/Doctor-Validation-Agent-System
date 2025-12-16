from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from datetime import datetime
from database import Base

class Provider(Base):
    __tablename__ = "providers"
    
    id = Column(Integer, primary_key=True, index=True)
    hospital_name = Column(String)
    address = Column(Text)
    doctor_name = Column(String, index=True)
    specialization = Column(String)
    qualification = Column(String)
    phone_number = Column(String)
    license_number = Column(String)
    status = Column(String)  # verified, updated details, human verification needed
    reason = Column(Text)
    confidence_score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class UploadHistory(Base):
    __tablename__ = "upload_history"
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String)
    file_path = Column(String)  # Path to uploaded file
    file_type = Column(String)  # CSV or PDF
    status = Column(String)  # Completed, Pending, Failed
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    record_count = Column(Integer, default=0)

class ValidationResult(Base):
    __tablename__ = "validation_results"
    
    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer)
    original_data = Column(Text)  # JSON string
    validated_data = Column(Text)  # JSON string
    changes_accepted = Column(Integer, default=0)  # 0=pending, 1=accepted, -1=rejected
    validated_at = Column(DateTime, default=datetime.utcnow)

class ValidationSession(Base):
    __tablename__ = "validation_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    upload_id = Column(Integer)
    session_id = Column(String, unique=True, index=True)
    total_hospitals = Column(Integer, default=0)
    completed_hospitals = Column(Integer, default=0)
    total_records = Column(Integer, default=0)
    verified_count = Column(Integer, default=0)
    updated_count = Column(Integer, default=0)
    needs_review_count = Column(Integer, default=0)
    status = Column(String, default="in_progress")  # in_progress, completed, failed
    current_hospital = Column(String, default="")
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    status_message = Column(String, default="")  # Detailed status message (e.g., "Finding address...", "Scraping...")

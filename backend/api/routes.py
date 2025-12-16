from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from database import get_db
from models import Provider, UploadHistory, ValidationResult, ValidationSession
import pandas as pd
import json
import sys
import re
import os
from datetime import datetime
from typing import List
import uuid
import threading
import io
from pydantic import BaseModel
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from vallidation_agent import validate_hospital_doctors, group_doctors_by_hospital, validate_and_write_incremental

router = APIRouter(prefix="/api", tags=["validation"])


class StartValidationRequest(BaseModel):
    upload_id: int

_validation_sessions = {}
_sessions_lock = threading.Lock()

@router.post("/upload/csv")
async def upload_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload CSV file with provider data"""
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files allowed")
    
    try:
       
        contents = await file.read()
        df = pd.read_csv(io.BytesIO(contents))
        
        
        uploads_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'uploads')
        os.makedirs(uploads_dir, exist_ok=True)
        
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_filename = f"{timestamp}_{file.filename}"
        file_path = os.path.join(uploads_dir, unique_filename)
        
        
        df.to_csv(file_path, index=False, encoding='utf-8')
        
        upload = UploadHistory(
            filename=file.filename,
            file_path=file_path,
            file_type="CSV",
            status="Completed",
            record_count=len(df)
        )
        db.add(upload)
        db.commit()
        db.refresh(upload)
        
        return {
            "message": "CSV uploaded successfully",
            "filename": file.filename,
            "records": len(df),
            "upload_id": upload.id
        }
    except Exception as e:
        print(f"CSV Upload Error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/validate/start")
async def start_validation(upload_id: int, db: Session = Depends(get_db)):
    """Start validation workflow for uploaded CSV (LEGACY - uses batch mode)"""
    upload = db.query(UploadHistory).filter(UploadHistory.id == upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    
    try:
        
        csv_path = os.path.join(os.path.dirname(__file__), '..', '..', 'testing_data.csv')
        df = pd.read_csv(csv_path, on_bad_lines='skip')
        
        hospitals = group_doctors_by_hospital(df)
        
        all_results = []
        for hospital_key, csv_doctors in hospitals.items():
            hospital_name, address = hospital_key.split("||")
            
            try:
                results = validate_hospital_doctors(hospital_name, address, csv_doctors)
                all_results.extend(results)
            except Exception as e:
                for doctor in csv_doctors:
                    all_results.append({
                        **doctor,
                        "status": "human verification needed",
                        "reason": f"Validation error: {str(e)}"
                    })
        
        # Save to database
        for result in all_results:
            provider = Provider(
                hospital_name=result.get("hospital_name", ""),
                address=result.get("address", ""),
                doctor_name=result.get("doctor_name", ""),
                specialization=result.get("specialization", ""),
                qualification=result.get("qualification", ""),
                phone_number=result.get("phone_number", ""),
                license_number=result.get("license_number", ""),
                status=result.get("status", ""),
                reason=result.get("reason", ""),
                confidence_score=result.get("confidence_score", 0.0)
            )
            db.add(provider)
        
        db.commit()
        
        return {
            "message": "Validation completed",
            "total_processed": len(all_results),
            "summary": {
                "verified": sum(1 for r in all_results if r.get("status") == "verified"),
                "updated": sum(1 for r in all_results if r.get("status") == "updated details"),
                "needs_review": sum(1 for r in all_results if r.get("status") == "human verification needed")
            }
        }
    except Exception as e:
        print(f"Validation Error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


def run_incremental_validation(session_id: str, csv_path: str, output_csv: str):
    """Background task to run incremental validation"""
    from database import SessionLocal
    db = SessionLocal()
    

    
    try:
        # Get session
        session = db.query(ValidationSession).filter(ValidationSession.session_id == session_id).first()
        if not session:
            print(f"Session {session_id} not found")
            return
        
        # Progress callback
        def progress_callback(hospital_idx, total_hospitals, hospital_name, status, results, stats, status_message=""):
            session.completed_hospitals = hospital_idx
            session.current_hospital = hospital_name
            session.status_message = status_message
            session.total_records = stats.get("total_processed", 0)
            session.verified_count = stats.get("verified", 0)
            session.updated_count = stats.get("updated", 0)
            session.needs_review_count = stats.get("needs_review", 0)
            db.commit()
            print(f"Progress: {hospital_idx}/{total_hospitals} - {hospital_name} - {status} - {status_message}")
        
        # Database callback
        def db_callback(results):
            for result in results:
                provider = Provider(
                    hospital_name=result.get("hospital_name", ""),
                    address=result.get("address", ""),
                    doctor_name=result.get("doctor_name", ""),
                    specialization=result.get("specialization", ""),
                    qualification=result.get("qualification", ""),
                    phone_number=result.get("phone_number", ""),
                    license_number=result.get("license_number", ""),
                    status=result.get("status", ""),
                    reason=result.get("reason", ""),
                    confidence_score=result.get("confidence_score", 0.0)
                )
                db.add(provider)
            db.commit()
        
        # Run incremental validation
        stats = validate_and_write_incremental(
            input_csv=csv_path,
            output_csv=output_csv,
            progress_callback=progress_callback,
            db_callback=db_callback
        )
        
        # Update session as completed
        session.status = "completed"
        session.completed_at = datetime.utcnow()
        session.status_message = "Validation completed"
        session.total_records = stats.get("total_processed", 0)
        session.verified_count = stats.get("verified", 0)
        session.updated_count = stats.get("updated", 0)
        session.needs_review_count = stats.get("needs_review", 0)
        db.commit()
        
        print(f"Validation session {session_id} completed successfully")
        
    except Exception as e:
        print(f"Error in validation session {session_id}: {e}")
        import traceback
        traceback.print_exc()
        
        session = db.query(ValidationSession).filter(ValidationSession.session_id == session_id).first()
        if session:
            session.status = "failed"
            session.status_message = f"Error: {str(e)}"
            session.completed_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


@router.post("/validate/start-incremental")
async def start_incremental_validation(
    request: StartValidationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Start incremental validation with real-time progress updates"""
    upload = db.query(UploadHistory).filter(UploadHistory.id == request.upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    
    if not upload.file_path or not os.path.exists(upload.file_path):
        raise HTTPException(status_code=404, detail="Uploaded file not found on disk")
    
    try:
        # Generate unique session ID
        session_id = str(uuid.uuid4())
        
        # Load CSV from stored file path to get hospital count
        csv_path = upload.file_path
        df = pd.read_csv(csv_path, on_bad_lines='skip')
        hospitals = group_doctors_by_hospital(df)
        
        # Create validation session
        validation_session = ValidationSession(
            upload_id=request.upload_id,
            session_id=session_id,
            total_hospitals=len(hospitals),
            completed_hospitals=0,
            status="in_progress",
            status_message="Initializing..."
        )
        db.add(validation_session)
        db.commit()
        db.refresh(validation_session)
        
        # Create outputs directory if it doesn't exist
        outputs_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'outputs')
        os.makedirs(outputs_dir, exist_ok=True)
        
        # Output CSV path with unique name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_csv = os.path.join(outputs_dir, f"validation_results_{timestamp}.csv")
        
        # Start background validation
        background_tasks.add_task(run_incremental_validation, session_id, csv_path, output_csv)
        
        return {
            "message": "Incremental validation started",
            "session_id": session_id,
            "total_hospitals": len(hospitals)
        }
        
    except Exception as e:
        print(f"Error starting incremental validation: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/validation/progress/{session_id}")
async def get_validation_progress(session_id: str, db: Session = Depends(get_db)):
    """Get real-time validation progress for a session"""
    session = db.query(ValidationSession).filter(ValidationSession.session_id == session_id).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    progress_percentage = 0
    if session.total_hospitals > 0:
        progress_percentage = int((session.completed_hospitals / session.total_hospitals) * 100)
    
    return {
        "session_id": session.session_id,
        "status": session.status,
        "status_message": session.status_message,
        "progress_percentage": progress_percentage,
        "total_hospitals": session.total_hospitals,
        "completed_hospitals": session.completed_hospitals,
        "current_hospital": session.current_hospital,
        "total_records": session.total_records,
        "verified_count": session.verified_count,
        "updated_count": session.updated_count,
        "needs_review_count": session.needs_review_count,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "completed_at": session.completed_at.isoformat() if session.completed_at else None
    }

@router.get("/validation/status")
async def get_validation_status(
    status: str = None,
    search: str = None,
    skip: int = 0,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """Get validation results with filters and pagination"""
    query = db.query(Provider)
    
    if status and status != "All":
        query = query.filter(Provider.status.contains(status.lower()))
    
    if search:
        query = query.filter(Provider.doctor_name.contains(search))
    
    total = query.count()
    providers = query.offset(skip).limit(limit).all()
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "data": [
            {
                "id": p.id,
                "provider_name": p.doctor_name,
                "hospital": p.hospital_name,
                "status": p.status,
                "confidence_score": p.confidence_score,
                "flags": p.reason if "not found" in p.reason or "mismatch" in p.reason else "",
                "specialization": p.specialization,
                "phone_number": p.phone_number
            }
            for p in providers
        ]
    }

@router.get("/validation/{provider_id}")
async def get_provider_details(provider_id: int, db: Session = Depends(get_db)):
    """Get detailed comparison for a provider"""
    provider = db.query(Provider).filter(Provider.id == provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    
    # Parse reason to extract old vs new data
    # Default: Original matches current provider state (assuming no change unless noted)
    original = {
        "name": provider.doctor_name,
        "phone": provider.phone_number or "",
        "address": provider.address,
        "npi": provider.license_number or "",
        "education": provider.qualification or "",
        "specialties": provider.specialization or ""
    }
    
    validated = original.copy()
    
    # Parse reason for updates
    if provider.reason and "Updated:" in provider.reason:
        try:
             
             update_part = provider.reason.split("Updated: ", 1)[1]
             pattern = r"(\w+)\s*\[(.*?)\s*→\s*(.*?)\]"
             matches = re.finditer(pattern, update_part)
             
             field_map = {
                 "phone": "phone",
                 "phone_number": "phone", 
                 "specialization": "specialties",
                 "qualification": "education",
                 "license_number": "npi"
             }
        
             for match in matches:
                 field_name = match.group(1)
                 old_val = match.group(2).strip()
                 
                 key = field_map.get(field_name, field_name)
                 
                 if key in original:
                     original[key] = old_val
                     
        except Exception as e:
            print(f"Error parsing update reason: {e}")

    return {
        "original": original,
        "validated": validated,
        "status": provider.status,
        "reason": provider.reason
    }

@router.put("/validation/{provider_id}/accept")
async def accept_changes(provider_id: int, db: Session = Depends(get_db)):
    """Accept validated changes"""
    provider = db.query(Provider).filter(Provider.id == provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    
    provider.status = "verified"
    db.commit()
    
    return {"message": "Changes accepted", "provider_id": provider_id}

@router.put("/validation/{provider_id}/reject")
async def reject_changes(provider_id: int, db: Session = Depends(get_db)):
    """Reject validated changes"""
    provider = db.query(Provider).filter(Provider.id == provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    
    provider.status = "rejected"
    db.commit()
    
    return {"message": "Changes rejected", "provider_id": provider_id}

@router.get("/dashboard/stats")
async def get_dashboard_stats(db: Session = Depends(get_db)):
    """Get dashboard statistics"""
    total_providers = db.query(Provider).count()
    validated_providers = db.query(Provider).filter(Provider.status == "verified").count()
    errors_detected = db.query(Provider).filter(Provider.status.contains("human verification")).count()
    flagged_records = db.query(Provider).filter(Provider.status == "updated details").count()
    
    return {
        "total_providers": total_providers,
        "validated_providers": validated_providers,
        "errors_detected": errors_detected,
        "flagged_records": flagged_records
    }

@router.get("/dashboard/trends")
async def get_error_trends(db: Session = Depends(get_db)):
    """Get error trends over time"""
    from sqlalchemy import func, extract
    from datetime import datetime, timedelta
    
    # Get data from last 6 weeks
    six_weeks_ago = datetime.utcnow() - timedelta(weeks=6)
    
    # Query providers with errors grouped by week
    providers_by_week = db.query(
        func.strftime('%Y-%W', Provider.created_at).label('week'),
        func.count(Provider.id).label('count')
    ).filter(
        Provider.created_at >= six_weeks_ago,
        Provider.status.contains('human verification')
    ).group_by('week').order_by('week').all()
    
    # Format response
    weeks = []
    counts = []
    
    for week, count in providers_by_week:
        weeks.append(f"Week {week.split('-')[1]}")
        counts.append(count)
    
    # If no data, return empty arrays
    if not weeks:
        return {
            "labels": ["Week 1", "Week 2", "Week 3", "Week 4", "Week 5", "Week 6"],
            "data": [0, 0, 0, 0, 0, 0]
        }
    
    return {
        "labels": weeks[-6:] if len(weeks) > 6 else weeks,  # Last 6 weeks
        "data": counts[-6:] if len(counts) > 6 else counts
    }

@router.get("/uploads")
async def get_upload_history(db: Session = Depends(get_db)):
    """Get upload history"""
    uploads = db.query(UploadHistory).order_by(UploadHistory.uploaded_at.desc()).limit(10).all()
    
    return [
        {
            "id": u.id,
            "filename": u.filename,
            "type": u.file_type,
            "status": u.status,
            "timestamp": u.uploaded_at.strftime("%Y-%m-%d %H:%M"),
            "record_count": u.record_count
        }
        for u in uploads
    ]

@router.get("/uploaded-data/{upload_id}")
async def get_uploaded_data(upload_id: int, db: Session = Depends(get_db)):
    """Get the contents of an uploaded CSV file"""
    upload = db.query(UploadHistory).filter(UploadHistory.id == upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    
    if not upload.file_path or not os.path.exists(upload.file_path):
        raise HTTPException(status_code=404, detail="Uploaded file not found on disk")
    
    try:
        # Read CSV file
        df = pd.read_csv(upload.file_path)
        
        # Convert to list of dictionaries
        data = df.to_dict('records')
        
        return {
            "upload_id": upload.id,
            "filename": upload.filename,
            "uploaded_at": upload.uploaded_at.isoformat(),
            "record_count": len(data),
            "columns": list(df.columns),
            "data": data
        }
    except Exception as e:
        print(f"Error reading uploaded file: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


import sys
import os
import pandas as pd
from sqlalchemy.orm import Session
from api.routes import get_db, Provider  # Adjust import based on your structure
from database import SessionLocal

# Add parent directory to path to allow imports if run directly
sys.path.insert(0, os.path.dirname(__file__))

def sync_csv_to_db(csv_file_path):
    print(f"Reading CSV from: {csv_file_path}")
    
    try:
        df = pd.read_csv(csv_file_path)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return

    db = SessionLocal()
    
    updated_count = 0
    not_found_count = 0
    
    try:
        for index, row in df.iterrows():
            hospital_name = row.get('hospital_name')
            doctor_name = row.get('doctor_name')
            
            if not hospital_name or not doctor_name:
                continue
                
            # Clean names for matching
            hospital_name = str(hospital_name).strip()
            doctor_name = str(doctor_name).strip()

            print(f"Processing: {doctor_name} at {hospital_name}")

            # Find provider in DB
            provider = db.query(Provider).filter(
                Provider.hospital_name == hospital_name,
                Provider.doctor_name == doctor_name
            ).first()
            
            if provider:
                # Update fields
                provider.status = str(row.get('status', provider.status))
                provider.reason = str(row.get('reason', provider.reason))
                provider.phone_number = str(row.get('phone_number', provider.phone_number))
                provider.specialization = str(row.get('specialization', provider.specialization))
                provider.qualification = str(row.get('qualification', provider.qualification))
                provider.license_number = str(row.get('license_number', provider.license_number))
                
                # Handle confidence score separately to ensure float
                conf_score = row.get('confidence_score')
                if pd.notna(conf_score) and conf_score != '':
                   try:
                       provider.confidence_score = float(conf_score)
                   except ValueError:
                       pass # Keep existing if invalid

                updated_count += 1
                print(f"  -> Updated")
            else:
                not_found_count += 1
                print(f"  -> Not found in DB")
        
        db.commit()
        print("-" * 30)
        print(f"Sync Complete.")
        print(f"Updated: {updated_count}")
        print(f"Not Found/Skipped: {not_found_count}")
        
    except Exception as e:
        print(f"Error during sync: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python sync_csv_to_db.py <path_to_csv>")
        sys.exit(1)
    
    csv_path = sys.argv[1]
    if not os.path.exists(csv_path):
        print(f"File not found: {csv_path}")
        sys.exit(1)
        
    sync_csv_to_db(csv_path)

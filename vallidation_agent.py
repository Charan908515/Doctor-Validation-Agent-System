from scraping import main as scrape_hospital
import csv
import json
import re
import sys
import asyncio
from pathlib import Path
from typing import Dict, List, Union, Any
import logging
import pandas as pd

# Fix for Windows asyncio SSL error - needed for browser automation
#if sys.platform == 'win32':
#    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def _normalize_text(s: Union[str, None]) -> str:
    """Normalize text for comparison."""
    if s is None or pd.isna(s):
        return ""
    s = str(s).strip().lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _normalize_phone(s: Union[str, None]) -> str:
    """Normalize phone number to last 10 digits."""
    if s is None or pd.isna(s):
        return ""
    digits = re.sub(r"[^\d]", "", str(s))
    if len(digits) > 10:
        digits = digits[-10:]
    return digits


def _fuzzy_name_match(n1: str, n2: str) -> bool:
    """
    Fuzzy match for doctor names with support for:
    - Token matching (order independent)
    - Initial matching (e.g., "S" matches "Sharma")
    - "Dr." prefix handling
    """
    if not n1 and not n2:
        return True
    if not n1 or not n2:
        return False
        
    def clean_tokens(text):
        t = str(text).lower().strip()
        # Remove "Dr." prefix
        if t.startswith("dr."):
            t = t[3:]
        elif t.startswith("dr "):
            t = t[3:]
        t = re.sub(r"[^\w\s]", " ", t)
        return [w for w in t.split() if w]

    tokens1 = clean_tokens(n1)
    tokens2 = clean_tokens(n2)
    
    if not tokens1 or not tokens2:
        return False
        
    # Use the longer list as reference
    if len(tokens1) <= len(tokens2):
        reference = tokens2
        candidate = tokens1
    else:
        reference = tokens1
        candidate = tokens2
    
    used_indices = set()
    
    for c_tok in candidate:
        found_match = False
        for i, r_tok in enumerate(reference):
            if i in used_indices:
                continue
            
            # Exact match or initial match
            is_same = (c_tok == r_tok)
            is_initial = (len(c_tok) == 1 and r_tok.startswith(c_tok)) or \
                         (len(r_tok) == 1 and c_tok.startswith(r_tok))
            
            if is_same or is_initial:
                used_indices.add(i)
                found_match = True
                break
        
        if not found_match:
            return False
            
    return True


def group_doctors_by_hospital(df: pd.DataFrame) -> Dict[str, List[Dict]]:
    """
    Group doctors by hospital name and address combination.
    
    Returns:
        Dictionary with keys as "hospital_name||address" and values as list of doctor records
    """
    hospitals = {}
    
    for idx, row in df.iterrows():
        hospital_name = str(row.get("hospital_name", "")).strip()
        address = str(row.get("address", "")).strip()
        
        # Create unique key for hospital
        hospital_key = f"{hospital_name}||{address}"
        
        if hospital_key not in hospitals:
            hospitals[hospital_key] = []
        
        # Convert row to dict
        doctor_record = {
            "hospital_name": hospital_name,
            "address": address,
            "doctor_name": str(row.get("doctor_name", "")).strip(),
            "specialization": str(row.get("specialization", "") or row.get("specialty", "") or row.get("speciality", "")).strip(),
            "qualification": str(row.get("qualification", "")).strip(),
            "phone_number": str(row.get("phone_number", "") or row.get("phone", "")).strip(),
            "license_number": str(row.get("license_number", "") or row.get("license", "")).strip()
        }
        
        hospitals[hospital_key].append(doctor_record)
    
    return hospitals


def compare_doctor_data(csv_doctor: Dict, scraped_doctors: List[Dict]) -> Dict:
    """
    Compare a single CSV doctor record against scraped doctors list.
    
    Returns:
        Dictionary with status, reason, and updated data fields
    """
    csv_name = csv_doctor.get("doctor_name", "")
    csv_phone = _normalize_phone(csv_doctor.get("phone_number", ""))
    csv_spec = _normalize_text(csv_doctor.get("specialization", ""))
    csv_qual = _normalize_text(csv_doctor.get("qualification", ""))
    
    # Try to find doctor in scraped list using fuzzy matching
    found_doctor = None
    for scraped in scraped_doctors:
        scraped_name = scraped.get("full_name", "")
        if _fuzzy_name_match(csv_name, scraped_name):
            found_doctor = scraped
            break
    
    # Rule 2: Doctor not found in scraped list
    if not found_doctor:
        return {
            **csv_doctor,  # Keep all original data
            "status": "human verification needed",
            "reason": f"Doctor '{csv_name}' not found on hospital website"
        }
    
    # Doctor found - compare details
    scraped_phone = _normalize_phone(found_doctor.get("phone_number", ""))
    scraped_spec = _normalize_text(found_doctor.get("specialization", ""))
    scraped_qual = _normalize_text(found_doctor.get("qualification", ""))
    
    phone_match = (csv_phone == scraped_phone) if (csv_phone and scraped_phone) else True
    spec_match = (csv_spec == scraped_spec) if (csv_spec and scraped_spec) else True
    qual_match = (csv_qual == scraped_qual) if (csv_qual and scraped_qual) else True
    
    # Rule 4: All details match
    if phone_match and spec_match and qual_match:
        return {
            **csv_doctor,
            "status": "verified",
            "reason": "All details match website data"
        }
    
    # Rule 3: Some details don't match - update with scraped data
    updates = []
    result = csv_doctor.copy()
    
    if not phone_match and scraped_phone:
        updates.append(f"phone [{csv_doctor.get('phone_number', 'N/A')} → {found_doctor.get('phone_number', 'N/A')}]")
        result["phone_number"] = found_doctor.get("phone_number", csv_doctor.get("phone_number"))
    
    if not spec_match and scraped_spec:
        updates.append(f"specialization [{csv_doctor.get('specialization', 'N/A')} → {found_doctor.get('specialization', 'N/A')}]")
        result["specialization"] = found_doctor.get("specialization", csv_doctor.get("specialization"))
    
    if not qual_match and scraped_qual:
        updates.append(f"qualification [{csv_doctor.get('qualification', 'N/A')} → {found_doctor.get('qualification', 'N/A')}]")
        result["qualification"] = found_doctor.get("qualification", csv_doctor.get("qualification"))
    
    reason = "Updated: " + ", ".join(updates) if updates else "Data verified and updated"
    
    return {
        **result,
        "status": "updated details",
        "reason": reason
    }


def validate_hospital_doctors(hospital_name: str, address: str, csv_doctors: List[Dict], status_callback=None) -> List[Dict]:
    """
    Validate all doctors for a single hospital.
    
    Args:
        hospital_name: Name of the hospital
        address: Full address of the hospital
        csv_doctors: List of doctor records from CSV for this hospital
        status_callback: Optional callback(message) for status updates
        
    Returns:
        List of validation results with status and reason
    """
    print(f"\n{'='*80}")
    print(f"Processing Hospital: {hospital_name}")
    print(f"Address: {address}")
    print(f"CSV Doctors Count: {len(csv_doctors)}")
    print(f"{'='*80}")
    
    if status_callback:
        status_callback(f"Finding address for {hospital_name}...")
    
    # Call scraping agent
    try:
        scrape_result = scrape_hospital(hospital_name, address)
    except Exception as e:
        logging.error(f"Error scraping hospital {hospital_name}: {e}")
        scrape_result = {"verified": False, "error": str(e)}
    
    # Rule 1: Hospital address not verified
    if not scrape_result.get("verified", False):
        error_msg = scrape_result.get("error", "Address verification failed")
        print(f"⚠️  Hospital not verified: {error_msg}")
        
        results = []
        for doctor in csv_doctors:
            results.append({
                **doctor,
                "status": "human verification needed",
                "reason": f"Hospital address not found via Mappls/Google API - {error_msg}"
            })
        return results
    
    # Hospital verified - compare doctors
    scraped_doctors = scrape_result.get("doctors", [])
    print(f"✓ Hospital verified! Found {len(scraped_doctors)} doctors on website")
    
    if status_callback:
        status_callback(f"Verifying {len(csv_doctors)} doctors against {len(scraped_doctors)} found records...")
    
    results = []
    for csv_doctor in csv_doctors:
        result = compare_doctor_data(csv_doctor, scraped_doctors)
        results.append(result)
        
        # Log result
        status = result.get("status", "unknown")
        doctor_name = result.get("doctor_name", "Unknown")
        if status == "verified":
            print(f"  ✓ {doctor_name}: Verified")
        elif status == "updated details":
            print(f"  ↻ {doctor_name}: Updated")
        else:
            print(f"  ⚠ {doctor_name}: Needs review")
    
    return results


def write_validation_results(results: List[Dict], output_file: str):
    """
    Write validation results to CSV file.
    
    Args:
        results: List of validation result dictionaries
        output_file: Path to output CSV file
    """
    if not results:
        logging.warning("No results to write")
        return
    
    # Define output columns
    columns = [
        "hospital_name",
        "address", 
        "doctor_name",
        "specialization",
        "qualification",
        "phone_number",
        "license_number",
        "status",
        "reason"
    ]
    
    # Create DataFrame
    df = pd.DataFrame(results)
    
    # Ensure all columns exist
    for col in columns:
        if col not in df.columns:
            df[col] = ""
    
    # Reorder columns
    df = df[columns]
    
    # Write to CSV
    df.to_csv(output_file, index=False, encoding='utf-8')
    print(f"\n✓ Validation results written to: {output_file}")
    
    # Print summary statistics
    status_counts = df['status'].value_counts()
    print(f"\nSummary:")
    print(f"  Total records: {len(df)}")
    for status, count in status_counts.items():
        print(f"  {status}: {count}")


def validate_and_write_incremental(
    input_csv: str,
    output_csv: str,
    progress_callback=None,
    db_callback=None
):
    """
    Validate hospitals incrementally with immediate writes.
    
    Args:
        input_csv: Path to input CSV file
        output_csv: Path to output CSV file
        progress_callback: Optional callback(hospital_idx, total, hospital_name, status, results)
        db_callback: Optional callback(results) to update database
        
    Returns:
        Dictionary with summary statistics
    """
    print("="*80)
    print(" DOCTOR VALIDATION AGENT (INCREMENTAL MODE)")
    print("="*80)
    
    # Load CSV
    try:
        df = pd.read_csv(input_csv, on_bad_lines='skip')
        print(f"\n✓ Loaded {len(df)} records from {input_csv}")
    except Exception as e:
        logging.error(f"Error loading CSV: {e}")
        return {"error": str(e)}
    
    # Group by hospital
    hospitals = group_doctors_by_hospital(df)
    total_hospitals = len(hospitals)
    print(f"✓ Grouped into {total_hospitals} unique hospitals")
    
    # Initialize output file with headers
    output_path = Path(output_csv)
    if output_path.exists():
        output_path.unlink()  # Remove old file
    
    columns = [
        "hospital_name", "address", "doctor_name", "specialization",
        "qualification", "phone_number", "license_number", "status", "reason"
    ]
    
    # Create empty CSV with headers
    pd.DataFrame(columns=columns).to_csv(output_csv, index=False, encoding='utf-8')
    
    # Track statistics
    all_stats = {
        "total_processed": 0,
        "verified": 0,
        "updated": 0,
        "needs_review": 0,
        "hospitals_completed": 0
    }
    
    # Validate each hospital incrementally
    for idx, (hospital_key, csv_doctors) in enumerate(hospitals.items(), 1):
        hospital_name, address = hospital_key.split("||")
        
        print(f"\n[{idx}/{total_hospitals}] Processing: {hospital_name}")
        
        try:
            # Pass a status callback that updates the progress
            def status_cb(msg):
                if progress_callback:
                     progress_callback(
                        hospital_idx=idx,
                        total_hospitals=total_hospitals,
                        hospital_name=hospital_name,
                        status="in_progress",
                        results=[],
                        stats=all_stats.copy(),
                        status_message=msg
                    )

            # Scrape and validate
            results = validate_hospital_doctors(hospital_name, address, csv_doctors, status_callback=status_cb)
            
            # Update statistics
            all_stats["total_processed"] += len(results)
            all_stats["verified"] += sum(1 for r in results if r.get("status") == "verified")
            all_stats["updated"] += sum(1 for r in results if r.get("status") == "updated details")
            all_stats["needs_review"] += sum(1 for r in results if r.get("status") == "human verification needed")
            all_stats["hospitals_completed"] = idx
            
            # Immediately append to CSV
            df_results = pd.DataFrame(results)
            for col in columns:
                if col not in df_results.columns:
                    df_results[col] = ""
            df_results = df_results[columns]
            
            # Append to existing CSV
            df_results.to_csv(output_csv, mode='a', header=False, index=False, encoding='utf-8')
            
            print(f"  ✓ Written {len(results)} results to CSV")
            
            # Call database callback if provided
            if db_callback:
                try:
                    db_callback(results)
                    print(f"  ✓ Updated database")
                except Exception as e:
                    logging.error(f"Database callback error: {e}")
            
            # Call progress callback if provided
            if progress_callback:
                try:
                    progress_callback(
                        hospital_idx=idx,
                        total_hospitals=total_hospitals,
                        hospital_name=hospital_name,
                        status="completed",
                        results=results,
                        stats=all_stats.copy(),
                        status_message=f"Completed validation for {hospital_name}"
                    )
                except Exception as e:
                    logging.error(f"Progress callback error: {e}")
                    
        except Exception as e:
            logging.error(f"Error validating hospital {hospital_name}: {e}")
            
            # Add error records
            error_results = []
            for doctor in csv_doctors:
                error_results.append({
                    **doctor,
                    "status": "human verification needed",
                    "reason": f"Validation error: {str(e)}"
                })
            
            # Write error records
            df_error = pd.DataFrame(error_results)
            for col in columns:
                if col not in df_error.columns:
                    df_error[col] = ""
            df_error = df_error[columns]
            df_error.to_csv(output_csv, mode='a', header=False, index=False, encoding='utf-8')
            
            all_stats["total_processed"] += len(error_results)
            all_stats["needs_review"] += len(error_results)
            all_stats["hospitals_completed"] = idx
            
            # Call callbacks even on error
            if db_callback:
                try:
                    db_callback(error_results)
                except Exception as e:
                    logging.error(f"Database callback error: {e}")
            
            if progress_callback:
                try:
                    progress_callback(
                        hospital_idx=idx,
                        total_hospitals=total_hospitals,
                        hospital_name=hospital_name,
                        status="error",
                        results=error_results,
                        stats=all_stats.copy()
                    )
                except Exception as e:
                    logging.error(f"Progress callback error: {e}")
    
    print(f"\n{'='*80}")
    print(" INCREMENTAL VALIDATION COMPLETE")
    print(f"{'='*80}")
    print(f"\nSummary:")
    print(f"  Total records: {all_stats['total_processed']}")
    print(f"  Verified: {all_stats['verified']}")
    print(f"  Updated: {all_stats['updated']}")
    print(f"  Needs review: {all_stats['needs_review']}")
    
    return all_stats


def main(input_csv: str = "testing_data.csv", output_csv: str = "out.csv"):
    """
    Main validation workflow (batch mode - processes all at once).
    
    Args:
        input_csv: Path to input CSV file
        output_csv: Path to output CSV file
    """
    print("="*80)
    print(" DOCTOR VALIDATION AGENT")
    print("="*80)
    
    # Load CSV
    try:
        df = pd.read_csv(input_csv, on_bad_lines='skip')
        print(f"\n✓ Loaded {len(df)} records from {input_csv}")
    except Exception as e:
        logging.error(f"Error loading CSV: {e}")
        return
    
    # Group by hospital
    hospitals = group_doctors_by_hospital(df)
    print(f"✓ Grouped into {len(hospitals)} unique hospitals")
    
    # Validate each hospital
    all_results = []
    for idx, (hospital_key, csv_doctors) in enumerate(hospitals.items(), 1):
        hospital_name, address = hospital_key.split("||")
        
        print(f"\n[{idx}/{len(hospitals)}] Processing: {hospital_name}")
        
        try:
            results = validate_hospital_doctors(hospital_name, address, csv_doctors)
            all_results.extend(results)
        except Exception as e:
            logging.error(f"Error validating hospital {hospital_name}: {e}")
            # Add error records
            for doctor in csv_doctors:
                all_results.append({
                    **doctor,
                    "status": "human verification needed",
                    "reason": f"Validation error: {str(e)}"
                })
    
    # Write results
    write_validation_results(all_results, output_csv)
    
    print(f"\n{'='*80}")
    print(" VALIDATION COMPLETE")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
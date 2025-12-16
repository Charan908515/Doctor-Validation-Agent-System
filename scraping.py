import requests
import json
import sys
import os
import re
import dotenv
from difflib import SequenceMatcher
dotenv.load_dotenv(os.path.join(os.path.dirname(__file__), '../config/.env'))

current_dir = os.path.dirname(os.path.abspath(__file__))
browser_agent_path = os.path.join(current_dir, "browser_agent")
if browser_agent_path not in sys.path:
    sys.path.append(browser_agent_path)

try:
    from new_orchestation import run_agent
except ImportError:
    print(f"Error: Could not import 'run_agent' from {browser_agent_path}")
    sys.exit(1)


def is_address_in_india(address):
    keywords = ["india", "andhra", "pradesh", "telangana", "delhi", "mumbai", "karnataka", "tamil", "nadu", "kerala", "bengaluru", "chennai", "hyderabad", "kurnool"]
    return any(k in address.lower() for k in keywords)


def get_mappls_token(client_id, client_secret):
    url = "https://outpost.mapmyindia.com/api/security/oauth/token"
    data = {"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret}
    try:
        response = requests.post(url, data=data)
        response.raise_for_status()
        return response.json().get("access_token")
    except Exception as e:
        print(f"   [Mappls Auth Error]: {e}")
        return None

def strict_verify_address(user_input, result_name, result_address):
    user_input = user_input.lower()
    result_full = f"{result_name} {result_address}".lower()
    user_pincode = re.search(r'\b\d{6}\b', user_input)
    result_pincode = re.search(r'\b\d{6}\b', result_full)
    
    if user_pincode and result_pincode:
        if user_pincode.group() != result_pincode.group():
            print(f"   Pincode Mismatch! Input: {user_pincode.group()} vs Found: {result_pincode.group()}")
            return False, 0.0

    ignore_words = {"hospital", "clinic", "road", "street", "st", "dr", "doctor", "lane", "opp", "near", "beside", "andhra", "pradesh", "india"}
    user_tokens = [w for w in re.split(r'\W+', user_input) if len(w) > 3 and w not in ignore_words]
    
    matched_count = 0
    total_tokens = len(user_tokens)
    
    if total_tokens == 0:
        return True, 100.0 
        
    for token in user_tokens:
        if token in result_full:
            matched_count += 1
            
    match_percentage = (matched_count / total_tokens) * 100
    print(f"   🔍 Match Confidence: {match_percentage:.1f}% ({matched_count}/{total_tokens} keywords found)")

    if match_percentage < 40: 
        return False, match_percentage
        
    return True, match_percentage

def strict_verify_location_with_mappls(address, client_id, client_secret):
    print(f"\n STAGE 1: Checking Mappls (MapmyIndia) API...")
    
    token = get_mappls_token(client_id, client_secret)
    if not token:
        return {"verified": False, "source": "Mappls", "details": "Auth Failed", "address_confidence_score": 0.0}

    url = "https://atlas.mappls.com/api/places/textsearch/json"
    params = { "query": address }
    headers = { "Authorization": f"Bearer {token}", "User-Agent": "ValidationAgent/1.0" }

    try:
        response = requests.get(url, params=params, headers=headers)
        data = response.json()
        
        locations = data.get("suggestedLocations", [])
        if not locations:
            return {"verified": False, "source": "Mappls", "details": "No results found", "address_confidence_score": 0.0}

        medical_keywords = ["Hospital", "Clinic", "Medical", "Doctor", "Dr.", "Nursing", "Scan", "Lab", "Pharmacy"]
        best_match = None
        confidence_score = 0.0
        
        print(f"   found {len(locations)} potential matches. Filtering for exact healthcare match...")

        for loc in locations:
            name = loc.get("placeName", "")
            addr = loc.get("placeAddress", "")
            category_codes = loc.get("keywords", []) 
            
            is_health_code = any(code.startswith("HLT") or code in ["LABRAD", "HSPGEN"] for code in category_codes)
            name_is_medical = any(term.lower() in name.lower() for term in medical_keywords)

            if is_health_code or name_is_medical:
                is_match, conf_score = strict_verify_address(address, name, addr)
                
                if is_match:
                    best_match = loc
                    confidence_score = conf_score
                    print(f"   Match Found & Verified: {name}")
                    break 
                else:
                    print(f"   Rejecting nearby candidate: {name} (Address mismatch)")
        
        if not best_match:
            return {"verified": False, "source": "Mappls", "details": "Hospital not found at this exact location (Nearby results rejected)", "address_confidence_score": 0.0}

        name = best_match.get("placeName", "")
        loc_address = best_match.get("placeAddress", "")
        full_result = f"{name}, {loc_address}"
        
        return {
            "verified": True, 
            "source": "Mappls (Strict)", 
            "name": full_result,
            "type": "Healthcare",
            "raw_data": best_match,
            "address_confidence_score": confidence_score
        }
            
    except Exception as e:
        print(f"   [Mappls Search Error]: {e}")

    return {"verified": False, "source": "Mappls", "details": "Error", "address_confidence_score": 0.0}

def verify_location_with_google(address, api_key):
    print(f"\n STAGE 1: Checking Google Maps API (Global)...")
    
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = { "query": address, "key": api_key }
    
    try:
        response = requests.get(url, params=params)
        data = response.json()
        
        if data.get("status") != "OK" or not data.get("results"):
            return {"verified": False, "source": "GoogleAPI", "details": data.get("error_message", "No results")}
        
        results = data["results"]
        medical_types = ["hospital", "doctor", "health", "pharmacy", "physiotherapist", "dentist"]
        best_match = None
        
        for place in results:
            place_types = place.get("types", [])
            place_name = place.get("name", "")
            
            if any(t in place_types for t in medical_types) or "hospital" in place_name.lower() or "clinic" in place_name.lower():
                best_match = place
                print(f" Match Found: {place_name} (Type: {place_types})")
                break
        
        if not best_match:
            print("  No strict medical match found. Using top result.")
            best_match = results[0]

        return {
            "verified": True,
            "source": "GoogleAPI",
            "name": best_match.get("name"),
            "full_address": best_match.get("formatted_address"),
            "place_id": best_match.get("place_id"),
            "website": None 
        }

    except Exception as e:
        print(f"   [Google API Error]: {e}")
        return {"verified": False, "source": "GoogleAPI", "details": str(e)}


def extract_json_from_markdown(text: str) -> str:
    pattern = r'```(?:json)?\s*\n?(.*?)\n?```'
    match = re.search(pattern, text, re.DOTALL)
    
    if match:
        return match.group(1).strip()
    
    return text.strip()


def main(hospital_name: str, hospital_address: str):
    """
    Main function to scrape doctor data from a hospital website.
    
    Args:
        hospital_name: Name of the hospital
        hospital_address: Full address of the hospital
        
    Returns:
        Dictionary with:
        - verified: Boolean (True if hospital found and scraped)
        - hospital_name: Verified hospital name
        - hospital_address: Verified hospital address
        - doctors: List of doctor dictionaries
        - address_confidence_score: Float confidence score
        - error: String (if verification failed)
    """
    print("="*60)
    print(" HOSPITAL & DOCTOR DATA SCRAPING SYSTEM")
    print("="*60)
    
    # Combine for full address search
    full_address = f"{hospital_name}, {hospital_address}"
    
    google_key = os.getenv("google_maps_api_key")
    mappls_client_id = os.getenv("mappls_client_id")
    mappls_client_secret = os.getenv("mappls_client_secret")
    location_data = {"verified": False}
    
    # Step 1: Verify hospital location
    if is_address_in_india(full_address):
        if mappls_client_id and mappls_client_secret:
            location_data = strict_verify_location_with_mappls(full_address, mappls_client_id, mappls_client_secret)
        else:
            print(" Address is in India, but MAPPLS keys are missing. Trying Google...")
            if google_key:
                location_data = verify_location_with_google(full_address, google_key)
            else:
                print(" No API keys available for India.")
    else:
        if google_key:
            location_data = verify_location_with_google(full_address, google_key)
        else:
            print(" Address is outside India, but GOOGLE_MAPS_API_KEY is missing.")

    if not location_data.get("verified"):
        print(f" FACILITY NOT FOUND. Address verification failed.")
        return {
            "verified": False,
            "hospital_name": hospital_name,
            "hospital_address": hospital_address,
            "doctors": [],
            "address_confidence_score": 0.0,
            "error": "Hospital address not found via Mappls/Google Maps API"
        }
    
    # Step 2: Verify hospital name match
    raw_place_name = location_data.get("name", "") or location_data.get("raw_data", {}).get("placeName", "")
    found_hospital_name = raw_place_name.split(",")[0].strip() if raw_place_name else ""

    def normalize(n: str) -> str:
        n = n or ""
        n = re.sub(r"\b(hospital|clinic|medical|centre|center|institute|institute\.|nursing)\b", "", n, flags=re.I)
        n = re.sub(r"[^\w\s]", " ", n)
        n = re.sub(r"\s+", " ", n).strip()
        return n.lower()

    norm_user = normalize(hospital_name)
    norm_found = normalize(found_hospital_name)

    print(f"  Verifying Name: User='{hospital_name}' vs Found='{found_hospital_name}'")

    similarity = SequenceMatcher(None, norm_user, norm_found).ratio() if norm_user and norm_found else 0.0
    user_tokens = set(re.findall(r'\w+', norm_user))
    found_tokens = set(re.findall(r'\w+', norm_found))
    common_tokens = user_tokens.intersection(found_tokens)

    if similarity < 0.5 and len(common_tokens) < 1:
        print(f" Hospital Name mismatch (Similarity: {similarity:.2f}). Needs verification.")
        return {
            "verified": False,
            "hospital_name": hospital_name,
            "hospital_address": hospital_address,
            "doctors": [],
            "address_confidence_score": location_data.get("address_confidence_score", 0.0),
            "error": f"Hospital name mismatch: expected '{hospital_name}' but found '{found_hospital_name}'"
        }

    print(f"\n FACILITY FOUND via {location_data['source']}!")
    print(f"   Name: {found_hospital_name}")
    
    verified_address = location_data.get("raw_data", {}).get("placeAddress", "") or location_data.get("full_address", hospital_address)
    
    # Step 3: Scrape doctors using run_agent
    print(f"\n PHASE 2: Scraping doctors from hospital website...")
    
    try:
        agent_result = run_agent(hospital_name, hospital_address)
        
        # Handle error cases
        if isinstance(agent_result, dict) and "error" in agent_result:
            print(f" Agent error: {agent_result['error']}")
            return {
                "verified": True,
                "hospital_name": found_hospital_name,
                "hospital_address": verified_address,
                "doctors": [],
                "address_confidence_score": location_data.get("address_confidence_score", 0.0),
                "error": f"Failed to scrape doctors: {agent_result['error']}"
            }
        
        # Extract output
        output = agent_result.get("output", "")
        
        # Try to parse as JSON
        try:
            # Extract from markdown if needed
            json_str = extract_json_from_markdown(str(output))
            doctors_data = json.loads(json_str)
            
            # Handle different return formats
            if isinstance(doctors_data, dict):
                # If it's a dict with a 'doctors' key
                if "doctors" in doctors_data:
                    doctors_list = doctors_data["doctors"]
                # If it's a single doctor object
                elif "full_name" in doctors_data or "name" in doctors_data:
                    doctors_list = [doctors_data]
                else:
                    doctors_list = []
            elif isinstance(doctors_data, list):
                doctors_list = doctors_data
            else:
                doctors_list = []
            
            # Normalize doctor data
            normalized_doctors = []
            for doc in doctors_list:
                if isinstance(doc, dict):
                    normalized_doctors.append({
                        "full_name": doc.get("full_name") or doc.get("name") or doc.get("doctor_name", ""),
                        "specialization": doc.get("specialization") or doc.get("specialty") or doc.get("speciality", ""),
                        "qualification": doc.get("qualification") or doc.get("qualifications", ""),
                        "phone_number": doc.get("phone_number") or doc.get("phone") or doc.get("contact", "")
                    })
            
            print(f"\n Successfully scraped {len(normalized_doctors)} doctors")
            
            return {
                "verified": True,
                "hospital_name": found_hospital_name,
                "hospital_address": verified_address,
                "doctors": normalized_doctors,
                "address_confidence_score": location_data.get("address_confidence_score", 0.0)
            }
            
        except json.JSONDecodeError as e:
            print(f" Failed to parse doctor data as JSON: {e}")
            print(f" Raw output: {output[:500]}")
            return {
                "verified": True,
                "hospital_name": found_hospital_name,
                "hospital_address": verified_address,
                "doctors": [],
                "address_confidence_score": location_data.get("address_confidence_score", 0.0),
                "error": f"Failed to parse scraped data: {str(e)}"
            }
            
    except Exception as e:
        print(f" Error during scraping: {e}")
        return {
            "verified": True,
            "hospital_name": found_hospital_name,
            "hospital_address": verified_address,
            "doctors": [],
            "address_confidence_score": location_data.get("address_confidence_score", 0.0),
            "error": f"Scraping failed: {str(e)}"
        }


if __name__ == "__main__":
    # Test with sample data
    """hospital_name = "Sankalpa Super Speciality Hospital"
    hospital_address = "Karakambadi Bazar St, Tata Nagar, Tirupati, Andhra Pradesh 517501"
    
    result = main(hospital_name, hospital_address)
    
    print("\n" + "="*100)
    print(">>> Final Result:")
    print("="*100)
    print(json.dumps(result, indent=2))"""
    from langchain_sambanova import ChatSambaNova
    import os
    import dotenv
    dotenv.load_dotenv(os.path.join(os.path.dirname(__file__), '../config/.env'))
    llm=ChatSambaNova(model_name="gpt-oss-120b",api_key=os.getenv("sambanova1"))
    print(llm.invoke("Hello, how are you?"))

import sys
import os
import time
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import json
import asyncio
import re
import browser_manager

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
from crawl4ai.extraction_strategy import LLMExtractionStrategy
from crawl4ai.async_configs import LLMConfig
from pydantic import BaseModel, Field
from typing import Optional

import dotenv
dotenv.load_dotenv(os.path.join(os.path.dirname(__file__), '../config/.env'))

def get_deepseek_config():
    return LLMConfig(
        provider="ollama/deepseek-r1:8b", 
        api_token="no-token",            
        base_url="http://localhost:11434" 
    )

def extract_json_from_markdown(text: str) -> str:
    """Extract JSON from markdown code blocks or clean DeepSeek <think> tags."""
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
    pattern = r'```(?:json)?\s*\n?(.*?)\n?```'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    
    return text

class Doctor(BaseModel):
    name: str = Field(..., description="Name of the doctor")
    specialty: str = Field(..., description="Specialty or department, e.g. Cardiology")
    qualification: Optional[str] = Field(None, description="Educational qualifications, e.g. MBBS, MD")
    phone_number: Optional[str] = Field(None, description="Phone number or contact number if available")
    experience: Optional[str] = Field(None, description="Years of experience if mentioned")
    profile_url: str = Field(..., description="The URL of this profile page")

class DoctorLink(BaseModel):
    url: str = Field(..., description="The full URL to the individual doctor's profile page.")
    name: str = Field(..., description="The name of the doctor associated with this link.")


def find_doctors_listing_page(hospital_name, address):
    
    from new_orchestation import run_agent
    
    print(f"\n🔍 STEP 1: Finding Doctors Page for {hospital_name}...")
    
    prompt = f"""
    Find the official website for '{hospital_name}' located at '{address}'.
    Navigate to the website and find the section for 'Doctors', 'Specialties', or 'Find a Doctor'.
    
    CRITICAL DECISION:
    1. If the page lists ALL doctors directly (scrollable list), return that URL.
    2. If the page lists DEPARTMENTS (Cardiology, Neurology, etc.) and you must click them to see doctors, 
       extract the URLs of ALL department pages.
       
    OUTPUT FORMAT (JSON):
    {{
        "structure_type": "single_page" or "department_list",
        "urls": ["url1", "url2"...]
    }}
    """
    result = run_agent(prompt)
    
    try:
        data = extract_json_from_markdown(result["output"])
        return json.loads(data)
    except Exception as e:
        print(f"Error parsing agent output: {e}")
        return None

try:
    from config.config import LLMConfig as CentralLLMConfig
except ImportError:
    print("❌ Critical Error: Could not import 'LLMConfig' from 'config.py'.")
    sys.exit(1)

def get_api_key_from_llm(llm_base):
    """
    Safely extracts the API key from the LangChain/SambaNova object
    following the logic in your snippet.
    """
    s_key = llm_base.groq_api_key
    if hasattr(s_key, "get_secret_value"):
        s_key = s_key.get_secret_value()
    return s_key
async def extract_doctor_profile_urls(listing_urls):
    print(f"\n STEP 2: Extracting Doctor Profile URLs using SambaNova...")
    
    doctor_profile_links = set()
    rotation_list = CentralLLMConfig.get_main_llm_with_rotation(start_index=0, provider="groq")
    num_keys = len(rotation_list)

    instruction = """
    Analyze the links on this page. Extract ONLY the URLs that lead to an individual doctor's profile or bio page.
    Ignore links to departments, general pages, or 'book appointment' unless it is the only way to see the profile.
    """

    for i, url in enumerate(listing_urls):
        
        print(f"   ⚡ Scanning: {url}")
        page_success = False
        start_key_idx = i % num_keys
        current_url_rotation = rotation_list[start_key_idx:] + rotation_list[:start_key_idx]

        for idx, (key_name, llm_base) in enumerate(current_url_rotation):
            if page_success: break 

            try:
                print(f"🔑 Trying {key_name}...")
                api_key = get_api_key_from_llm(llm_base)

                if not api_key:
                    print(f"      ⚠️ No API key found for {key_name}, skipping.")
                    continue

                
                """llm_config = CrawlLLMConfig(
                    provider="openai/gpt-oss-120b",
                    base_url="https://api.sambanova.ai/v1",
                    api_token=api_key
                )"""
                llm_config = CrawlLLMConfig(
                    provider="groq/llama-3.3-70b-versatile",
                    api_token=api_key,
                    base_url="https://api.groq.com/openai/v1")
                
                llm_strategy = LLMExtractionStrategy(
                    llm_config=llm_config,
                    schema=DoctorLink.model_json_schema(), 
                    extraction_type="schema",
                    instruction=instruction
                )

                config = CrawlerRunConfig(
                    extraction_strategy=llm_strategy,
                    cache_mode=CacheMode.BYPASS,
                    wait_for="css:body",
                    page_timeout=300000  
                )

                
                async with AsyncWebCrawler() as crawler:
                    result = await crawler.arun(
                        url=url,
                        config=config,
                        js_code="window.scrollTo(0, document.body.scrollHeight);"
                    )

                    if result.success:
                        
                        content = result.extracted_content.replace("```json", "").replace("```", "")
                        try:
                            data = json.loads(content)
                            if isinstance(data, dict): data = [data]
                            
                            count = 0
                            for item in data:
                                link = item.get("url")
                                if link and "http" in link and link not in doctor_profile_links:
                                    doctor_profile_links.add(link)
                                    count += 1
                            
                            print(f"      ✅ Success with {key_name}: Found {count} profiles.")
                            page_success = True 
                            
                        except json.JSONDecodeError:
                            print(f"      ⚠️ JSON Error on {url} with {key_name}. (Trying next key...)")
                            
                    else:
                        print(f"      ❌ Failed with {key_name}: {result.error_message}")
                        
            
            except Exception as e:
                print(f"      ⚠️ Exception with {key_name}: {e}")

        if not page_success:
            print(f"   ❌ CRITICAL: All keys failed for {url}")

    return list(doctor_profile_links)

async def scrape_doctor_details(profile_urls):
    print(f"\n📄 STEP 3: Scraping details for {len(profile_urls)} doctors using SambaNova...")
    
    all_doctors = []
    rotation_list = CentralLLMConfig.get_main_llm_with_rotation(start_index=0, provider="groq")
    num_keys = len(rotation_list)
    
    instruction = "Extract the doctor's name, specialty, qualifications, phone number (if available else search for the hospital number even that not found then give null), and experience from this profile page."

    for i, url in enumerate(profile_urls):
        print(f"   ⚡ Analyzing: {url}")
        
        page_success = False

        start_key_idx = i % num_keys
        current_url_rotation = rotation_list[start_key_idx:] + rotation_list[:start_key_idx]

        for idx, (key_name, llm_base) in enumerate(current_url_rotation):
            if page_success: break

            try:
                api_key = get_api_key_from_llm(llm_base)
                
                if not api_key: continue

                """llm_config = CrawlLLMConfig(
                    provider="openai/gpt-oss-120b",
                    base_url="https://api.sambanova.ai/v1",
                    api_token=api_key
                )"""
                llm_config = CrawlLLMConfig(
                    provider="groq/llama-3.3-70b-versatile",
                    api_token=api_key,
                    base_url="https://api.groq.com/openai/v1")

                llm_strategy = LLMExtractionStrategy(
                    llm_config=llm_config,
                    schema=Doctor.model_json_schema(), 
                    extraction_type="schema",
                    instruction=instruction
                )

                config = CrawlerRunConfig(
                    extraction_strategy=llm_strategy,
                    cache_mode=CacheMode.BYPASS,
                    wait_for="css:body",
                    page_timeout=300000  
                )

                async with AsyncWebCrawler() as crawler:
                    result = await crawler.arun(url=url, config=config)
                    
                    if result.success:
                        content = result.extracted_content.replace("```json", "").replace("```", "")
                        try:
                            data = json.loads(content)
                            if isinstance(data, dict): data = [data]
                            for item in data:
                                item['source_url'] = url
                                print(f"     ✅ Found: {item.get('name')} (via {key_name})")
                            
                            all_doctors.extend(data)
                            page_success = True
                        except json.JSONDecodeError:
                            print(f"     ⚠️ JSON Error with {key_name}.")
                    else:
                        err_msg = result.error_message
                        if "429" in str(err_msg):
                            print(f"     ⚠️ Rate Limit on {key_name}. Rotating...")
                        else:
                            print(f"     ❌ Error on {key_name}: {err_msg}")

            except Exception as e:
                print(f"     ⚠️ Exception on {key_name}: {e}")

        if not page_success:
             print(f"   ❌ CRITICAL: Failed to scrape {url} with any key.")
                
    return all_doctors
if __name__ == "__main__":
  
    
    hospital = "Medicover Hospitals"
    addr = "Visakhapatnam MVP"
    
    
    structure_info = find_doctors_listing_page(hospital, addr)
    
    if not structure_info:
        print("Failed to identify hospital structure.")
        sys.exit()
    structure_info = {
        "urls": [
            "https://www.medicoverhospitals.com/visakhapatnam/visakhapatnam-mvp-doctors-list"
        ]
    }
    listing_pages = structure_info.get("urls", [])
    if isinstance(listing_pages, str):
        listing_pages = [listing_pages]

    print(f"   Found Listing Pages: {listing_pages}")
    doctor_urls = asyncio.run(extract_doctor_profile_urls(listing_pages))
    print(f"\n Found {len(doctor_urls)} unique doctor profiles.")
    if doctor_urls:
        details = asyncio.run(scrape_doctor_details(doctor_urls))
        with open("doctors_data_ollama.json", "w") as f:
            json.dump(details, f, indent=4)
        print(f"\n Done! Saved {len(details)} profiles to 'doctors_data_ollama.json'")
    else:
        print("No doctor profiles found. Switching to direct text extraction from listing page...")
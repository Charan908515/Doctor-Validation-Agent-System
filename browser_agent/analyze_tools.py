from playwright.sync_api import sync_playwright
from playwright.async_api import Page
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_sambanova import ChatSambaNova
from langchain_groq import ChatGroq
from schemas import build_attributes_model
from prompts import get_code_analysis_prompt, get_vision_analysis_prompt
from utils import extract_json_from_markdown
from browser_manager import browser_manager
from PIL import Image
import os
from typing import Literal,Optional
import mimetypes
import base64
import dotenv
import time
from langchain_core.tools import tool
dotenv.load_dotenv(os.path.join(os.path.dirname(__file__), '../config/.env'))
import asyncio
from crawl4ai import AsyncWebCrawler
from langchain_core.tools import tool

@tool
def scrape_with_crawl4ai(url: str):
    """
    Scrapes a specific URL using Crawl4AI to get high-quality Markdown content.
    Use this when you have a direct link to the 'Doctors' or 'Team' page and want 
    cleaner text than the standard scraper.
    """
    print(f">>> Crawl4AI: Scraping {url}...")
    
    async def _crawl():
        # Instantiate the crawler (verbose=False to keep logs clean)
        async with AsyncWebCrawler(verbose=False) as crawler:
            result = await crawler.arun(
                url=url,
                
                word_count_threshold=10, 
                bypass_cache=True
            )
            return result.markdown

    try:
        return asyncio.run(_crawl())
    except RuntimeError:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(_crawl())
    except Exception as e:
        return f"Error using Crawl4AI: {str(e)}"
@tool
def ask_human_help(message: str):
    """
    Pauses the automation and asks the human for help. 
    Use this if you see a CAPTCHA, Cloudflare block, or if you are stuck.
    """
    print(f"\n\n!!! AGENT NEEDS HELP: {message} !!!")
    print("Perform the necessary action in the browser (e.g., solve captcha).")
    input("Press ENTER here when you are done to continue...")
    return "Human help received. Proceeding."

@tool
def open_browser(url: str,sitename:str):
    """Open a browser and navigate to the specified URL."""
    return browser_manager.start_browser(url,sitename)

@tool
def close_browser():
    """Close the browser and cleanup resources."""
    return browser_manager.close_browser()

def extract_html_code():
    """Extracts the HTML code from the current page and saves a screenshot."""
    try:
        page = browser_manager.get_page()
        page.wait_for_load_state("load",timeout=60000)
        if not page:
            return "Error: No browser page is open"
        
        #page.wait_for_load_state("networkidle", timeout=60000)
        html_code = page.content()
        screenshot_path = "screenshot.png"
        page.screenshot(path=screenshot_path)
        return html_code
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return None



@tool
def extract_and_analyze_selectors(requirements: list[str]):
    """Extracts HTML code from current page and immediately analyzes it for selectors.
    This is a combined function that replaces the need to call extract_html_code() 
    followed by extract_selector_from_code().
    
    Args:
        requirements: List of UI elements to find selectors for (e.g., ["login button", "password field"])
    
    Returns:
        Structured selector information for the requested elements
    """
    try:
        page = browser_manager.get_page()
        
        if not page:
            return {"error": "No browser page is open"}
        
        page.wait_for_load_state("load",timeout=60000)
        
        html_code = page.content()
            
        requirements_text = "\n".join(requirements)
        
        # Retry logic with API key fallback
        api_keys = [
            ("gemini_llm14", os.getenv("gemini_llm6")),
            ("gemini_llm3", os.getenv("gemini_llm3")),
            ("gemini_llm4", os.getenv("gemini_llm4")),
            ("gemini_llm5", os.getenv("gemini_llm5"))
        ]
        api_keys1= [
            ("groq_llm1", os.getenv("groq_llm1")),
            ("groq_llm2", os.getenv("groq_llm2")),
            ("groq_llm3", os.getenv("groq_llm3")),
            ("groq_llm5", os.getenv("groq_llm5"))
        ]
        
        last_error = None
        for key_name, api_key in api_keys1:
            if not api_key:
                continue
                
            for attempt in range(3):  # 3 retries per API key
                try:
                    clean_response = {}
                    print(f"Attempting selector extraction with {key_name}, attempt {attempt + 1}/3")
                    #llm = ChatGoogleGenerativeAI(api_key=api_key, model="gemini-2.0-flash")
                    llm=ChatGroq(api_key=api_key, model="qwen/qwen3-32b")
                    prompt = get_code_analysis_prompt(requirements_text, html_code)
                    llm = llm.with_structured_output(build_attributes_model("Element_Properties", requirements))
                    response = llm.invoke(prompt)
                    
                    print(f"Successfully extracted selectors using {key_name}")
                    for key, val in response.dict().items():
                        sel = val.get('playwright_selector', '')
                        if "sample" in sel.lower() or len(sel) < 2:
                            print(f"Bad selector for {key}, attempting generic fallback")
                            clean_response[key] = f"text={key}" # Fallback to text match
                        else:
                            clean_response[key] = val
                
                    return clean_response
                    
                except Exception as e:
                    error_str = str(e).lower()
                    last_error = e
                    
                    # Check if it's a rate limit error
                    if "rate" in error_str or "quota" in error_str or "limit" in error_str or "429" in error_str:
                        print(f"Rate limit error with {key_name} on attempt {attempt + 1}: {str(e)}")
                        if attempt < 2:  # If not last attempt for this key
                            time.sleep(2)  # Wait 2 seconds before retry
                            continue
                        else:
                            print(f"Max retries reached for {key_name}, trying next API key")
                            break  # Try next API key
                    else:
                        # Non-rate-limit error, raise immediately
                        raise e
        
        # If we get here, all API keys failed
        error = f"Error in extract_and_analyze_selectors after trying all API keys: {str(last_error)}"
        return {"error": error}
        
    except Exception as e:
        error = f"Error in extract_and_analyze_selectors: {str(e)}"
        return {"error": error}

@tool
def analyze_using_vision(requirements: list[str], analysis_type: Optional[Literal["element_detection", "page_verification", "form_verification", "filter_detection", "hover_detection", "modal_detection","data_extraction"]]="element_detection", model: Optional[Literal["ollama","groq"]]="groq"):
    """Analyzes the current page using vision AI and returns the result.
    
    Args:
        requirements: List of requirements for analysis
        analysis_type: Type of analysis - element_detection, page_verification, form_verification, filter_detection, or hover_detection,data_extraction
        model: Vision model to use - ollama or groq
    """
    page = browser_manager.get_page()
    page.wait_for_load_state("load",timeout=60000)
    
    
    # Prepare screenshot
    try:
        page.screenshot(path="screenshot.png")
        screenshot_path = "screenshot.png"
        with Image.open(screenshot_path) as img:
            img_width, img_height = img.size
        
        mime_type, _ = mimetypes.guess_type(screenshot_path)
        if not mime_type:
            mime_type = 'image/png'
        with open(screenshot_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        print(f"Error preparing screenshot: {str(e)}")
        return {"error": f"Screenshot error: {str(e)}"}
    
    requirements_text = "\n".join(requirements)
    prompt = get_vision_analysis_prompt(requirements_text, img_width, img_height, analysis_type)
    
    # Retry logic with API key fallback for Groq
    if model == "groq":
        groq_keys = [
            ("groq_llm4", os.getenv("groq_llm4")),
            ("groq_llm5", os.getenv("groq_llm5"))
        ]
        
        img_url = f"data:{mime_type};base64,{img_b64}"
        messages = [
            {"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": img_url}}]},
        ]
        
        last_error = None
        for key_name, api_key in groq_keys:
            if not api_key:
                continue
                
            for attempt in range(3):  # 3 retries per API key
                try:
                    print(f"Attempting vision analysis with {key_name}, attempt {attempt + 1}/3")
                    llm = ChatGroq(api_key=api_key, model="meta-llama/llama-4-maverick-17b-128e-instruct")
                    
                    response = llm.invoke(messages)
                    json_response = extract_json_from_markdown(response.content)
                    
                    print(f"Successfully analyzed vision using {key_name}")
                    return json_response
                    
                except Exception as e:
                    error_str = str(e).lower()
                    last_error = e
                    
                    if "rate" in error_str or "quota" in error_str or "limit" in error_str or "429" in error_str:
                        print(f"Rate limit error with {key_name} on attempt {attempt + 1}: {str(e)}")
                        if attempt < 2:  
                            time.sleep(2)  
                        else:
                            print(f"Max retries reached for {key_name}, trying next API key")
                            break  
                    else:
                        
                        print(f"Non-rate-limit error in vision analysis: {str(e)}")
                        return {"error": str(e)}
        
        
        print(f"All Groq API keys failed: {str(last_error)}")
        return {"error": f"Vision analysis failed after trying all API keys: {str(last_error)}"}
        
    else:  
        try:
            print("using_ollama")
            llm = ChatOllama(model="llama3.2-vision:11b", temperature=0.1, model_kwargs={"gpu": True})
            
            img_url = screenshot_path
            messages = [
                {"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": img_url}}]},
            ]
            
            response = llm.invoke(messages)
            json_response = extract_json_from_markdown(response.content)
            return json_response
            
        except Exception as e:
            print(f"Error in ollama vision analysis: {str(e)}")
            return {"error": str(e)}

def extract_page_content_as_markdown() -> str:
    """
    Extracts the page content as clean Markdown.
    """
    page = browser_manager.get_page()
    if not page: return "Error: No page open"

    try:
       
        markdown = page.evaluate("""
            () => {
                function isVisible(el) {
                    return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                }

                function cleanText(text) {
                    return text.replace(/\\s+/g, ' ').trim();
                }

                function traverse(node) {
                    let text = "";
                    
                    // Handle Text Nodes
                    if (node.nodeType === 3) {
                        return cleanText(node.textContent);
                    }
                    
                    // Handle Elements
                    if (node.nodeType === 1) {
                        if (!isVisible(node)) return "";
                        
                        const tag = node.tagName.toLowerCase();
                        
                        // Skip script/style/noscript
                        if (['script', 'style', 'noscript', 'svg', 'path', 'head', 'meta'].includes(tag)) {
                            return "";
                        }

                        // Process children first
                        let childrenText = "";
                        node.childNodes.forEach(child => {
                            childrenText += traverse(child) + " ";
                        });
                        childrenText = childrenText.replace(/\\s+/g, ' ').trim();

                        if (!childrenText && !['img', 'input', 'br', 'hr'].includes(tag)) return "";

                        // Format based on Tag
                        if (tag === 'a') {
                            const href = node.getAttribute('href');
                            return href ? ` [${childrenText}](${href}) ` : childrenText;
                        }
                        if (tag === 'img') {
                            const alt = node.getAttribute('alt') || 'Image';
                            // const src = node.getAttribute('src'); // Optional: include src if needed
                            return ` ![${alt}] `;
                        }
                        if (['h1', 'h2', 'h3'].includes(tag)) {
                            return `\\n\\n# ${childrenText}\\n\\n`;
                        }
                        if (['h4', 'h5', 'h6'].includes(tag)) {
                            return `\\n\\n## ${childrenText}\\n\\n`;
                        }
                        if (tag === 'li') {
                            return `\\n- ${childrenText}`;
                        }
                        if (tag === 'p' || tag === 'div') {
                            return `\\n${childrenText}\\n`;
                        }
                        if (tag === 'button') {
                            return ` [Button: ${childrenText}] `;
                        }
                        if (tag === 'input') {
                            const val = node.value || node.getAttribute('placeholder') || '';
                            return ` [Input: ${val}] `;
                        }
                        
                        return childrenText + " ";
                    }
                    return "";
                }

                return traverse(document.body);
            }
        """)
        
        
        return markdown[:40000] 

    except Exception as e:
        return f"Error extracting markdown: {e}"

@tool
def scrape_data_using_text(requirements: str):
    """
    Scrapes structured data (JSON) from the page using text analysis.
    FAST & CHEAP alternative to Vision.
    
    Args:
        requirements: What to extract (e.g. "list of products with name, price, and url")
    """
    # 1. Get the content (Text + Links)
    content = extract_page_content_as_markdown()
    
    if "Error" in content:
        return {"error": content}

    # 2. Ask Gemini to parse it
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        google_api_key=os.getenv("gemini_llm1"),
        temperature=0
    )
    groq_llm=ChatGroq(
        model="qwen/qwen3-32b",
        api_key=os.getenv("groq_llm4"),
        temperature=0
    )
    sambanova_llm=ChatSambaNova(model="gpt-oss-120b",
    sambanova_api_key=os.getenv("sambanova2"),
    temperature=0.1,
    top_p=0.1,
    )
    ollama_llm=ChatOllama(
        model="deepseek-r1:8b"
    )
    prompt = f"""
    You are a Data Extraction Agent.
    
    ### USER REQUEST
    Extract the following data: {requirements}
    
    ### PAGE CONTENT (Markdown)
    {content}
    
    ### INSTRUCTIONS
    1. Identify all items matching the request.
    2. Extract details accurately.
    3. Return ONLY valid JSON.
    
    ### FORMAT
    {{
      "items": [
        {{ "name": "...", "price": "...", "url": "...", "description": "..." }}
      ],
      "count": N
    }}
    """
    
    try:
        response = ollama_llm.invoke(prompt)
        return extract_json_from_markdown(response.content)
    except Exception as e:
        return {"error": f"LLM Extraction failed: {e}"}

if __name__ == "__main__":
    browser_manager.start_browser("https://www.naukri.com/")
    requirements = ["login button", "register button"]
    
    features = analyze_using_vision(requirements, "element_detection", "ollama")
    print(features)
    
    browser_manager.close_browser()
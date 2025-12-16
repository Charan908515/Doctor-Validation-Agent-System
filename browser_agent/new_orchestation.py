import os
import time
import re
import asyncio
import sys
from urllib.parse import urlparse
from typing import Literal, List, Annotated
import operator
import dotenv
import nest_asyncio
from langchain_core.messages import ChatMessage, HumanMessage, AIMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_sambanova import ChatSambaNova
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.output_parsers import JsonOutputParser
from langchain_community.tools.tavily_search import TavilySearchResults
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.types import Command
from pydantic import BaseModel, Field
from browser_manager import browser_manager
from browser_tools import (
    click_id, fill_id, scan_page_with_som,hover_id,get_all_page_links,
    scroll_one_screen, press_key, get_page_text, hover_element,
    get_visible_input_fields, select_dropdown_option,
    open_dropdown_and_select, upload_file,get_all_page_links, 
        batch_scrape_doctors
)
from analyze_tools import (
    extract_and_analyze_selectors, analyze_using_vision, 
    scrape_data_using_text, scrape_with_crawl4ai,close_browser,open_browser
)
from new_prompts import (
    get_planning_agent_initial_prompt, 
    get_planning_agent_refine_prompt, 
    get_execution_agent_prompt1
)
nest_asyncio.apply()
dotenv.load_dotenv(os.path.join(os.path.dirname(__file__), '../config/.env'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config.config import LLMConfig as CentralLLMConfig
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from google.api_core.exceptions import ResourceExhausted

class ThrottledGoogleGenerativeAI(ChatGoogleGenerativeAI):
    @retry(
        retry=retry_if_exception_type(ResourceExhausted), 
        wait=wait_exponential(multiplier=1, min=2, max=10), 
        stop=stop_after_attempt(5)
    )
    def invoke(self, *args, **kwargs):
        return super().invoke(*args, **kwargs)

class ThrottledChatSambaNova(ChatSambaNova):
    def invoke(self, *args, **kwargs):
        time.sleep(12)  
        return super().invoke(*args, **kwargs)

def get_current_browser_info():
    page = browser_manager.get_page()
    if page and not page.is_closed():
        try:
            current_url = page.url
            parsed = urlparse(current_url)
            site_name = parsed.netloc.replace("www.", "")
            if not site_name: site_name = "local_or_unknown"
            return current_url, site_name
        except Exception as e:
            print(f"Error reading browser URL: {e}")
    return "unknown_url", "unknown_site"

def is_rate_limit_error(error_message: str) -> bool:
    """Check if an error message indicates a rate limit."""
    if not error_message:
        return False
    
    error_lower = str(error_message).lower()
    rate_limit_indicators = [
        '429',
        'rate limit',
        'quota exceeded',
        'too many requests',
        'resource_exhausted',
        'resourceexhausted'
    ]
    return any(indicator in error_lower for indicator in rate_limit_indicators)

# --- Schema Definitions ---
class PlannerOutput(BaseModel):
    agent: Literal["EXECUTION", "OUTPUT_FORMATTING"] = Field(
        description="The agent to run next. Use 'end' if the task is complete."
    )
    task: str = Field(
        description="The specific instruction for the agent."
    )
    reasoning: str = Field(
        description="Brief reasoning for why this step is chosen."
    )

class AgentState(MessagesState):
    input_str: str
    step_index: int
    execution_messages: Annotated[List[BaseMessage], operator.add]
    output_agent_messages: Annotated[List[BaseMessage], operator.add]
    final_output: str
    planner_api_key_index: int
    executor_api_key_index: int


def planner_agent(state: AgentState):
    user_input = state["input_str"]
    step_index = state.get("step_index", 0)
    if step_index == 0:
        system_message = get_planning_agent_initial_prompt(user_input)
        human_msg = "Please generate the initial plan."
    else:
        if browser_manager.get_page():
            try:
                interactive_map = scan_page_with_som.invoke({"query": None})
                if len(interactive_map) > 2000: 
                    interactive_map = interactive_map[:2000] + "...(truncated)"
                current_page_state = f"""URL: {browser_manager.get_page().url}INTERACTIVE ELEMENTS AVAILABLE:{interactive_map}"""
            except Exception as e:
                current_page_state = f"Page Open, but scan failed: {e}"
        else:
            current_page_state = "Browser not open."
        
        current_url, _ = get_current_browser_info()
        system_message = get_planning_agent_refine_prompt(current_url, current_page_state,user_input)
        human_msg = "Based on the browser state and history, what is the next step?"

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_message),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", human_msg)
    ])

    sanitized_history = state["messages"]
    
    
    current_start_index = state.get("planner_api_key_index", 1)
    rotation_list = CentralLLMConfig.get_main_llm_with_rotation(start_index=current_start_index, provider="sambanova")
    total_keys = len(rotation_list)
    
    last_error = None
    
    for idx, (key_name, llm_base) in enumerate(rotation_list):
        try:
            print(f"🔑 Planner trying {key_name}...")
            
            
            """gemini_llm = ThrottledGoogleGenerativeAI(
                model="gemini-2.5-flash",
                google_api_key=llm_base.google_api_key,
                temperature=0
            )"""
            
            s_key = llm_base.sambanova_api_key
            if hasattr(s_key, "get_secret_value"):
                s_key = s_key.get_secret_value()
            
            sambanova_llm = ThrottledChatSambaNova(
                model="gpt-oss-120b",
                api_key=s_key,
                temperature=0
            )
            structured_llm = sambanova_llm.with_structured_output(PlannerOutput)
            
            print(f"--- PLANNER (Step {step_index}) ---")
            chain = prompt | structured_llm
            response: PlannerOutput = chain.invoke({"chat_history": sanitized_history})
            
            result_task = response.task
            result_agent = response.agent
            
            print(f"✅ Planner succeeded with {key_name}")
            print(f">>> Decision: {result_agent} -> {result_task}")
            
            updated_messages = [HumanMessage(content=f"[Planner]: Next Step ({result_agent}): {result_task}")]
            
            successful_key_global_index = (current_start_index + idx) % total_keys

            if result_agent == "EXECUTION":
                return Command(
                    update={
                        "messages": updated_messages,
                        "execution_messages": [HumanMessage(content=result_task)],
                        "planner_api_key_index": successful_key_global_index
                    },
                    goto="executor_agent"
                )
            elif result_agent == "OUTPUT_FORMATTING":
                return Command(
                    update={
                        "messages": updated_messages,
                        "output_agent_messages": [HumanMessage(content=result_task)],
                        "planner_api_key_index": successful_key_global_index
                    },
                    goto="output_formatting_agent"
                )
            elif result_agent == "end":
                return Command(
                    update={"messages": [HumanMessage(content="Task Completed.")]},
                    goto=END
                )
            else:
                return Command(goto=END)
                
        except Exception as e:
            last_error = e
            if is_rate_limit_error(str(e)):
                print(f"⚠️  Rate limit on {key_name}, rotating...")
                continue
            else:
                print(f">>>> Planner Error (non-rate-limit): {e}")
              
                return Command(
                    update={"messages": [HumanMessage(content=f"Planner Error: {e}")]},
                    goto="planner_agent"
                )
    
   
    print(f"❌ All SambaNova keys exhausted for planner")
    return Command(
        update={"messages": [HumanMessage(content=f"Planner Error - All keys exhausted: {last_error}")]},
        goto=END
    )

    

def executor_agent(state: AgentState):
    task_msg = state["execution_messages"][-1]
    task = task_msg.content
    task=task.replace("{","{{")
    task=task.replace("}","}}")
    # Define Tools
    tavily = TavilySearchResults(tavily_api_key="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")
    tools = [
        tavily, click_id, fill_id, hover_id,
        scroll_one_screen, press_key, get_page_text, open_browser,
        scan_page_with_som,
        scrape_data_using_text, analyze_using_vision, extract_and_analyze_selectors,get_all_page_links, 
        batch_scrape_doctors,
        hover_element, get_visible_input_fields, select_dropdown_option,
        open_dropdown_and_select, scrape_with_crawl4ai, upload_file
    ]
    
    system_message = get_execution_agent_prompt1(task)
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_message),
        MessagesPlaceholder(variable_name="chat_history"),
        MessagesPlaceholder(variable_name="agent_scratchpad")
    ])
    
    
    history_subset = state["execution_messages"][-5:]
    
    current_start_index = state.get("executor_api_key_index", 5)
    rotation_list = CentralLLMConfig.get_main_llm_with_rotation(start_index=current_start_index, provider="sambanova")
    total_keys = len(rotation_list)
    
    last_error = None
    
    for idx, (key_name, llm_base) in enumerate(rotation_list):
        try:
            print(f"🔑 Executor trying {key_name}...")
            
            """gemini_llm = ThrottledGoogleGenerativeAI(
                model="gemini-2.5-flash",
                google_api_key=llm_base.google_api_key,
                temperature=0
            )"""
            # Extract key from SecretStr safely
            s_key = llm_base.sambanova_api_key
            if hasattr(s_key, "get_secret_value"):
                s_key = s_key.get_secret_value()

            sambanova_llm = ThrottledChatSambaNova(
                model="gpt-oss-120b",
                api_key=s_key,
                temperature=0
            )
            
            agent = create_tool_calling_agent(sambanova_llm, tools, prompt)
            agent_executor = AgentExecutor(
                agent=agent, tools=tools, verbose=True,
                max_iterations=15, handle_parsing_errors=True
            )
            
            print(f"--- EXECUTOR: {task} ---")
            result = agent_executor.invoke({
                "input": task, 
                "chat_history": history_subset
            })
            
            output_text = result["output"]
            
            print(f"✅ Executor succeeded with {key_name}")
            
            successful_key_global_index = (current_start_index + idx) % total_keys
            
            return Command(
                update={
                    "execution_messages": [AIMessage(content=output_text)],
                    "messages": [AIMessage(content=f"[Executor]: {output_text}")],
                    "step_index": state["step_index"] + 1,
                    "executor_api_key_index": successful_key_global_index
                },
                goto="planner_agent"
            )
            
        except Exception as e:
            last_error = e
            if is_rate_limit_error(str(e)):
                print(f"⚠️  Rate limit on {key_name}, rotating...")
                continue
            else:
                print(f">>> Executor Error (non-rate-limit): {e}")
                
                return Command(
                    update={
                        "messages": [HumanMessage(content=f"Executor Failed: {e}")],
                        "step_index": state["step_index"] + 1
                    },
                    goto="planner_agent"
                )
    
   
    print(f"❌ All SambaNova keys exhausted for executor")
    return Command(
        update={
            "messages": [HumanMessage(content=f"Executor Failed - All keys exhausted: {last_error}")],
            "step_index": state["step_index"] + 1
        },
        goto="planner_agent"
    )


def extract_json_from_markdown(text: str) -> str:
    """Extract JSON from markdown code blocks like ```json ... ```"""
   
    pattern = r'```(?:json)?\s*\n?(.*?)\n?```'
    match = re.search(pattern, text, re.DOTALL)
    
    if match:
        return match.group(1).strip()
    
    return text.strip()

def output_agent(state: AgentState):
    print("--- OUTPUT FORMATTING ---")
    
    instructions = state["output_agent_messages"][-1].content
   
    data_context = "\n".join([m.content for m in state["messages"] if isinstance(m, AIMessage)])
    
    prompt = f"""
    You are a Data Extraction Specialist.
    USER INSTRUCTIONS: {instructions}
    
    RAW DATA CONTEXT:
    {data_context}
    
    Please format the data exactly as requested (likely JSON). 
    Return ONLY the raw formatted text (e.g., the JSON object). Do not add markdown blocks like ```json.
    """
    
    try:
        ollama_llm = ChatOllama(model="deepseek-r1:8b")
        result = ollama_llm.invoke(prompt)
        formatted_output = result.content.strip()
        formatted_output = extract_json_from_markdown(formatted_output)
        
        
        filename = "doctors_data.json"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(formatted_output)
            
        print(f"\n✅ SUCCESS (Ollama): Data saved to '{filename}'")
        print(f"Final Output Preview: {formatted_output[:200]}...")

        return Command(
            update={
                "messages": [AIMessage(content=f"Final Output saved to {filename}: {formatted_output}")],
                "final_output": formatted_output
            },
            goto=END
        )
    except Exception as ollama_error:
        print(f"⚠️  Ollama failed: {ollama_error}. Trying Gemini fallback...")
        
        
        rotation_list = CentralLLMConfig.get_main_llm_with_rotation(start_index=0, provider="gemini")
        
        for idx, (key_name, llm_base) in enumerate(rotation_list):
            try:
                print(f"🔑 Output agent trying {key_name}...")
                
                llm = ThrottledGoogleGenerativeAI(
                    model="gemini-2.5-flash",
                    google_api_key=llm_base.google_api_key,
                    temperature=0.1
                )
                
                result = llm.invoke(prompt)
                formatted_output = result.content.strip()
                formatted_output = extract_json_from_markdown(formatted_output)
                
                
                filename = "doctors_data.json"
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(formatted_output)
                    
                print(f"\n✅ SUCCESS ({key_name}): Data saved to '{filename}'")
                print(f"Final Output Preview: {formatted_output[:200]}...")

                return Command(
                    update={
                        "messages": [AIMessage(content=f"Final Output saved to {filename}: {formatted_output}")],
                        "final_output": formatted_output
                    },
                    goto=END
                )
                
            except Exception as e:
                if is_rate_limit_error(str(e)):
                    print(f"⚠️  Rate limit on {key_name}, rotating...")
                    continue
                else:
                    print(f"❌ Output agent error: {e}")
                    return Command(goto="planner_agent")
        print(f"❌ All output formatting options exhausted")
        return Command(goto="planner_agent")

def create_agent():
    workflow = StateGraph(AgentState)
    
    workflow.add_node("planner_agent", planner_agent)
    workflow.add_node("executor_agent", executor_agent) 
    workflow.add_node("output_formatting_agent", output_agent) 

    workflow.add_edge(START, "planner_agent")
    
    return workflow.compile()

def run_agent(hospital_name,hospital_location):
    try:
        prompt =f"""
                Find the official website for '{hospital_name}' located at '{hospital_location}'.
                
                Once found:
                1. Navigate to the doctors or specialties section.
                2. If you see a list of departments/specialties, extract their links and use batch processing to find doctor profiles.
                3. Scrape the details (Name, Qualification, Specialty, Phone Number, url of the doctor page if seperate page is present) for all doctors found.
                4. Output the final data as JSON.
                """
        app = create_agent()
        initial_state = {
            "input_str": prompt,
            "step_index": 0,
            "final_output": "",
            "execution_messages": [],
            "output_agent_messages": [],
            "messages": [],
            "planner_api_key_index": 1,
            "executor_api_key_index": 6
        }
        
        print(f"Starting Task: {prompt}")
        result = app.invoke(initial_state)
        for key, item in result.items():
            print("="*60)
            print(f">>>{key}")
            print(item)
        return {"output": result.get("final_output", "No output generated.")}
    except Exception as e:
        print(f"An error occurred during execution: {e}")
        return {"error": f"Error during agent running: {e}"}
    finally:
        print(">>> CLEANUP: Closing Browser...")
        
        try:
            if browser_manager.is_browser_open():
                browser_manager.close_browser()
                
                time.sleep(0.5)
        except Exception as cleanup_error:
            print(f"Warning: Browser cleanup error: {cleanup_error}")

if __name__=="__main__":
    a1="open https://www.medicoverhospitals.in/hospitals/andhra-pradesh/visakhapatnam-mvp/?utm_source=google&utm_medium=organic&utm_campaign=gmb-vizag-mvp website and find whether there is a search field for searching doctors or not and give output as json(output:True or False)"
    a2="open https://www.medicoverhospitals.in/hospitals/andhra-pradesh/visakhapatnam-mvp/?utm_source=google&utm_medium=organic&utm_campaign=gmb-vizag-mvp website and search for Dr Bommana Vinay Kumar and give the output format as a json format with name,phone number,specialization,qualifications"
    a="open https://www.medicoverhospitals.in/hospitals/andhra-pradesh/visakhapatnam-mvp/?utm_source=google&utm_medium=organic&utm_campaign=gmb-vizag-mvp website then search for doctors.sometimes the list is deep and seperated as deparments  so search on the website carefully and scrape all the doctors details (all departments) who are working on the hospital.the output format is a json format with name,phone number,specialization,qualifications"
    prompt = """
    Find the official website for 'Medicover Hospitals' located at 'Visakhapatnam MVP'.
    
    Once found:
    1. Navigate to the doctors or specialties section.
    2. If you see a list of departments/specialties, extract their links and use batch processing to find doctor profiles.
    3. Scrape the details (Name, Qualification, Specialty,url of the doctor page if seperate page is present ) for all doctors found.
    4. Output the final data as JSON.
    """
    prompt1 = """
    Find the official website for 'Sankalpa Hospitals' located at 'Karakambadi Bazar St, Tata Nagar, Tirupati, Andhra Pradesh 517501'.
    
    Once found:
    1. Navigate to the doctors or specialties section.
    2. If you see a list of departments/specialties, extract their links and use batch processing to find doctor profiles.
    3. Scrape the details (Name, Qualification, Specialty) for all doctors found.
    4. Output the final data as JSON.
    """
   
    output=run_agent('Sankalpa Hospitals','Karakambadi Bazar St, Tata Nagar, Tirupati, Andhra Pradesh 517501')
    print(output)
    
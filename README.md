# Doctor Validation Agent System

A comprehensive, AI-powered system for automating the verification of doctor profiles against hospital websites. This system uses advanced browser automation, multi-agent orchestration, and fuzzy matching to validate high volumes of provider data with precision.

## ❓ Why It Is Needed

In the healthcare industry, maintaining accurate provider directories is critical but challenging. 
- **The Problem**: Manual verification of doctor details (Name, Specialty, Qualification, License) across thousands of hospital websites is:
    - **Slow**: Taking hours or days for large datasets.
    - **Error-Prone**: Human fatigue leads to missed discrepancies.
    - **Dynamic**: Hospital websites change structure frequently, breaking simple scrapers.
- **The Solution**: An intelligent "Agentic" system that behaves like a human researcher. It doesn't just scrape; it *navigates*, *reads*, *plans*, and *verifies* information autonomously, ensuring data integrity for healthcare payers and providers.

## ✨ Functionality

1.  **Autonomous Navigation**:
    -   Understands natural language commands (e.g., "Find the cardiology department and list all doctors").
    -   Navigates complex UI (dropdowns, search bars, paginated lists) using **Playwright**.
2.  **Intelligent Extraction**:
    -   Uses **Crawl4AI** and **LLMs** (SambaNova, Groq, Gemini) to extract structured data from unstructured HTML.
    -   Handles "lazy loading" and dynamic content seamlessly.
3.  **Strict Validation Protocol**:
    -   **Location Check**: Verifies the hospital actually exists at the given address using **Mappls** or **Google Maps API**.
    -   **Fuzzy Matching**: Compares input CSV data vs. website data with smart tolerance for spelling variations (e.g., "Dr. V. Kumar" vs "Vinay Kumar").
4.  **Resilient Architecture**:
    -   **LLM Rotation**: Automatically rotates between API keys (SambaNova, Groq, Gemini) to handle rate limits.
    -   **Incremental Saving**: Saves progress link-by-link to prevent data loss.
5.  **Interactive Dashboard**:
    -   React-based UI to upload files, monitor real-time scraping progress, and manually review "flagged" records.

## 🛠️ How It Works (Architecture)

The system is composed of three main layers. Here is the breakdown with key file references:

### 1. The "Brain" (Browser Agent)
Located in `browser_agent/`, this is the core intelligence.
-   **Multi-Agent Orchestration** (`browser_agent/new_orchestation.py`): 
    -   Built with **LangGraph**.
    -   **Planner Agent**: Breaks down the high-level goal (e.g., "Find doctors") into steps.
    -   **Executor Agent**: Executes tools (Click, Type, Scroll, Read).
    -   **Output Agent**: Formats the final scraped data into JSON.
-   **Smart Crawling** (`browser_agent/crawler.py`):
    -   Uses **Crawl4AI** combined with LLMs to "read" a page and extract doctor profiles into structured Pydantic models.
-   **Tools** (`browser_agent/browser_tools.py`):
    -   Wraps Playwright functions (click, fill, scan_page) into tools callable by the AI.

### 2. The Controller (Validation Logic)
-   **Orchestrator** (`vallidation_agent.py`):
    -   The entry point for batch processing.
    -   Groups input data by hospital (`group_doctors_by_hospital`).
    -   Manages the flow: `CSV -> Location Check -> Scrape -> Compare -> Save`.
-   **Scraping Logic** (`scraping.py`):
    -   Connects the validation logic to the Browser Agent.
    -   Performs the **Mappls/Google Maps** location verification before attempting to scrape.

### 3. The Application Layer (Frontend & Backend)
-   **Backend** (`backend/`):
    -   **API** (`backend/main.py`, `backend/api/routes.py`): A **FastAPI** server that exposes endpoints for uploading CSVs and starting validation tasks.
    -   **Database** (`backend/models.py`, `backend/database.py`): Uses **SQLite** (via SQLAlchemy) to store upload history, validation sessions, and results.
-   **Frontend** (`frontend/`):
    -   A **React (Vite)** application for user interaction.
    -   Displays real-time logs and progress bars.

## 🚀 Setup Instructions

### Prerequisites
-   **Python 3.9+**
-   **Node.js & npm** (for the frontend)
-   **Playwright Browsers**: Must be installed via `playwright install`

### 1. Environment Configuration
Create a `.env` file in the `config/` directory (or root) with the following keys:
```env
# Geocoding
google_maps_api_key=your_key
# OR
mappls_client_id=your_id
mappls_client_secret=your_secret

# LLM Providers (At least one required)
groq_api_key=your_groq_key
sambanova_api_key=your_sambanova_key
google_api_key=your_gemini_key
```

### 2. Backend Setup
Navigate to the root directory.

1.  **Install Python Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
2.  **Install Playwright Browsers**:
    ```bash
    playwright install
    ```
3.  **Run the Backend Server**:
    Navigate to the backend folder and run:
    ```bash
    cd backend
    python main.py
    # Server starts at http://localhost:8000
    ```
    *Note: The backend will automatically create the SQLite database (`validation.db`).*

### 3. Frontend Setup
Open a new terminal.

1.  **Navigate to Frontend**:
    ```bash
    cd frontend
    ```
2.  **Install Dependencies**:
    ```bash
    npm install
    ```
3.  **Start the UI**:
    ```bash
    npm run dev
    # App opens at http://localhost:5173
    ```

## 📖 Usage Guide

1.  Open the web dashboard (usually `http://localhost:5173`).
2.  **Upload**: Go to the "Upload" tab and drop your CSV file containing doctor data.
    -   *Required Columns*: `hospital_name`, `address`, `doctor_name`, `specialization`, `phone_number`.
3.  **Start Validation**: Click the "Validate" button next to your uploaded file.
4.  **Monitor**: Watch the "Real-time Status" panel. You will see:
    -   "Finding address for [Hospital]..."
    -   "Found [X] doctors on website..."
    -   "Verifying..."
5.  **Review**: Once complete, view the results table.
    -   ✅ **Verified**: Exact match found.
    -   ↻ **Updated**: Doctor found, but details (phone/specialty) were updated from the website.
    -   ⚠️ **Needs Review**: Hospital or doctor could not be found automatically.
6.  **Export**: Download the final validated CSV from the "Outputs" folder or the Dashboard.

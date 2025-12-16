import sys
import asyncio

# FORCE Proactor (Correct for Playwright on Windows)
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine, Base
from models import Provider, UploadHistory, ValidationResult, ValidationSession
from api.routes import router

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Doctor Validation API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(router)

@app.get("/")
async def root():
    return {"message": "Doctor Validation API", "status": "running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    # reload=False is safer for Playwright stability, but True works if Proactor is enforced
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
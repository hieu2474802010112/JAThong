from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.api import api_router

app = FastAPI(
    title="AI-powered CV Management & Grading System API",
    description="Backend API for managing, parsing, and grading CVs using Google Gemini AI.",
    version="1.0.0"
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API v1 routes
app.include_router(api_router, prefix="/api/v1")

@app.get("/", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "service": "AI CV Management API",
        "version": "1.0.0"
    }

from fastapi import APIRouter
from app.api.v1.endpoints import cv, chat

api_router = APIRouter()
api_router.include_router(cv.router, prefix="/cv", tags=["CV"])
api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])

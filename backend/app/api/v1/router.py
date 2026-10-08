"""API v1 router aggregator."""
from fastapi import APIRouter
from backend.app.api.v1.github import router as github_router

api_v1_router = APIRouter()
api_v1_router.include_router(github_router)

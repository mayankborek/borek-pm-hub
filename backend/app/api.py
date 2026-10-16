"""Versioned API router. Feature routers (auth, projects, tasks) are added here later."""

from fastapi import APIRouter

api_router = APIRouter(prefix="/api/v1")

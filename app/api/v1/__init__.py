from fastapi import APIRouter
from app.api.v1.routes import entries, types

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(types.router)
api_router.include_router(entries.router)

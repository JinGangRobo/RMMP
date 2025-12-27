from app.core.config import settings
from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def root():
    return {"message": "Hello World"}

@router.get("/info")
async def info():
    return {
        "app_name": settings.APP_NAME,
        "app_version": settings.APP_VERSION,
        "app_description": settings.APP_DESCRIPTION,
        "app_license": settings.APP_LICENSE,
        "app_env": settings.APP_ENV,
        "debug": settings.DEBUG,
        "log_level": settings.LOG_LEVEL,
        "host": settings.HOST,
        "port": settings.PORT,
    }

from fastapi import APIRouter
from app.api.v1.base import root_router

# 基础路由
base_router = APIRouter()
base_router.include_router(root_router)

# 总路由
router = APIRouter()
router.include_router(base_router)
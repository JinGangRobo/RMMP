import logging
import threading
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.api.v1 import router
from app.core.config import settings
from app.core.database import create_db_and_tables
from app.core.feishu import start_feishu_ws_client
from app.core.logger import setup_logging
from app.middleware.logging_middleware import LoggingMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""

    # 初始化日志
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info(f"应用启动 - 环境: {settings.APP_ENV}")
    logger.info(f"当前时间: 2025-11-19 00:17:00 UTC")
    logger.info(f"当前用户: AC-DB")

    logger.info("初始化数据库连接...")
    try:
        create_db_and_tables()
        logger.info("数据表创建成功")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        raise

    ws_thread = threading.Thread(target=start_feishu_ws_client,
                                 daemon=True)
    ws_thread.start()
    logger.info("飞书消息监听线程已启动")

    yield

    # 关闭时
    logger.info("应用关闭，清理资源...")


def create_app():
    _app = FastAPI(
        title=settings.APP_NAME,
        description=settings.APP_DESCRIPTION,
        version=settings.APP_VERSION,
        license_info=settings.APP_LICENSE,
        debug=settings.DEBUG,
        lifespan=lifespan
    )

    # 日志中间件
    _app.add_middleware(LoggingMiddleware)
    # 注册路由
    _app.include_router(router)

    return _app


app = create_app()

if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT,
                reload=True if settings.APP_ENV == "dev" else False,
                log_config=None)

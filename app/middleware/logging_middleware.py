import logging
import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件"""

    async def dispatch(self, request: Request,
                       call_next: Callable) -> Response:
        # 生成请求 ID
        request_id = str(uuid.uuid4())

        # 记录请求信息
        start_time = time.time()

        # 获取客户端信息
        client_host = request.client.host if request.client else "unknown"

        # 请求开始日志
        logger.info(
            f"请求开始",
            extra={
                "request_id": request_id,
                "method": request.method,
                "url": str(request.url),
                "client_host": client_host,
                "user_agent": request.headers.get("user-agent", "unknown")
            }
        )

        # 将 request_id 添加到请求状态
        request.state.request_id = request_id

        try:
            # 处理请求
            response = await call_next(request)

            # 计算处理时间
            process_time = time.time() - start_time

            # 添加自定义响应头
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = str(process_time)

            # 请求完成日志
            logger.info(
                f"请求完成",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "url": str(request.url),
                    "status_code": response.status_code,
                    "process_time": f"{process_time:.3f}s",
                    "client_host": client_host
                }
            )

            return response

        except Exception as e:
            # 计算处理时间
            process_time = time.time() - start_time

            # 错误日志
            logger.error(
                f"请求异常",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "url": str(request.url),
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "process_time": f"{process_time:.3f}s",
                    "client_host": client_host
                },
                exc_info=True
            )
            raise


class RequestContextMiddleware(BaseHTTPMiddleware):
    """请求上下文中间件 - 在日志中添加上下文信息"""

    async def dispatch(self, request: Request,
                       call_next: Callable) -> Response:
        # 这里可以添加用户信息、租户信息等到日志上下文
        # 例如从 JWT token 中提取用户信息

        response = await call_next(request)
        return response

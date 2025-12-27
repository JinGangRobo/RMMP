import logging
import logging.handlers
import sys
from datetime import UTC, datetime
from pathlib import Path

import colorlog
from pythonjsonlogger.json import JsonFormatter

from app.core.config import settings


class CustomJsonFormatter(JsonFormatter):
    """自定义 JSON 格式化器，用于扩展日志字段，便于日志分析和追踪。"""

    def add_fields(self, log_record, record, message_dict):
        super(CustomJsonFormatter, self).add_fields(log_record, record,
                                                    message_dict)
        log_record['timestamp'] = datetime.now(UTC).isoformat()
        log_record['level'] = record.levelname
        log_record['logger'] = record.name
        log_record['module'] = record.module
        log_record['function'] = record.funcName
        log_record['line'] = record.lineno
        log_record['env'] = settings.APP_ENV
        log_record['app'] = settings.APP_NAME
        log_record['version'] = settings.APP_VERSION


class ColoredFormatter(colorlog.ColoredFormatter):
    """彩色日志格式化器（仅用于控制台输出）"""

    def __init__(self):
        super().__init__(
            fmt='%(log_color)s%(asctime)s%(reset)s [%(levelname)-8s]%(reset)s '
                '%(cyan)s%(name)s%(reset)s %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            log_colors={
                'DEBUG': 'blue',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'bold_red',
            },
            secondary_log_colors={
                'message': {
                    'DEBUG': 'white',
                    'INFO': 'white',
                    'WARNING': 'yellow',
                    'ERROR': 'red',
                    'CRITICAL': 'bold_red',
                }
            }
        )


class PlainFormatter(logging.Formatter):
    """纯文本格式化器（用于文件输出，无 ANSI 转义码）"""

    def __init__(self):
        super().__init__(
            fmt='%(asctime)s [%(levelname)-8s] %(name)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )


def print_startup_banner():
    """打印启动欢迎图案"""
    banner = r"""
    _      _____   ____    _   _   _  __   ___  
   / \    |_   _| / ___|  | | | | | |/ /  / _ \ 
  / _ \     | |   \___ \  | | | | | ' /  | | | |
 / ___ \    | |    ___) | | |_| | | . \  | |_| |
/_/   \_\   |_|   |____/   \___/  |_|\_\  \___/ 
                                                
    """.format(
        version=settings.APP_VERSION,
        env=settings.APP_ENV.upper(),
        level=settings.LOG_LEVEL.upper()
    )
    print(banner)


def get_formatter(for_console=False):
    """根据环境和输出目标获取合适的格式化器"""
    if settings.LOG_FORMAT == "json" and not for_console:
        return CustomJsonFormatter(
            '%(timestamp)s %(level)s %(name)s %(message)s')
    elif for_console and settings.APP_ENV == "dev":
        return ColoredFormatter()
    else:
        return PlainFormatter()


def setup_logging():
    """设置日志配置"""

    # 打印启动图案
    print_startup_banner()

    # 创建日志目录
    log_path = Path(settings.LOG_FILE_PATH)
    log_path.mkdir(parents=True, exist_ok=True)

    # 获取根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))
    root_logger.handlers.clear()

    # 控制台处理器（使用彩色格式）
    if settings.LOG_TO_CONSOLE:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(
            logging.DEBUG if settings.DEBUG else logging.INFO)
        console_handler.setFormatter(get_formatter(for_console=True))
        root_logger.addHandler(console_handler)

    # 文件处理器（使用纯文本格式，避免 ANSI 转义码）
    if settings.LOG_TO_FILE:
        # 通用日志文件
        app_file_handler = logging.handlers.RotatingFileHandler(
            filename=log_path / "app.log",
            maxBytes=settings.LOG_FILE_MAX_BYTES,
            backupCount=settings.LOG_FILE_BACKUP_COUNT,
            encoding='utf-8'
        )
        app_file_handler.setLevel(logging.DEBUG)
        app_file_handler.setFormatter(PlainFormatter())  # 文件使用纯文本
        root_logger.addHandler(app_file_handler)

        # 错误日志文件
        error_file_handler = logging.handlers.RotatingFileHandler(
            filename=log_path / "error.log",
            maxBytes=settings.LOG_FILE_MAX_BYTES,
            backupCount=settings.LOG_FILE_BACKUP_COUNT,
            encoding='utf-8'
        )
        error_file_handler.setLevel(logging.ERROR)
        error_file_handler.setFormatter(PlainFormatter())  # 文件使用纯文本
        root_logger.addHandler(error_file_handler)

    # 配置 uvicorn 日志
    configure_uvicorn_logging()

    # 统一第三方库日志（清空 handler，防止重复输出）
    for lib in ["sqlalchemy.engine.Engine", "sqlalchemy", "uvicorn.access",
                "uvicorn",
                "aiomysql", "asyncpg", "redis", "httpx"]:
        logger = logging.getLogger(lib)
        logger.handlers.clear()
        logger.setLevel(logging.DEBUG)
        logger.propagate = True

    # 生产环境减少第三方库日志
    if settings.APP_ENV == "pro":
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("asyncio").setLevel(logging.WARNING)

    logging.info(
        f"日志系统初始化完成 - 环境: {settings.APP_ENV}, 级别: {settings.LOG_LEVEL}")


def configure_uvicorn_logging():
    """配置 Uvicorn 日志"""
    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_access_logger = logging.getLogger("uvicorn.access")

    # 清空 handler，使用统一格式
    uvicorn_logger.handlers.clear()
    uvicorn_access_logger.handlers.clear()
    uvicorn_logger.propagate = True
    uvicorn_access_logger.propagate = True

    if settings.ENABLE_ACCESS_LOG and settings.LOG_TO_FILE:
        # 访问日志单独文件（使用纯文本格式）
        access_handler = logging.handlers.RotatingFileHandler(
            filename=settings.ACCESS_LOG_PATH,
            maxBytes=settings.LOG_FILE_MAX_BYTES,
            backupCount=settings.LOG_FILE_BACKUP_COUNT,
            encoding='utf-8'
        )
        access_handler.setFormatter(PlainFormatter())  # 文件使用纯文本
        uvicorn_access_logger.addHandler(access_handler)


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的日志记录器"""
    return logging.getLogger(name)

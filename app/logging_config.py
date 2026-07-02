"""
RHMail AI — 结构化日志配置

提供 JSON 格式的结构化日志，便于日志收集和分析。

Copyright (c) 2026 RHCLOUD PTE LTD
Developer: TONGZHOU LIU
"""

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any

# 请求 ID 上下文变量，用于追踪请求链路
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class StructuredFormatter(logging.Formatter):
    """JSON 格式的结构化日志"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "request_id": request_id_var.get(),
        }
        
        # 添加异常信息
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info),
            }
        
        # 添加额外字段
        if hasattr(record, "extra_data"):
            log_data["data"] = record.extra_data
        
        return json.dumps(log_data, ensure_ascii=False)


class RequestIDFilter(logging.Filter):
    """为日志记录添加请求 ID"""
    
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def setup_logging(level: str = "INFO", json_format: bool = True) -> None:
    """配置日志系统
    
    Args:
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: 是否使用 JSON 格式（生产环境推荐 True）
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    
    # 清除现有处理器
    root_logger.handlers.clear()
    
    # 控制台处理器
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level.upper()))
    
    if json_format:
        formatter = StructuredFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s | request_id=%(request_id)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    
    handler.setFormatter(formatter)
    handler.addFilter(RequestIDFilter())
    root_logger.addHandler(handler)
    
    # 降低第三方库日志级别
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("google").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)


def generate_request_id() -> str:
    """生成唯一请求 ID"""
    return str(uuid.uuid4())[:8]


class LoggerAdapter(logging.LoggerAdapter):
    """日志适配器，支持额外上下文"""
    
    def process(self, msg: str, kwargs: Any) -> tuple[str, Any]:
        if "extra" not in kwargs:
            kwargs["extra"] = {}
        if "data" in kwargs:
            kwargs["extra"]["extra_data"] = kwargs.pop("data")
        return msg, kwargs


def get_logger(name: str) -> LoggerAdapter:
    """获取带适配器的日志记录器"""
    logger = logging.getLogger(name)
    return LoggerAdapter(logger, {})

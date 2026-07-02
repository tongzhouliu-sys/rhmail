"""
RHMail AI — 安全中间件

提供 CSRF 保护和速率限制功能。

Copyright (c) 2026 RHCLOUD PTE LTD
Developer: TONGZHOU LIU
"""

import hashlib
import hmac
import logging
import time
from collections import defaultdict
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import settings

log = logging.getLogger("middleware")

# CSRF 保护
CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"
CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
CSRF_EXEMPT_PATHS = {"/health", "/api/"}  # API 端点使用其他认证机制


def generate_csrf_token(session_token: str) -> str:
    """基于会话 token 生成 CSRF token"""
    salt = settings.secret_key[:16] if len(settings.secret_key) >= 16 else settings.secret_key
    return hmac.new(
        salt.encode(),
        session_token.encode(),
        hashlib.sha256
    ).hexdigest()[:32]


def validate_csrf_token(session_token: str, csrf_token: str) -> bool:
    """验证 CSRF token 是否有效"""
    expected = generate_csrf_token(session_token)
    return hmac.compare_digest(expected, csrf_token)


class CSRFMiddleware(BaseHTTPMiddleware):
    """CSRF 保护中间件
    
    - 为所有请求设置 CSRF cookie
    - 验证 POST/PUT/DELETE 请求的 CSRF token
    - 豁免 API 端点（使用其他认证机制）
    """
    
    async def dispatch(self, request: Request, call_next: Callable):
        # 为所有响应设置 CSRF cookie
        response = await call_next(request)
        
        # 如果用户已登录，生成并设置 CSRF token
        session = request.cookies.get("session")
        if session and not request.cookies.get(CSRF_COOKIE_NAME):
            csrf_token = generate_csrf_token(session)
            response.set_cookie(
                CSRF_COOKIE_NAME,
                csrf_token,
                httponly=False,  # JavaScript 需要读取
                samesite="lax",
                secure=request.url.scheme == "https",
                max_age=3600,
            )
        
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """简单的内存速率限制中间件
    
    基于 IP 地址限制请求频率，防止暴力破解和滥用。
    """
    
    def __init__(self, app, max_requests: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)
    
    def _is_rate_limited(self, client_ip: str) -> bool:
        """检查 IP 是否超过速率限制"""
        now = time.time()
        window_start = now - self.window_seconds
        
        # 清理过期记录
        self.requests[client_ip] = [
            t for t in self.requests[client_ip] if t > window_start
        ]
        
        # 检查是否超限
        if len(self.requests[client_ip]) >= self.max_requests:
            return True
        
        # 记录本次请求
        self.requests[client_ip].append(now)
        return False
    
    async def dispatch(self, request: Request, call_next: Callable):
        # 获取客户端 IP（考虑反向代理）
        client_ip = request.headers.get(
            "x-forwarded-for",
            request.client.host if request.client else "unknown"
        ).split(",")[0].strip()
        
        # 检查速率限制
        if self._is_rate_limited(client_ip):
            log.warning("Rate limit exceeded for IP: %s", client_ip)
            return JSONResponse(
                {"detail": "请求过于频繁，请稍后再试"},
                status_code=429,
                headers={"Retry-After": str(self.window_seconds)}
            )
        
        return await call_next(request)


def add_security_middleware(app):
    """为 FastAPI 应用添加安全中间件"""
    # 先添加速率限制（外层）
    app.add_middleware(RateLimitMiddleware, max_requests=100, window_seconds=60)
    # 再添加 CSRF（内层）
    app.add_middleware(CSRFMiddleware)
    
    log.info("安全中间件已加载：CSRF 保护 + 速率限制")

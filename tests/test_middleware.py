"""
RHMail AI — Middleware 模块测试

测试安全中间件功能。

Copyright (c) 2026 RHCLOUD PTE LTD
Developer: TONGZHOU LIU
"""

import pytest
from unittest.mock import Mock, AsyncMock
from fastapi import Request
from app.middleware import (
    CSRFMiddleware,
    RateLimitMiddleware,
    generate_csrf_token,
    validate_csrf_token,
)


class TestCSRFProtection:
    """测试 CSRF 保护"""

    def test_generate_csrf_token(self):
        """测试生成 CSRF token"""
        token = generate_csrf_token("test-session-token")
        assert token is not None
        assert isinstance(token, str)
        assert len(token) == 32

    def test_validate_csrf_token_valid(self):
        """测试验证有效 CSRF token"""
        session_token = "test-session"
        csrf_token = generate_csrf_token(session_token)
        assert validate_csrf_token(session_token, csrf_token) is True

    def test_validate_csrf_token_invalid(self):
        """测试验证无效 CSRF token"""
        assert validate_csrf_token("session1", "wrong-token") is False
        assert validate_csrf_token("session1", "session2") is False

    def test_csrf_token_consistency(self):
        """测试 CSRF token 一致性"""
        token1 = generate_csrf_token("same-session")
        token2 = generate_csrf_token("same-session")
        assert token1 == token2


class TestRateLimit:
    """测试速率限制"""

    def test_rate_limit_initialization(self):
        """测试速率限制初始化"""
        app = Mock()
        middleware = RateLimitMiddleware(app, max_requests=5, window_seconds=60)
        assert middleware.max_requests == 5
        assert middleware.window_seconds == 60

    def test_rate_limit_allows_requests(self):
        """测试允许正常请求"""
        app = Mock()
        middleware = RateLimitMiddleware(app, max_requests=10, window_seconds=60)
        
        # 前 10 个请求应该被允许
        for i in range(10):
            assert middleware._is_rate_limited("127.0.0.1") is False

    def test_rate_limit_blocks_excess(self):
        """测试阻止过量请求"""
        app = Mock()
        middleware = RateLimitMiddleware(app, max_requests=5, window_seconds=60)
        
        # 前 5 个请求允许
        for i in range(5):
            assert middleware._is_rate_limited("127.0.0.1") is False
        
        # 第 6 个请求应该被阻止
        assert middleware._is_rate_limited("127.0.0.1") is True

    def test_rate_limit_different_ips(self):
        """测试不同 IP 独立计数"""
        app = Mock()
        middleware = RateLimitMiddleware(app, max_requests=5, window_seconds=60)
        
        # IP1 使用 5 次
        for i in range(5):
            middleware._is_rate_limited("192.168.1.1")
        
        # IP2 应该不受影响
        assert middleware._is_rate_limited("192.168.1.2") is False

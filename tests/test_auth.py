"""
RHMail AI — Auth 模块测试

测试认证和会话管理功能。

Copyright (c) 2026 RHCLOUD PTE LTD
Developer: TONGZHOU LIU
"""

import pytest
from app.auth import make_cookie, _valid, COOKIE_NAME


class TestAuth:
    """测试认证功能"""

    def test_make_cookie(self):
        """测试生成 cookie"""
        token = make_cookie()
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_valid_token(self):
        """测试有效 token 验证"""
        token = make_cookie()
        assert _valid(token) is True

    def test_invalid_token(self):
        """测试无效 token"""
        assert _valid("invalid-token") is False
        assert _valid("") is False
        assert _valid(None) is False

    def test_expired_token(self):
        """测试过期 token（模拟）"""
        # 注意：实际过期测试需要等待或修改时间
        # 这里只测试格式错误的 token
        assert _valid("expired.fake.token") is False

    def test_cookie_name(self):
        """测试 cookie 名称常量"""
        assert COOKIE_NAME == "session"

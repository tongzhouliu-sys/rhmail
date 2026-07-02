"""
RHMail AI — Main API 端点测试

测试 FastAPI 路由和 API 端点。

Copyright (c) 2026 RHCLOUD PTE LTD
Developer: TONGZHOU LIU
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.auth import make_cookie


class TestHealthEndpoint:
    """测试健康检查端点"""

    def test_health_check(self):
        """测试健康检查"""
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestAuthentication:
    """测试认证端点"""

    def test_login_page(self):
        """测试登录页面"""
        client = TestClient(app)
        response = client.get("/login")
        assert response.status_code == 200
        assert "登录" in response.text

    def test_login_wrong_password(self):
        """测试错误密码"""
        client = TestClient(app)
        response = client.post("/login", data={"password": "wrong-password"})
        assert response.status_code == 401

    def test_login_correct_password(self):
        """测试正确密码"""
        client = TestClient(app)
        response = client.post(
            "/login",
            data={"password": "test-password"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "session" in response.cookies

    def test_logout(self):
        """测试登出"""
        client = TestClient(app)
        response = client.post("/logout", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"


class TestProtectedEndpoints:
    """测试受保护端点"""

    def test_dashboard_requires_auth(self):
        """测试仪表盘需要认证"""
        client = TestClient(app)
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == "/login"

    def test_dashboard_with_auth(self):
        """测试已认证的仪表盘访问"""
        client = TestClient(app)
        token = make_cookie()
        client.cookies.set("session", token)
        response = client.get("/")
        assert response.status_code == 200

    def test_emails_requires_auth(self):
        """测试邮件列表需要认证"""
        client = TestClient(app)
        response = client.get("/emails", follow_redirects=False)
        assert response.status_code == 307

    def test_api_requires_auth(self):
        """测试 API 需要认证"""
        client = TestClient(app)
        response = client.get("/api/emails")
        assert response.status_code == 401


class TestAPIEndpoints:
    """测试 API 端点"""

    def test_api_emails_list(self):
        """测试邮件列表 API"""
        client = TestClient(app)
        token = make_cookie()
        client.cookies.set("session", token)
        response = client.get("/api/emails")
        assert response.status_code == 200
        assert "items" in response.json()

    def test_api_toggle_read_not_found(self):
        """测试切换已读状态（不存在的邮件）"""
        client = TestClient(app)
        token = make_cookie()
        client.cookies.set("session", token)
        response = client.post("/api/emails/99999/toggle-read")
        assert response.status_code == 404

    def test_api_toggle_account_not_found(self):
        """测试切换账号状态（不存在的账号）"""
        client = TestClient(app)
        token = make_cookie()
        client.cookies.set("session", token)
        response = client.post("/api/accounts/99999/toggle")
        assert response.status_code == 404

    def test_api_delete_account_not_found(self):
        """测试删除账号（不存在的账号）"""
        client = TestClient(app)
        token = make_cookie()
        client.cookies.set("session", token)
        response = client.delete("/api/accounts/99999")
        assert response.status_code == 404

"""
RHMail AI — Config 模块测试

测试配置加载和环境变量处理。

Copyright (c) 2026 RHCLOUD PTE LTD
Developer: TONGZHOU LIU
"""

import pytest
import os
from unittest.mock import patch
from app.config import Settings, _get_database_url, _accounts_from_env


class TestDatabaseURL:
    """测试数据库 URL 处理"""

    def test_sqlite_absolute_path(self):
        """测试 SQLite 绝对路径"""
        with patch.dict(os.environ, {"DATABASE_URL": "sqlite:////app/data/app.db"}):
            url = _get_database_url()
            assert "sqlite" in url

    def test_sqlite_relative_path(self):
        """测试 SQLite 相对路径"""
        with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///./app.db"}):
            url = _get_database_url()
            assert "sqlite" in url

    def test_postgres_url_conversion(self):
        """测试 PostgreSQL URL 转换"""
        with patch.dict(os.environ, {"DATABASE_URL": "postgres://user:pass@host/db"}):
            url = _get_database_url()
            assert "postgresql+psycopg" in url

    def test_postgresql_url_conversion(self):
        """测试 PostgreSQL URL 转换（postgresql://）"""
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pass@host/db"}):
            url = _get_database_url()
            assert "postgresql+psycopg" in url


class TestAccountsFromEnv:
    """测试从环境变量加载账号"""

    def test_single_account(self):
        """测试单个账号"""
        env = {
            "GMAIL_EMAIL_1": "test@gmail.com",
            "GMAIL_REFRESH_TOKEN_1": "token123",
        }
        with patch.dict(os.environ, env):
            accounts = _accounts_from_env()
            assert len(accounts) == 1
            assert accounts[0]["email"] == "test@gmail.com"
            assert accounts[0]["refresh_token"] == "token123"

    def test_multiple_accounts(self):
        """测试多个账号"""
        env = {
            "GMAIL_EMAIL_1": "test1@gmail.com",
            "GMAIL_REFRESH_TOKEN_1": "token1",
            "GMAIL_EMAIL_2": "test2@gmail.com",
            "GMAIL_REFRESH_TOKEN_2": "token2",
        }
        with patch.dict(os.environ, env):
            accounts = _accounts_from_env()
            assert len(accounts) == 2

    def test_no_accounts(self):
        """测试无账号"""
        with patch.dict(os.environ, {}, clear=True):
            accounts = _accounts_from_env()
            assert len(accounts) == 0

    def test_incomplete_account(self):
        """测试不完整账号（只有 email 没有 token）"""
        env = {
            "GMAIL_EMAIL_1": "test@gmail.com",
            # 缺少 GMAIL_REFRESH_TOKEN_1
        }
        with patch.dict(os.environ, env):
            accounts = _accounts_from_env()
            assert len(accounts) == 0


class TestSettings:
    """测试 Settings 数据类"""

    def test_default_values(self):
        """测试默认值"""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            assert settings.fetch_interval_minutes == 30
            assert settings.digest_hour == 8
            assert settings.body_max_chars == 2000

    def test_custom_values(self):
        """测试自定义值"""
        env = {
            "FETCH_INTERVAL_MINUTES": "10",
            "DIGEST_HOUR": "9",
            "BODY_MAX_CHARS": "3000",
        }
        with patch.dict(os.environ, env):
            settings = Settings()
            assert settings.fetch_interval_minutes == 10
            assert settings.digest_hour == 9
            assert settings.body_max_chars == 3000

    def test_check_required_envs_missing(self):
        """测试检查缺失的环境变量"""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            # 应该记录警告但不抛出异常
            settings.check_required_envs()

    def test_whitelist_blacklist_parsing(self):
        """测试白名单/黑名单解析"""
        env = {
            "WHITELIST_FROM": "boss@company.com,manager@company.com",
            "BLACKLIST_FROM": "spam@example.com,noreply@",
        }
        with patch.dict(os.environ, env):
            settings = Settings()
            assert len(settings.whitelist_from) == 2
            assert "boss@company.com" in settings.whitelist_from
            assert len(settings.blacklist_from) == 2
            assert "spam@example.com" in settings.blacklist_from

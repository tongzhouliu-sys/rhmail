"""
RHMail AI — 测试配置与共享 fixtures

Copyright (c) 2026 RHCLOUD PTE LTD
Developer: TONGZHOU LIU
"""

import os
import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 设置测试环境变量（必须在导入 app 模块之前）
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"
os.environ["DASHBOARD_PASSWORD"] = "test-password"
os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["LLM_API_BASE"] = "http://test.local"
os.environ["LLM_API_KEY"] = "test-key"
os.environ["GOOGLE_CLIENT_ID"] = "test-client-id"
os.environ["GOOGLE_CLIENT_SECRET"] = "test-client-secret"

from app.models import Base
from app.db import SessionLocal, init_db, engine as app_engine


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """为应用引擎初始化测试数据库（供 FastAPI 端点测试使用）"""
    init_db()
    yield
    # 清理
    Base.metadata.drop_all(app_engine)
    if os.path.exists("./test.db"):
        os.remove("./test.db")


@pytest.fixture(scope="function")
def db_engine():
    """创建独立的测试数据库引擎（供模型测试使用）"""
    engine = create_engine("sqlite:///./test.db", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    yield engine
    # 不 drop_all，因为应用引擎可能还在使用


@pytest.fixture(scope="function")
def db_session(db_engine):
    """创建测试数据库会话"""
    TestingSession = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def sample_email_data():
    """示例邮件数据"""
    return {
        "message_id": "test-message-123",
        "from_email": "sender@example.com",
        "from_name": "Test Sender",
        "to_email": "recipient@example.com",
        "to_name": "Test Recipient",
        "subject": "Test Email Subject",
        "body_text": "This is a test email body with some content.",
        "body_html": "<html><body><p>This is a test email body with some content.</p></body></html>",
        "received_at": datetime.utcnow(),
        "list_unsubscribe": "",
    }


@pytest.fixture
def sample_analysis_result():
    """示例分析结果"""
    return {
        "category": "社交其他",
        "importance": 3,
        "one_line": "这是一封测试邮件",
        "summary": [
            {
                "type": "text",
                "title": "邮件内容",
                "text": "这是一封用于测试的邮件内容。"
            }
        ],
        "model_used": "test-model",
    }


@pytest.fixture
def mock_llm_response():
    """模拟 LLM 响应"""
    return {
        "category": "重要通知",
        "importance": 4,
        "one_line": "您的账户需要验证",
        "summary": [
            {
                "type": "facts",
                "title": "关键信息",
                "items": [
                    {"k": "验证截止日期", "v": "2026-07-15"},
                    {"k": "账户类型", "v": "标准账户"}
                ]
            },
            {
                "type": "list",
                "title": "需要完成的操作",
                "items": [
                    "登录账户设置页面",
                    "完成身份验证",
                    "更新联系信息"
                ]
            }
        ],
    }

"""
RHMail AI — Models 模块测试

测试 ORM 模型定义和数据库操作。

Copyright (c) 2026 RHCLOUD PTE LTD
Developer: TONGZHOU LIU
"""

import uuid
import pytest
from datetime import datetime
from app.models import GmailAccount, GmailMessage, AnalysisResult, DailyDigest


def _unique_email() -> str:
    return f"test-{uuid.uuid4().hex[:8]}@gmail.com"


class TestGmailAccount:
    """测试 Gmail 账号模型"""

    def test_create_account(self, db_session):
        """测试创建账号"""
        account = GmailAccount(
            email=_unique_email(),
            refresh_token="test-token",
            added_via="oauth",
        )
        db_session.add(account)
        db_session.commit()
        
        assert account.id is not None
        assert account.is_active is True
        assert account.needs_reauth is False

    def test_account_defaults(self, db_session):
        """测试账号默认值"""
        account = GmailAccount(
            email=_unique_email(),
            refresh_token="test-token",
        )
        db_session.add(account)
        db_session.commit()
        
        assert account.is_active is True
        assert account.needs_reauth is False
        assert account.added_via == "oauth"


class TestGmailMessage:
    """测试邮件消息模型"""

    def test_create_message(self, db_session):
        """测试创建消息"""
        account = GmailAccount(email=_unique_email(), refresh_token="test-token")
        db_session.add(account)
        db_session.commit()
        
        message = GmailMessage(
            account_id=account.id,
            message_id=f"msg-{uuid.uuid4().hex[:8]}",
            from_email="sender@example.com",
            subject="Test Subject",
            body_text="Test body",
            received_at=datetime.utcnow(),
        )
        db_session.add(message)
        db_session.commit()
        
        assert message.id is not None
        assert message.account_id == account.id
        assert message.is_read is False
        assert message.is_filtered is False

    def test_message_relationships(self, db_session):
        """测试消息关系"""
        email = _unique_email()
        account = GmailAccount(email=email, refresh_token="test-token")
        db_session.add(account)
        db_session.commit()
        
        message = GmailMessage(
            account_id=account.id,
            message_id=f"msg-{uuid.uuid4().hex[:8]}",
            from_email="sender@example.com",
            subject="Test",
        )
        db_session.add(message)
        db_session.commit()
        
        assert message.account.email == email


class TestAnalysisResult:
    """测试分析结果模型"""

    def test_create_analysis(self, db_session):
        """测试创建分析结果"""
        account = GmailAccount(email=_unique_email(), refresh_token="test-token")
        db_session.add(account)
        db_session.commit()
        
        message = GmailMessage(
            account_id=account.id,
            message_id=f"msg-{uuid.uuid4().hex[:8]}",
            from_email="sender@example.com",
        )
        db_session.add(message)
        db_session.commit()
        
        analysis = AnalysisResult(
            message_pk=message.id,
            category="重要通知",
            importance=4,
            one_line="重要通知",
            summary="这是摘要",
        )
        db_session.add(analysis)
        db_session.commit()
        
        assert analysis.id is not None
        assert analysis.importance == 4

    def test_analysis_defaults(self, db_session):
        """测试分析结果默认值"""
        account = GmailAccount(email=_unique_email(), refresh_token="test-token")
        db_session.add(account)
        db_session.commit()
        
        message = GmailMessage(
            account_id=account.id,
            message_id=f"msg-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(message)
        db_session.commit()
        
        analysis = AnalysisResult(message_pk=message.id)
        db_session.add(analysis)
        db_session.commit()
        
        assert analysis.category == "社交其他"
        assert analysis.importance == 1


class TestDailyDigest:
    """测试每日摘要模型"""

    def test_create_digest(self, db_session):
        """测试创建日报"""
        account = GmailAccount(email=_unique_email(), refresh_token="test-token")
        db_session.add(account)
        db_session.commit()
        
        digest = DailyDigest(
            date=f"2099-01-{uuid.uuid4().hex[:2]}",
            account_id=account.id,
            total_emails=10,
            important_emails=3,
            content_md="# 日报内容",
        )
        db_session.add(digest)
        db_session.commit()
        
        assert digest.id is not None
        assert digest.total_emails == 10
        assert digest.important_emails == 3

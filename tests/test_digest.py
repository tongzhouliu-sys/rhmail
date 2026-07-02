"""
RHMail AI — Digest 模块测试

测试每日摘要生成功能。

Copyright (c) 2026 RHCLOUD PTE LTD
Developer: TONGZHOU LIU
"""

import pytest
from datetime import datetime
from app.digest import render_markdown, CATEGORY_ORDER
from app.models import GmailMessage, AnalysisResult


class TestDigestRenderer:
    """测试摘要渲染器"""

    def test_render_markdown_empty(self):
        """测试空数据渲染"""
        md, total, important = render_markdown("2026-07-02", [])
        assert "2026-07-02" in md
        assert total == 0
        assert important == 0

    def test_render_markdown_with_messages(self, db_session):
        """测试有消息的渲染"""
        # 创建测试数据
        from app.models import GmailAccount
        account = GmailAccount(
            email="test@gmail.com",
            refresh_token="test-token",
        )
        db_session.add(account)
        db_session.commit()
        
        message = GmailMessage(
            account_id=account.id,
            message_id="msg-1",
            from_email="sender@example.com",
            subject="Test Subject",
            received_at=datetime.utcnow(),
        )
        db_session.add(message)
        db_session.commit()
        
        analysis = AnalysisResult(
            message_pk=message.id,
            category="重要通知",
            importance=4,
            one_line="重要通知内容",
            summary="这是摘要",
        )
        db_session.add(analysis)
        db_session.commit()
        
        rows = [(message, analysis)]
        md, total, important = render_markdown("2026-07-02", rows)
        
        assert "2026-07-02" in md
        assert total == 1
        assert important == 1
        assert "重要通知" in md
        assert "sender@example.com" in md

    def test_render_markdown_category_order(self):
        """测试分类顺序"""
        # CATEGORY_ORDER 应该包含所有 6 个分类
        assert len(CATEGORY_ORDER) == 6
        assert "紧急·需回复" in CATEGORY_ORDER
        assert "金融·账户告警" in CATEGORY_ORDER
        assert "法律·合同" in CATEGORY_ORDER
        assert "重要通知" in CATEGORY_ORDER
        assert "订阅·营销" in CATEGORY_ORDER
        assert "社交其他" in CATEGORY_ORDER

    def test_render_markdown_importance_counting(self, db_session):
        """测试重要性计数"""
        from app.models import GmailAccount
        account = GmailAccount(
            email="test@gmail.com",
            refresh_token="test-token",
        )
        db_session.add(account)
        db_session.commit()
        
        # 创建 3 封邮件，2 封重要
        messages_data = [
            ("msg-1", "重要通知", 4),
            ("msg-2", "普通通知", 2),
            ("msg-3", "紧急通知", 5),
        ]
        
        rows = []
        for msg_id, category, importance in messages_data:
            message = GmailMessage(
                account_id=account.id,
                message_id=msg_id,
                from_email="sender@example.com",
            )
            db_session.add(message)
            db_session.commit()
            
            analysis = AnalysisResult(
                message_pk=message.id,
                category=category,
                importance=importance,
                one_line=f"消息 {msg_id}",
            )
            db_session.add(analysis)
            db_session.commit()
            
            rows.append((message, analysis))
        
        md, total, important = render_markdown("2026-07-02", rows)
        
        assert total == 3
        assert important == 2  # importance >= 4 的有 2 封

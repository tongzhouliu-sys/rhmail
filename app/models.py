"""
RHMail AI — ORM 数据模型

定义 4 张核心表：
- GmailAccount: Gmail 账号凭证与同步状态
- GmailMessage: 邮件消息（含信头、清洗后正文）
- AnalysisResult: AI 分析结果（分类、评分、摘要、要点）
- DailyDigest: 每日 Markdown 摘要

Copyright (c) 2026 RHCLOUD PTE LTD
Developer: TONGZHOU LIU
"""

from datetime import datetime
from sqlalchemy import (
    Integer, String, Text, Boolean, DateTime, ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class GmailAccount(Base):
    __tablename__ = "gmail_accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    refresh_token: Mapped[str] = mapped_column(Text)
    last_history_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    needs_reauth: Mapped[bool] = mapped_column(Boolean, default=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    added_via: Mapped[str] = mapped_column(String(16), default="oauth")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    messages: Mapped[list["GmailMessage"]] = relationship(back_populates="account")


class GmailMessage(Base):
    __tablename__ = "gmail_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("gmail_accounts.id"))
    message_id: Mapped[str] = mapped_column(String(64))
    from_email: Mapped[str] = mapped_column(String(320), default="")
    from_name: Mapped[str] = mapped_column(String(320), default="")
    to_email: Mapped[str] = mapped_column(String(320), default="")
    to_name: Mapped[str] = mapped_column(String(320), default="")
    subject: Mapped[str] = mapped_column(Text, default="")
    body_text: Mapped[str] = mapped_column(Text, default="")
    received_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_filtered: Mapped[bool] = mapped_column(Boolean, default=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    account: Mapped["GmailAccount"] = relationship(back_populates="messages")
    analysis: Mapped["AnalysisResult"] = relationship(back_populates="message", uselist=False)
    __table_args__ = (
        UniqueConstraint("account_id", "message_id", name="uq_account_message"),
        Index("ix_received_at", "received_at"),
        Index("ix_account_id", "account_id"),
        Index("ix_account_received", "account_id", "received_at"),
    )


class AnalysisResult(Base):
    __tablename__ = "analysis_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_pk: Mapped[int] = mapped_column(ForeignKey("gmail_messages.id"), unique=True)
    category: Mapped[str] = mapped_column(String(32), default="社交其他")
    importance: Mapped[int] = mapped_column(Integer, default=1)
    one_line: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    model_used: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    message: Mapped["GmailMessage"] = relationship(back_populates="analysis")
    __table_args__ = (
        Index("ix_category", "category"),
        Index("ix_importance", "importance"),
    )


class DailyDigest(Base):
    __tablename__ = "daily_digests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[str] = mapped_column(String(10))
    account_id: Mapped[int] = mapped_column(ForeignKey("gmail_accounts.id"))
    total_emails: Mapped[int] = mapped_column(Integer, default=0)
    important_emails: Mapped[int] = mapped_column(Integer, default=0)
    content_md: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    account: Mapped["GmailAccount"] = relationship()
    __table_args__ = (UniqueConstraint("date", "account_id", name="uq_date_account"),)


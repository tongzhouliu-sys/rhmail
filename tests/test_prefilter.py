"""
RHMail AI — Prefilter 模块测试

测试规则预过滤功能。

Copyright (c) 2026 RHCLOUD PTE LTD
Developer: TONGZHOU LIU
"""

import pytest
from unittest.mock import patch
from app.prefilter import should_filter_out


class TestShouldFilterOut:
    """测试邮件预过滤规则"""

    @patch("app.prefilter.settings")
    def test_blacklist_match(self, mock_settings):
        """测试黑名单匹配"""
        mock_settings.blacklist_from = ["spam@example.com", "noreply@"]
        msg = {"from_email": "noreply@spam.com"}
        assert should_filter_out(msg) is True

    @patch("app.prefilter.settings")
    def test_blacklist_no_match(self, mock_settings):
        """测试黑名单不匹配"""
        mock_settings.blacklist_from = ["spam@example.com"]
        msg = {"from_email": "important@gmail.com"}
        assert should_filter_out(msg) is False

    @patch("app.prefilter.settings")
    def test_blacklist_case_insensitive(self, mock_settings):
        """测试黑名单大小写不敏感"""
        mock_settings.blacklist_from = ["SPAM@EXAMPLE.COM"]
        msg = {"from_email": "spam@example.com"}
        assert should_filter_out(msg) is True

    @patch("app.prefilter.settings")
    def test_blacklist_partial_match(self, mock_settings):
        """测试黑名单部分匹配"""
        mock_settings.blacklist_from = ["noreply@"]
        msg = {"from_email": "noreply@company.com"}
        assert should_filter_out(msg) is True

    @patch("app.prefilter.settings")
    def test_empty_blacklist(self, mock_settings):
        """测试空黑名单"""
        mock_settings.blacklist_from = []
        msg = {"from_email": "anyone@example.com"}
        assert should_filter_out(msg) is False

    @patch("app.prefilter.settings")
    def test_empty_from_email(self, mock_settings):
        """测试空发件人"""
        mock_settings.blacklist_from = ["spam@"]
        msg = {"from_email": ""}
        assert should_filter_out(msg) is False

    @patch("app.prefilter.settings")
    def test_none_from_email(self, mock_settings):
        """测试 None 发件人"""
        mock_settings.blacklist_from = ["spam@"]
        msg = {"from_email": None}
        assert should_filter_out(msg) is False

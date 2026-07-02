"""
RHMail AI — Cleaner 模块测试

测试 HTML 清洗、文本处理和摘要渲染功能。

Copyright (c) 2026 RHCLOUD PTE LTD
Developer: TONGZHOU LIU
"""

import pytest
from app.cleaner import (
    clean_body,
    clean_text,
    _html_to_text,
    _strip_quotes,
    _strip_signature,
    render_markdown,
    render_summary,
    summary_plaintext,
)


class TestCleanBody:
    """测试邮件正文清洗"""

    def test_clean_body_with_html(self):
        """测试 HTML 正文清洗"""
        html = "<html><body><p>重要内容</p><script>alert('xss')</script></body></html>"
        result = clean_body(None, html)
        assert "重要内容" in result
        assert "alert" not in result

    def test_clean_body_with_text(self):
        """测试纯文本正文清洗"""
        text = "这是一封测试邮件\n包含多行内容"
        result = clean_body(text, None)
        assert "测试邮件" in result
        assert "多行内容" in result

    def test_clean_body_truncation(self):
        """测试正文截断"""
        long_text = "a" * 5000
        result = clean_body(long_text, None)
        assert len(result) <= 2100  # 2000 + " …(截断)"


class TestCleanText:
    """测试文本清理"""

    def test_clean_text_removes_extra_spaces(self):
        """测试移除多余空格"""
        text = "hello    world"
        result = clean_text(text)
        assert result == "hello world"

    def test_clean_text_compresses_newlines(self):
        """测试压缩空行"""
        text = "line1\n\n\n\nline2"
        result = clean_text(text)
        assert result == "line1\n\nline2"

    def test_clean_text_empty_input(self):
        """测试空输入"""
        assert clean_text(None) == ""
        assert clean_text("") == ""


class TestHtmlToText:
    """测试 HTML 转文本"""

    def test_html_to_text_basic(self):
        """测试基本 HTML 转换"""
        html = "<p>段落1</p><p>段落2</p>"
        result = _html_to_text(html)
        assert "段落1" in result
        assert "段落2" in result

    def test_html_to_text_removes_scripts(self):
        """测试移除脚本标签"""
        html = "<p>内容</p><script>malicious()</script>"
        result = _html_to_text(html)
        assert "内容" in result
        assert "malicious" not in result

    def test_html_to_text_extracts_alt_text(self):
        """测试提取图片 alt 文本"""
        html = '<img src="image.jpg" alt="产品图片">'
        result = _html_to_text(html)
        assert "产品图片" in result


class TestStripQuotes:
    """测试引用文本移除"""

    def test_strip_quotes(self):
        """测试移除引用行"""
        text = "正文内容\n> 引用内容\n更多正文"
        result = _strip_quotes(text)
        assert "正文内容" in result
        assert "引用内容" not in result
        assert "更多正文" in result


class TestStripSignature:
    """测试签名移除"""

    def test_strip_signature_dash(self):
        """测试移除 -- 分隔的签名"""
        text = "邮件正文\n-- \n签名内容"
        result = _strip_signature(text)
        assert "邮件正文" in result
        assert "签名内容" not in result

    def test_strip_signature_sent_from(self):
        """测试移除 Sent from 签名"""
        text = "邮件正文\nSent from my iPhone"
        result = _strip_signature(text)
        assert "邮件正文" in result
        assert "iPhone" not in result


class TestRenderMarkdown:
    """测试 Markdown 渲染"""

    def test_render_markdown_headers(self):
        """测试标题渲染"""
        md = "# 标题1\n## 标题2\n### 标题3"
        result = render_markdown(md)
        assert "<h1>标题1</h1>" in result
        assert "<h2>标题2</h2>" in result
        assert "<h3>标题3</h3>" in result

    def test_render_markdown_bold_italic(self):
        """测试粗体和斜体"""
        md = "**粗体** *斜体*"
        result = render_markdown(md)
        assert "<strong>粗体</strong>" in result
        assert "<em>斜体</em>" in result

    def test_render_markdown_lists(self):
        """测试列表渲染"""
        md = "- 项目1\n- 项目2\n1. 数字1\n2. 数字2"
        result = render_markdown(md)
        assert "<ul>" in result
        assert "<li>项目1</li>" in result
        assert "<ol>" in result
        assert "<li>数字1</li>" in result


class TestRenderSummary:
    """测试摘要渲染"""

    def test_render_summary_structured(self):
        """测试结构化摘要渲染"""
        import json
        summary = json.dumps([
            {
                "type": "facts",
                "title": "关键信息",
                "items": [{"k": "金额", "v": "100元"}]
            }
        ], ensure_ascii=False)
        result = render_summary(summary)
        assert "关键信息" in result
        assert "金额" in result
        assert "100元" in result

    def test_render_summary_legacy(self):
        """测试旧版 Markdown 摘要"""
        summary = "**重要** 内容"
        result = render_summary(summary)
        assert "重要" in result


class TestSummaryPlaintext:
    """测试摘要纯文本化"""

    def test_summary_plaintext_structured(self):
        """测试结构化摘要转纯文本"""
        import json
        summary = json.dumps([
            {
                "type": "facts",
                "items": [{"k": "日期", "v": "2026-07-01"}]
            }
        ], ensure_ascii=False)
        result = summary_plaintext(summary)
        assert "日期" in result
        assert "2026-07-01" in result

    def test_summary_plaintext_legacy(self):
        """测试旧版摘要转纯文本"""
        summary = "多行\n内容"
        result = summary_plaintext(summary)
        assert "多行" in result
        assert "内容" in result

"""
RHMail AI — Analyzer 模块测试

测试 LLM 分析器和数据验证功能。

Copyright (c) 2026 RHCLOUD PTE LTD
Developer: TONGZHOU LIU
"""

import pytest
import json
from app.analyzer import _coerce_importance, _coerce_summary, _unwrap


class TestCoerceImportance:
    """测试重要性评分强制转换"""

    def test_valid_integer(self):
        """测试有效整数"""
        assert _coerce_importance(3) == 3
        assert _coerce_importance(1) == 1
        assert _coerce_importance(5) == 5

    def test_clamp_to_range(self):
        """测试范围限制"""
        assert _coerce_importance(0) == 1
        assert _coerce_importance(-1) == 1
        assert _coerce_importance(6) == 5
        assert _coerce_importance(100) == 5

    def test_string_conversion(self):
        """测试字符串转换"""
        assert _coerce_importance("3") == 3
        assert _coerce_importance("5") == 5

    def test_invalid_values(self):
        """测试无效值"""
        assert _coerce_importance(None) == 1
        assert _coerce_importance("invalid") == 1
        assert _coerce_importance([]) == 1


class TestCoerceSummary:
    """测试摘要内容强制转换"""

    def test_list_to_json(self):
        """测试列表转 JSON"""
        data = [{"type": "text", "text": "内容"}]
        result = _coerce_summary(data)
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed == data

    def test_dict_to_json(self):
        """测试字典转 JSON"""
        data = {"blocks": [{"type": "text"}]}
        result = _coerce_summary(data)
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed == data

    def test_string_passthrough(self):
        """测试字符串直接传递"""
        text = "这是摘要内容"
        result = _coerce_summary(text)
        assert result == text

    def test_none_handling(self):
        """测试 None 处理"""
        result = _coerce_summary(None)
        assert result == ""


class TestUnwrap:
    """测试 JSON 内容解包"""

    def test_plain_json(self):
        """测试纯 JSON"""
        s = '{"key": "value"}'
        assert _unwrap(s) == '{"key": "value"}'

    def test_json_with_code_block(self):
        """测试带代码块的 JSON"""
        s = '```json\n{"key": "value"}\n```'
        result = _unwrap(s)
        assert '{"key": "value"}' in result

    def test_json_with_whitespace(self):
        """测试带空白的 JSON"""
        s = '  \n  {"key": "value"}  \n  '
        result = _unwrap(s)
        assert result == '{"key": "value"}'

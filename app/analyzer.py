"""
RHMail AI — LLM 分析器

调用 OpenAI 兼容接口，对邮件进行智能分析：
- 6 类分类（紧急、金融、法律、重要通知、订阅、社交）
- 1-5 重要性评分
- 一句话摘要
- 结构化要点提取（JSON 格式）

Copyright (c) 2026 RHCLOUD PTE LTD
Developer: TONGZHOU LIU
"""

import json
import httpx
from app.config import settings

SYSTEM_PROMPT = """你是专业的邮件智能分析、翻译与结构化排版助手。请阅读邮件正文，将其核心内容翻译为中文并结构化，严格只返回如下 JSON（不要输出任何额外文字，也不要用 ```json 代码块包裹）:
{
  "category": "紧急·需回复 | 金融·账户告警 | 法律·合同 | 重要通知 | 订阅·营销 | 社交其他",
  "importance": 1,
  "one_line": "一句话核心概述(中文, 不超过50字, 不含换行)",
  "summary": [
    {"type": "facts", "title": "关键信息", "items": [{"k": "金额", "v": "$100.00"}, {"k": "截止日期", "v": "2026-07-01"}]},
    {"type": "list", "title": "活动商品", "items": ["商品 A 五折", "商品 B 买一送一"]},
    {"type": "text", "title": "说明", "text": "一段精炼的说明文字。"}
  ]
}

分类口径:
- 紧急·需回复: 个人/工作直发, 含截止日期或明确问句
- 金融·账户告警: 券商/银行/保证金/对账单等账户相关
- 法律·合同: 律所/法院/合同/传票/仲裁
- 重要通知: 学校/政府/账户安全/验证码
- 订阅·营销: 营销推广(通常已被预过滤)
- 社交其他: 其余
importance 为 1-5 的整数。

【summary 结构化规则 —— 必须严格遵守】
summary 是一个"内容块"数组。每个块为以下三种类型之一:
- facts: 关键数据键值对。把金额/日期/截止时间/折扣力度/账号/订单号/验证码等关键信息抽取为 items, 每项为 {"k": "标签", "v": "值"}。标签简短(2-6字), 值保留原始数字与单位。
- list: 并列要点/商品/操作步骤。items 为字符串数组, 每条一句话, 紧凑、不换行、不加序号符号(渲染端会自动加)。
- text: 无法结构化的说明性段落。text 为一段精炼文字, 段内不要堆叠多余换行。

排版与翻译要求:
1. 全部翻译为中文, 准确忠实, 不遗漏核心信息, 不臆造原文没有的内容。
2. 去除原文冗余空行、无意义换行, 以及纯装饰符号行(如 ═══ ─── *** ===== ☆☆☆ 等), 不要保留。
3. 关键数据优先用 facts 块前置; 多条并列信息用 list 块; 其余用 text 块。
4. 块的数量保持精简(通常 1-4 个), 不要为单条信息硬拆成多块, 也不要输出空块或空字段。
5. 每个块的 title 简短, 可省略(留空字符串)。整体应紧凑、清晰、阅读体验极佳。
6. 若为广告/营销邮件, 需将海报/Banner/促销文案一并中译, 用 facts(优惠力度/截止时间) + list(活动商品/行动按钮) 清晰呈现。
7. 若邮件内容极简(如纯验证码、单条通知), summary 可只含一个 facts 或 text 块。"""


_DEFAULT = {"category": "社交其他", "importance": 1, "one_line": "", "summary": ""}


def _coerce_importance(value) -> int:
    """Coerce the model's importance into an int clamped to 1-5."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = 1
    return max(1, min(5, n))


def _coerce_summary(value) -> str:
    """Store structured block arrays as a JSON string; pass plain strings through."""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value or "")


async def analyze(msg: dict) -> dict:
    user = (
        f"发件人:{msg.get('from_email', '?')}\n"
        f"主题:{msg.get('subject', '(无主题)')}\n"
        f"正文:\n{msg.get('body_text', '')}"
    )
    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "max_tokens": 1200,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    try:
        async with httpx.AsyncClient(base_url=settings.llm_api_base, timeout=40) as c:
            r = await c.post("/chat/completions", json=payload, headers=headers)
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
        data = json.loads(_unwrap(content))
        return {
            "category": str(data.get("category") or _DEFAULT["category"]),
            "importance": _coerce_importance(data.get("importance")),
            "one_line": str(data.get("one_line") or "").strip(),
            "summary": _coerce_summary(data.get("summary")),
            "model_used": settings.llm_model,
        }
    except Exception as e:
        d = dict(_DEFAULT)
        d["one_line"] = (msg.get("subject") or "")[:120]
        d["summary"] = f"(分析失败:{str(e)[:60]})"
        d["model_used"] = settings.llm_model
        return d


def _unwrap(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.strip("`")
        s = s[4:] if s.lower().startswith("json") else s
    return s.strip()

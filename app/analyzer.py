import json
import httpx
from app.config import settings

SYSTEM_PROMPT = """你是专业的邮件智能分析、翻译与排版助手。请阅读邮件正文，将其核心内容翻译并精炼为中文概要，仅返回如下 JSON，不要包含任何其它文字:
{
  "category": "紧急·需回复 | 金融·账户告警 | 法律·合同 | 重要通知 | 订阅·营销 | 社交其他",
  "importance": 1,
  "one_line": "一句话核心概述(中文)",
  "summary": "排版优良的邮件内容完整中文概要(请参照下方排版规则)"
}

分类口径:
- 紧急·需回复:个人/工作直发,含截止日期或明确问句
- 金融·账户告警:券商/银行/保证金/对账单等账户相关
- 法律·合同:律所/法院/合同/传票/仲裁
- 重要通知:学校/政府/账户安全/验证码
- 订阅·营销:营销推广(通常已被预过滤)
- 社交其他:其余
importance 为 1-5 的整数。

【排版规则 —— 必须严格遵守】
你在生成 summary 时，必须对原文进行智能排版重构，遵守以下规则:

1. 段落精简：将原文中大量冗余的连续空行、无意义换行全部去除。只在语义分段处保留一个换行。同一段内容不应被多次换行打断。
2. 逻辑分组：将相关内容聚合为逻辑段落。例如: 优惠信息归为一段、操作步骤归为一段、注意事项归为一段。段与段之间用一个空行分隔。
3. 列表化：当原文含有多条并列的信息(如商品列表、步骤说明、多个要点)时，使用简洁的序号列表(1. 2. 3.)或短横线列表(- )呈现，每条一行，紧凑排列。
4. 关键数据前置：金额、日期、截止时间、折扣力度等关键数据应放在显眼位置，不要埋在大段文字中。
5. 去装饰化：原文中纯粹用于视觉装饰的符号行(如 ═══、───、***、=====、☆☆☆ 等分隔线)一律去除，不要保留。
6. 保留语义：排版优化不得改变原文的任何核心语义和信息完整性。翻译须准确忠实。
7. 广告/营销邮件：若邮件为广告或营销推广，请务必将其中的图片海报/Banner文案/促销折扣等文本一并准确中译，清晰列出活动商品、优惠力度、截止时间或行动按钮等核心广告信息。
8. 最终输出的 summary 应是一段排版精炼、段落清晰、阅读体验极佳的中文概要文本。"""



_DEFAULT = {"category": "社交其他", "importance": 1, "one_line": "", "summary": ""}


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
        "max_tokens": 800,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    try:
        async with httpx.AsyncClient(base_url=settings.llm_api_base, timeout=40) as c:
            r = await c.post("/chat/completions", json=payload, headers=headers)
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
        data = json.loads(_unwrap(content))
        out = {**_DEFAULT, **{k: data.get(k, _DEFAULT[k]) for k in _DEFAULT}}
        out["importance"] = int(out["importance"])
        out["model_used"] = settings.llm_model
        return out
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

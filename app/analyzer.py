import json
import httpx
from app.config import settings

SYSTEM_PROMPT = """你是专业的邮件智能分析与翻译助手。请阅读邮件正文，将其核心内容翻译并精炼为中文概要，仅返回如下 JSON，不要包含任何其它文字:
{
  "category": "紧急·需回复 | 金融·账户告警 | 法律·合同 | 重要通知 | 订阅·营销 | 社交其他",
  "importance": 1,
  "one_line": "一句话核心概述(中文)",
  "summary": "邮件内容的完整中文概要(请准确将邮件核心内容翻译并梳理为中文。若邮件为广告或营销推广，请务必将其中的图片海报/Banner文案/促销折扣等文本一并准确中译，清晰列出活动商品、优惠力度、截止时间或行动按钮等核心广告信息)"
}
分类口径:
- 紧急·需回复:个人/工作直发,含截止日期或明确问句
- 金融·账户告警:券商/银行/保证金/对账单等账户相关
- 法律·合同:律所/法院/合同/传票/仲裁
- 重要通知:学校/政府/账户安全/验证码
- 订阅·营销:营销推广(通常已被预过滤)
- 社交其他:其余
importance 为 1-5 的整数。"""



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
        "max_tokens": 600,
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

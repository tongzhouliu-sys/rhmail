from app.config import settings


def should_filter_out(msg: dict) -> bool:
    frm = (msg.get("from_email") or "").lower()

    # 如果在显式发件人黑名单中，则过滤
    if any(b.lower() in frm for b in settings.blacklist_from):
        return True

    # 不再根据退订头(list_unsubscribe)或促销关键字自动过滤，分析全部邮件
    return False


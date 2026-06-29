import re
from app.config import settings


def should_filter_out(msg: dict) -> bool:
    frm = (msg.get("from_email") or "").lower()
    subject = (msg.get("subject") or "").lower()

    if any(w.lower() in frm for w in settings.whitelist_from):
        return False
    if any(b.lower() in frm for b in settings.blacklist_from):
        return True
    if msg.get("list_unsubscribe"):
        return True
    if re.search(r"(unsubscribe|newsletter|促销|优惠|限时|退订)", subject):
        return True
    return False

from collections import defaultdict

CATEGORY_ORDER = ["紧急·需回复", "金融·账户告警", "法律·合同", "重要通知", "订阅·营销", "社交其他"]


def render_markdown(day: str, rows: list) -> tuple[str, int, int]:
    by_cat = defaultdict(list)
    for m, a in rows:
        by_cat[a.category].append((m, a))
    total = len(rows)
    important = sum(1 for _, a in rows if a.importance >= 4)

    out = [f"# {day} 邮件日报", "", f"共 {total} 封,其中需关注 {important} 封。", ""]
    for cat in CATEGORY_ORDER:
        items = by_cat.get(cat)
        if not items:
            continue
        out.append(f"## {cat}({len(items)})")
        for m, a in sorted(items, key=lambda x: x[1].importance, reverse=True):
            out.append(f"- [{a.importance}] {a.one_line or m.subject} — {m.from_email}")
            if a.summary:
                out.append(f"  - {a.summary}")
        out.append("")
    return "\n".join(out), total, important

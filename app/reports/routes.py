"""Отчёты владельца: выручка, менеджеры, категории, воронка, источники, хиты.

Доступ: admin и manager. Период — месяц (?month=YYYY-MM, по умолчанию текущий).
"""
import calendar
from datetime import date

from flask import Blueprint, redirect, render_template, request, url_for

from .. import models as m
from ..auth import current_user, login_required
from sqlalchemy import case, func

reports_bp = Blueprint("reports", __name__)


def _period(month_str):
    """'2026-10' → (date, date) [start, end); некорректное → текущий месяц."""
    today = date.today()
    try:
        y, mth = (int(x) for x in month_str.split("-")[:2])
        if not (1 <= mth <= 12):
            raise ValueError
    except (ValueError, AttributeError):
        y, mth = today.year, today.month
    start = date(y, mth, 1)
    last_day = calendar.monthrange(y, mth)[1]
    if mth == 12:
        end = date(y + 1, 1, 1)
    else:
        end = date(y, mth + 1, 1)
    return start, end, last_day


@reports_bp.route("/")
@login_required
def index():
    user = current_user()
    if user is None or user.role not in ("admin", "manager"):
        return redirect(url_for("dashboard"))

    month_str = request.args.get("month", "")
    start, end, _ = _period(month_str)

    # ---- Периодовая выручка и заказы ----
    orders = (m.Order.query
              .filter(m.Order.order_date >= start, m.Order.order_date < end,
                      m.Order.status != "canceled")
              .all())
    revenue = sum(o.total for o in orders)

    # ---- По менеджерам (кто создал заказ) ----
    by_manager = {}
    for o in orders:
        who = None
        if o.created_by:
            u = m.User.query.get(o.created_by)
            who = u.full_name or u.username if u else "—"
        else:
            who = "Без менеджера"
        by_manager.setdefault(who, [0.0, 0])
        by_manager[who][0] += o.total
        by_manager[who][1] += 1
    manager_rows = sorted(
        ((k, v[0], v[1]) for k, v in by_manager.items()),
        key=lambda r: -r[1])

    # ---- По категориям (позиции заказов) ----
    by_cat = {}
    for o in orders:
        for it in o.items:
            name = "Услуги"
            if it.product and it.product.category:
                name = it.product.category.name
            by_cat.setdefault(name, 0.0)
            by_cat[name] += it.total
    cat_rows = sorted(by_cat.items(), key=lambda r: -r[1])

    # ---- Лиды периода ----
    leads = (m.Lead.query
             .filter(m.Lead.created_at >= start, m.Lead.created_at < end)
             .all())
    won = [l for l in leads if l.status == "won"]
    funnel = []
    for key, label in m.LEAD_STATUS_NAMES.items():
        n = len([l for l in leads if l.status == key])
        if n or key in ("new", "won", "lost"):
            funnel.append((key, label, n))
    by_source = {}
    for l in leads:
        by_source[l.source or "другое"] = by_source.get(l.source or "другое", 0) + 1
    source_rows = sorted(by_source.items(), key=lambda r: -r[1])

    # ---- Хиты (позиции заказов периода) ----
    hits = {}
    for o in orders:
        for it in o.items:
            name = it.product_name or (
                it.product.name if it.product else "—")
            hits.setdefault(name, [0.0, 0.0])
            hits[name][0] += it.qty
            hits[name][1] += it.total
    hit_rows = sorted(hits.items(), key=lambda r: -r[1][1])[:10]

    max_m = max((r[1] for r in manager_rows), default=0) or 1
    max_c = max((r[1] for r in cat_rows), default=0) or 1
    max_l = max((l for _, _, l in funnel), default=0) or 1
    max_h = max((r[1][1] for r in hit_rows), default=0) or 1

    def month_label(s):
        y, mth = (int(x) for x in s.split("-")[:2])
        return date(y, mth, 1).strftime("%B %Y").strip()

    return render_template(
        "reports.html",
        month_value=f"{start.year:04d}-{start.month:02d}",
        month_name=month_label(f"{start.year:04d}-{start.month:02d}"),
        revenue=revenue, orders_count=len(orders),
        leads_count=len(leads), won_count=len(won),
        manager_rows=manager_rows, cat_rows=cat_rows,
        funnel=funnel, source_rows=source_rows, hit_rows=hit_rows,
        max_m=max_m, max_c=max_c, max_l=max_l, max_h=max_h,
    )

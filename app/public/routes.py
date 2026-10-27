"""Публичные конторы: форма заявки из bio-ссылок и webhook приёма лидов.

Схема приёма лидов из Instagram/TikTok:
  1. Ссылка в bio → GET /lead?source=tiktok  (форма, без логина)
  2. Агрегатор комментариев/DM (360leads, Telemost, Parsegram и т.п.) →
     POST /webhooks/lead с заголовком X-Webhook-Token
"""
from flask import (
    Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for,
)

from .. import csrf, db
from .. import models as m
from ..crm.autopilot import apply_autopilot, normalize_phone

public_bp = Blueprint("public", __name__)
csrf.exempt(public_bp)  # анонимные формы: CSRF-токена нет, защита через токен/лимиты


def create_lead_from_data(data):
    """Создаёт заявку + карточку клиента из dict (форма или webhook),
    затем запускает автопилот (категория/бюджет/сроки, менеджер, задача)."""
    name = (data.get("name") or "").strip()
    phone = normalize_phone(data.get("phone") or "")
    source = (data.get("source") or "сайт").strip()
    if source not in m.LEAD_SOURCES:
        source = "другое"

    client = None
    if phone:
        client = m.Client.query.filter_by(phone=phone).first()
    if client is None and (name or phone):
        client = m.Client(
            name=name or phone,
            phone=phone,
            email=(data.get("email") or "").strip(),
        )
        db.session.add(client)
        db.session.flush()

    extra = []
    for key in ("utm_source", "utm_medium", "utm_campaign"):
        if data.get(key):
            extra.append(f"{key}={data[key]}")
    comment = (data.get("comment") or "").strip()
    if extra:
        comment = (comment + " · " if comment else "") + " ".join(extra)

    lead = m.Lead(
        client_id=client.id if client else None,
        source=source,
        need=(data.get("need") or "").strip(),
        comment=comment,
    )
    db.session.add(lead)

    if current_app.config.get("AUTOPILOT_ENABLED", True):
        apply_autopilot(lead)

    db.session.commit()
    return lead


@public_bp.route("/lead", methods=["GET", "POST"])
def lead_form():
    """Форма для ссылки в bio Instagram/TikTok. ?source=tiktok подставит источник."""
    if request.method == "POST":
        lead = create_lead_from_data(request.form.to_dict())
        flash("Заявка принята, мы перезвоним!", "success")
        return redirect(url_for("public.lead_done", lead_id=lead.id))
    source = request.args.get("source", "")
    if source not in m.LEAD_SOURCES:
        source = "tiktok"
    return render_template("public/lead_form.html", source=source, sources=m.LEAD_SOURCES)


@public_bp.route("/lead/done/<int:lead_id>")
def lead_done(lead_id):
    lead = m.Lead.query.get_or_404(lead_id)
    return render_template("public/lead_done.html", lead=lead)


@public_bp.route("/webhooks/lead", methods=["POST"])
def webhook_lead():
    token = current_app.config.get("WEBHOOK_TOKEN", "")
    if not token or request.headers.get("X-Webhook-Token") != token:
        return jsonify(ok=False, error="forbidden"), 403
    data = request.get_json(silent=True)
    if data is None:
        data = request.form.to_dict()
    if not (data.get("name") or data.get("phone")):
        return jsonify(ok=False, error="name или phone обязательны"), 400
    lead = create_lead_from_data(data)
    return jsonify(ok=True, lead_id=lead.id)

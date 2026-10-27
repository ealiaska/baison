"""Приём DM и комментариев Instagram через официальный Meta API.

Заменяет «ChatPlace» для Instagram: личка бизнес-аккаунта автоматически
попадает в baisón — заявка создаётся, квалификация (категория, бюджет,
сроки, кто решает) и менеджер — работой автопилота.

События, которые обрабатываются:
  * DM (messaging) — сообщение в личку. Первый текст → новая заявка,
    последующие — добавляются в комментарий той же открытой заявки
    (автопилот досвачивает пустые поля из нового текста).
  * Комментарии к постам (value) — если в тексте есть продукт
    (котёл/насос/плитка...) или намерение (цена, купить, монтаж, доставка)
    → заявка с источником instagram.

Клиент из Instagram идентифицируется псевдонимом ig:<ig_user_id>
(телефона у Meta в событии нет). Как только клиент сам напишет номер —
он заменяет псевдоним в карточке.

Настройка (developers.facebook.com → ваше приложение):
  * Webhooks → Instagram: Callback URL https://<домен>/webhooks/ig,
    Verify Token = IG_VERIFY_TOKEN из .env
  * Подписки: messages, comments
  * В .env: IG_ACCESS_TOKEN (с instagram_manage_messages), IG_USER_ID
"""
import json
import logging
import re

import requests
from flask import current_app, jsonify, request

from .. import db
from .. import models as m
from ..crm.autopilot import apply_autopilot, detect_categories, normalize_phone
from .routes import public_bp

log = logging.getLogger("baison.ig")

# Настоящий телефон в тексте: +7 / 8 / 9 + 10 цифр (РФ и Казахстан),
# не часть более длинной последовательности цифр
_REAL_PHONE_RE = re.compile(r"(?<!\d)(?:\+7|8|9)\d{10}(?!\d)")

# Намерение в комментарии под постом
_INTENT_RE = re.compile(
    r"сколько (стоит|цена|будет)|цен[аы]|стоимост|купить|заказат|срочн|"
    r"монтаж|установк|доставк|в наличии|наличии|как (купить|заказать)|"
    r"позвоните|перезвоните|св[яе]житесь|отправьт|напишите в личк",
    re.I,
)


def _extract_phone(text):
    """Первый настоящий телефон в тексте → '+7XXXXXXXXXX' (или '')."""
    mm = _REAL_PHONE_RE.search(text or "")
    return normalize_phone(mm.group(0)) if mm else ""


def _looks_salesy(text):
    """Комментарий похож на запрос: есть продукт, намерение или телефон."""
    if not (text or "").strip():
        return False
    if detect_categories(text):
        return True
    if _INTENT_RE.search(text):
        return True
    return bool(_extract_phone(text))


def _send_ig_reply(to_id, text):
    """Автоответ клиенту через Graph API. Возвращает ошибку (str) или None."""
    token = current_app.config.get("IG_ACCESS_TOKEN", "")
    our_id = current_app.config.get("IG_USER_ID", "")
    if not (token and our_id):
        return "IG_ACCESS_TOKEN/IG_USER_ID не настроены"
    try:
        r = requests.post(
            f"{current_app.config['IG_GRAPH_URL']}/{our_id}/messages",
            params={
                "recipient": json.dumps({"id": to_id}),
                "message": json.dumps({"text": text}),
                "access_token": token,
            },
            timeout=10,
        )
        if r.status_code != 200:
            return f"Graph API {r.status_code}: {r.text[:200]}"
        return None
    except requests.RequestException as e:
        return str(e)


def _record_message(client, text, source, permalink=""):
    """Добавляет сообщение клиента в открытую заявку (или создаёт новую).

    Возвращает (lead, created: bool).
    """
    body = text or ""
    if permalink:
        body = f"{body} · {permalink}".strip(" ·")
    lead = (
        m.Lead.query.filter(
            m.Lead.client_id == client.id,
            m.Lead.status.notin_(["won", "lost"]),
        )
        .order_by(m.Lead.id.desc())
        .first()
    )
    if lead is None:
        lead = m.Lead(client_id=client.id, source=source, comment=body)
        db.session.add(lead)
        db.session.flush()
        created = True
    else:
        lead.comment = f"{lead.comment or ''} | {body}".strip(" |")
        created = False

    if current_app.config.get("AUTOPILOT_ENABLED", True):
        apply_autopilot(lead)
    return lead, created


def _handle_dm(sender_id, text):
    """Одно входящее DM. Возвращает dict для журнала ответа вебхуку."""
    text = (text or "").strip()
    if not text:
        return {"skipped": "пустое сообщение"}

    pseudo = f"ig:{sender_id}"
    client = m.Client.query.filter_by(phone=pseudo).first()
    new_client = client is None
    if new_client:
        client = m.Client(name=f"IG {sender_id[-6:]}", phone=pseudo)
        db.session.add(client)
        db.session.flush()

    # Клиент мог написать реальный телефон — привязываем его к карточке
    real = _extract_phone(text)
    if real:
        other = m.Client.query.filter(
            m.Client.phone == real, m.Client.id != client.id).first()
        if other:
            # такой телефон уже есть — считаем это тем же клиентом
            if new_client:
                db.session.delete(client)
                db.session.flush()
            client = other
        elif client.phone == pseudo:
            client.phone = real

    lead, created = _record_message(client, text, source="instagram")

    reply_error = None
    if new_client and current_app.config.get("IG_AUTO_REPLY", True):
        reply_error = _send_ig_reply(
            sender_id, current_app.config.get("IG_REPLY_TEXT", ""))

    db.session.commit()
    return {
        "type": "dm",
        "lead_id": lead.id,
        "new_lead": created,
        "client_id": client.id,
        "reply_error": reply_error,
    }


def _handle_comment(frm, text, permalink=""):
    """Комментарий к посту. Возвращает dict для журнала."""
    sender_id = (frm or {}).get("id", "")
    username = (frm or {}).get("username", "")
    text = (text or "").strip()
    if not sender_id or not text:
        return {"skipped": "пустой комментарий"}
    if not _looks_salesy(text):
        return {"skipped": "нет запроса на покупку"}

    pseudo = f"ig:{sender_id}"
    client = m.Client.query.filter_by(phone=pseudo).first()
    if client is None:
        client = m.Client(name=f"@{username}" if username else f"IG {sender_id[-6:]}",
                          phone=pseudo)
        db.session.add(client)
        db.session.flush()

    lead, created = _record_message(client, text, source="instagram",
                                    permalink=permalink)
    db.session.commit()
    return {
        "type": "comment",
        "lead_id": lead.id,
        "new_lead": created,
        "client_id": client.id,
    }


# ------------------------------------------------------------------- роуты

@public_bp.route("/webhooks/ig", methods=["GET"])
def ig_verify():
    """Meta проверяет Callback URL: возвращаем hub.challenge."""
    verify = current_app.config.get("IG_VERIFY_TOKEN", "")
    if not verify or request.args.get("hub.verify_token") != verify:
        return jsonify(error="invalid verify token"), 403
    if request.args.get("hub.mode") != "subscribe":
        return jsonify(error="unknown mode"), 400
    return request.args.get("hub.challenge", ""), 200


@public_bp.route("/webhooks/ig", methods=["POST"])
def webhook_ig():
    """События Instagram: DM (messaging) и комментарии (value)."""
    payload = request.get_json(silent=True) or {}
    results = []
    for entry in payload.get("entry", []):
        for ev in entry.get("messaging", []):
            try:
                sender = (ev.get("sender") or {}).get("id", "")
                for msg in ev.get("messages", []):
                    if not sender:
                        continue
                    if msg.get("type") == "text":
                        text = msg.get("text", "")
                    else:
                        text = "(фото/видео/файл)"
                    results.append(_handle_dm(sender, text))
            except Exception as e:  # не роняем весь батч
                db.session.rollback()
                log.exception("ig dm error")
                results.append({"error": str(e)})
        for ev in entry.get("value", []):
            try:
                results.append(_handle_comment(
                    ev.get("from") or {}, ev.get("text", ""),
                    ev.get("permalink", "")))
            except Exception as e:
                db.session.rollback()
                log.exception("ig comment error")
                results.append({"error": str(e)})
    return jsonify(ok=True, processed=results)

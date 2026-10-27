"""Тесты приёма DM и комментариев Instagram (webhook /webhooks/ig)."""
import json

import pytest

from app import models as m

VERIFY = "ig-verify-token-123"


def post_ig(client, payload):
    return client.post("/webhooks/ig", json=payload)


def dm_payload(sender, text, our_id="999"):
    return {
        "object": "instagram",
        "entry": [{
            "id": our_id,
            "time": 1700000000,
            "messaging": [{
                "sender": {"id": sender},
                "recipient": {"id": our_id},
                "timestamp": 1700000000,
                "messages": [{"mid": "m_1", "timestamp": 1700000000,
                              "type": "text", "text": text}],
            }],
        }],
    }


def comment_payload(sender_id, username, text):
    return {
        "object": "instagram",
        "entry": [{
            "id": "999",
            "time": 1700000000,
            "value": [{
                "id": "c_1",
                "created_time": 1700000000,
                "from": {"id": sender_id, "username": username},
                "text": text,
                "parent_id": "p_1",
                "permalink": "https://www.instagram.com/p/ABC123/",
            }],
        }],
    }


def test_meta_verification(client, sample):
    client.application.config["IG_VERIFY_TOKEN"] = VERIFY
    r = client.get("/webhooks/ig", query_string={
        "hub.mode": "subscribe", "hub.verify_token": VERIFY,
        "hub.challenge": "42challenge42"})
    assert r.status_code == 200
    assert r.get_data(as_text=True) == "42challenge42"

    # чужой токен — отказ
    client.application.config["IG_VERIFY_TOKEN"] = VERIFY
    r = client.get("/webhooks/ig", query_string={
        "hub.mode": "subscribe", "hub.verify_token": "wrong",
        "hub.challenge": "x"})
    assert r.status_code == 403


def test_dm_creates_lead_with_autopilot(client, sample, monkeypatch):
    client.application.config["IG_VERIFY_TOKEN"] = VERIFY
    client.application.config["IG_AUTO_REPLY"] = True
    client.application.config["IG_ACCESS_TOKEN"] = "token"
    client.application.config["IG_USER_ID"] = "999"
    sent = []
    import app.public.instagram_dm as ig
    monkeypatch.setattr(ig.requests, "post",
                        lambda *a, **kw: sent.append(kw) or type("R", (), {"status_code": 200, "text": ""})())

    r = post_ig(client, dm_payload("555000111222",
                                   "Здравствуйте! Котёл газовый нужен, "
                                   "срочно, бюджет 150 тыс."))
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["processed"][0]["new_lead"] is True

    lead = m.Lead.query.first()
    assert lead is not None
    assert lead.source == "instagram"
    assert lead.need and "Котлы" in lead.need
    assert lead.budget == 150000
    assert lead.deadline == "asap"
    assert lead.client.phone == "ig:555000111222"
    # автоответ ушёл новому клиенту
    assert len(sent) == 1


def test_second_dm_appends_and_fills_empty(client, sample, monkeypatch):
    import app.public.instagram_dm as ig
    monkeypatch.setattr(ig.requests, "post",
                        lambda *a, **kw: type("R", (), {"status_code": 200, "text": ""})())

    post_ig(client, dm_payload("555000111222", "Привет"))
    first = m.Lead.query.first()
    assert first is not None
    clients_before = m.Client.query.count()

    r = post_ig(client, dm_payload("555000111222",
                                   "А ещё насос для скважины, "
                                   "решаем с женой, тел 89991234567"))
    assert r.status_code == 200
    assert m.Lead.query.count() == 1
    assert m.Client.query.count() == clients_before  # нового клиента нет

    lead = m.Lead.query.one()
    from app import db as _db
    _db.session.refresh(lead)
    assert "насос" in lead.comment
    assert lead.decider == "family"
    # реальный телефон из DM заменил псевдоним
    assert lead.client.phone == "+79991234567"


def test_dm_real_phone_merges_with_existing_client(client, sample, monkeypatch):
    import app.public.instagram_dm as ig
    monkeypatch.setattr(ig.requests, "post",
                        lambda *a, **kw: type("R", (), {"status_code": 200, "text": ""})())

    existing = sample["client"]  # телефон из sample
    r = post_ig(client, dm_payload("555000999888",
                                   f"Здравствуйте, насос. Тел {existing.phone}"))
    assert r.status_code == 200
    lead = m.Lead.query.filter_by(client_id=existing.id).first()
    assert lead is not None
    assert lead.source == "instagram"
    # временный ig-клиент не остался
    assert m.Client.query.filter_by(phone="ig:555000999888").first() is None


def test_comment_with_intent_creates_lead(client, sample, monkeypatch):
    import app.public.instagram_dm as ig
    monkeypatch.setattr(ig.requests, "post",
                        lambda *a, **kw: type("R", (), {"status_code": 200, "text": ""})())

    r = post_ig(client, comment_payload("777000333444", "vasya_77",
                                        "Сколько стоит котёл с монтажом?"))
    assert r.status_code == 200
    res = r.get_json()["processed"][0]
    assert res["new_lead"] is True
    lead = m.Lead.query.first()
    assert lead.client.name == "@vasya_77"
    assert "instagram.com/p/ABC123" in lead.comment
    assert "монтаж" in (lead.need or "").lower() or "Котлы" in (lead.need or "")


def test_comment_without_intent_ignored(client, sample, monkeypatch):
    import app.public.instagram_dm as ig
    monkeypatch.setattr(ig.requests, "post",
                        lambda *a, **kw: type("R", (), {"status_code": 200, "text": ""})())

    r = post_ig(client, comment_payload("777000333555", "fan_77",
                                        "Классный пост! ❤️"))
    assert r.status_code == 200
    res = r.get_json()["processed"][0]
    assert res["skipped"] == "нет запроса на покупку"
    assert m.Lead.query.count() == 0


def test_auto_reply_disabled(client, sample, monkeypatch):
    import app.public.instagram_dm as ig
    sent = []
    monkeypatch.setattr(ig.requests, "post",
                        lambda *a, **kw: sent.append(1) or type("R", (), {"status_code": 200, "text": ""})())
    client.application.config["IG_AUTO_REPLY"] = False

    r = post_ig(client, dm_payload("555000111333", "Котёл сколько стоит?"))
    assert r.status_code == 200
    assert sent == []
    lead = m.Lead.query.first()
    assert lead is not None


def test_media_message_marked(client, sample, monkeypatch):
    import app.public.instagram_dm as ig
    monkeypatch.setattr(ig.requests, "post",
                        lambda *a, **kw: type("R", (), {"status_code": 200, "text": ""})())
    payload = dm_payload("555000111444", "")
    payload["entry"][0]["messaging"][0]["messages"] = [
        {"mid": "m_2", "timestamp": 1, "type": "image"}]
    r = post_ig(client, payload)
    assert r.status_code == 200
    lead = m.Lead.query.first()
    assert lead is not None
    assert "фото" in lead.comment

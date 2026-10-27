import pytest

from app import models as m


def login(client):
    return client.post("/login", data={"username": "admin", "password": "admin123"})


def test_public_form_creates_lead(client, db):
    r = client.get("/lead?source=tiktok")
    assert r.status_code == 200
    # браузер шлёт скрытое поле source из формы
    r = client.post("/lead?source=tiktok", data={
        "name": "Аня", "phone": "+79991234567", "need": "Котёл 24 кВт",
        "source": "tiktok",
    })
    assert r.status_code == 302
    lead = m.Lead.query.first()
    assert lead is not None
    assert lead.source == "tiktok"
    assert lead.need == "Котёл 24 кВт"
    assert lead.client.name == "Аня"
    assert lead.client.phone == "+79991234567"


def test_unknown_source_becomes_dryoe(client, db):
    client.application.config["WEBHOOK_TOKEN"] = "t"
    r = client.post("/webhooks/lead",
                    json={"name": "Тест", "phone": "1", "source": "hacker"},
                    headers={"X-Webhook-Token": "t"})
    assert r.status_code == 200
    lead = m.Lead.query.first()
    assert lead.source == "другое"


def test_webhook_requires_token(client, db):
    client.application.config["WEBHOOK_TOKEN"] = "secret-token"
    r = client.post("/webhooks/lead", json={"name": "Вася", "phone": "555"})
    assert r.status_code == 403
    assert m.Lead.query.count() == 0
    # без токона в конфиге — тоже отказ
    client.application.config["WEBHOOK_TOKEN"] = ""
    r = client.post("/webhooks/lead", json={"name": "Вася", "phone": "555"},
                    headers={"X-Webhook-Token": "secret-token"})
    assert r.status_code == 403


def test_webhook_creates_lead_and_reuses_client(client, db):
    client.application.config["WEBHOOK_TOKEN"] = "secret-token"
    payload = {"name": "Вася", "phone": "+79995555555", "source": "instagram",
               "need": "Насос", "utm_source": "tiktok_ad"}
    r = client.post("/webhooks/lead", json=payload,
                    headers={"X-Webhook-Token": "secret-token"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True and body["lead_id"] == 1

    lead = m.Lead.query.first()
    assert lead.source == "instagram"
    assert lead.client.phone == "+79995555555"
    assert "utm_source=tiktok_ad" in lead.comment

    # второй webhook с тем же телефоном — тот же клиент
    r = client.post("/webhooks/lead", json=payload,
                    headers={"X-Webhook-Token": "secret-token"})
    assert m.Client.query.count() == 1
    assert m.Lead.query.count() == 2


def test_webhook_invalid_payload(client, db):
    client.application.config["WEBHOOK_TOKEN"] = "secret-token"
    r = client.post("/webhooks/lead", json={"foo": "bar"},
                    headers={"X-Webhook-Token": "secret-token"})
    assert r.status_code == 400


def test_heat_scoring(db):
    hot = m.Lead(budget=100000, deadline="asap", decider="self")
    warm = m.Lead(budget=15000, deadline="month", decider="family")
    cold = m.Lead(budget=0, deadline="planning", decider="")
    assert hot.heat == "hot"
    assert warm.heat in ("warm", "hot")
    assert cold.heat == "cold"
    assert hot.heat_name == "Горячий"


def test_lead_qualification_via_form(client, sample):
    login(client)
    client.post("/crm/leads/add", data={"name": "Борис", "phone": "+79990000009"})
    lead = m.Lead.query.first()
    client.post(f"/crm/leads/{lead.id}/update", data={
        "source": "tiktok", "deal_amount": 0, "comment": "",
        "need": "Котельная под ключ", "budget": 200000,
        "deadline": "asap", "decider": "self",
    })
    from app import db as _db
    _db.session.refresh(lead)
    assert lead.heat == "hot"
    assert lead.need == "Котельная под ключ"


def test_client_card_page_and_update(client, sample):
    login(client)
    r = client.get(f"/crm/clients/{sample['client'].id}")
    assert r.status_code == 200
    text = r.get_data(as_text=True)
    assert "Иван" in text

    r = client.post(f"/crm/clients/{sample['client'].id}/update", data={
        "name": "Иван Петров", "phone": "+79990000001", "email": "ivan@mail.ru",
        "company": "", "address": "ул. Ленина 1", "notes": "звонить после 18:00",
    })
    assert r.status_code == 302
    from app import db as _db
    _db.session.refresh(sample["client"])
    assert sample["client"].name == "Иван Петров"
    assert sample["client"].notes == "звонить после 18:00"

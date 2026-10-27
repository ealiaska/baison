import pytest

from app import db as _db
from app import models as m
from app.crm.autopilot import (
    apply_autopilot, detect_budget, detect_categories, detect_decider,
    detect_deadline, normalize_phone, pick_manager,
)


# ------------------------------------------------------------- телефон

@pytest.mark.parametrize("raw,expected", [
    ("8 999 123-45-67", "+79991234567"),
    ("+7(999)123-45-67", "+79991234567"),
    ("9991234567", "+79991234567"),
    ("7 999 123 45 67", "+79991234567"),
    ("+79991234567", "+79991234567"),
    ("89991234567", "+79991234567"),
])
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


def test_normalize_phone_empty():
    assert normalize_phone("") == ""
    assert normalize_phone(None) == ""
    assert normalize_phone("абв") == ""


# ------------------------------------------------------------- парсинг текста

def test_detect_budget():
    assert detect_budget("бюджет 50к") == 50000
    assert detect_budget("до 100000 руб") == 100000
    assert detect_budget("вложено 150 тыс") == 150000
    assert detect_budget("ориентир 100 000") == 100000
    assert detect_budget("котёл 24 кВт") is None
    assert detect_budget("просто смотрю") is None
    # берётся максимум, если несколько
    assert detect_budget("от 30 до 80 тыс") == 80000


def test_detect_deadline():
    assert detect_deadline("срочно нужен котёл") == "asap"
    assert detect_deadline("нужно сегодня") == "asap"
    assert detect_deadline("на этой неделе") == "asap"
    assert detect_deadline("просто смотрю варианты") == "planning"
    assert detect_deadline("не срочно") == "planning"
    assert detect_deadline("в этом месяце") == "month"
    assert detect_deadline("здравствуйте") is None


def test_detect_decider():
    assert detect_decider("для компании") == "company"
    assert detect_decider("ООО Ромашка") == "company"
    assert detect_decider("решим с женой") == "family"
    assert detect_decider("на дачу") == "family"
    assert detect_decider("беру себе") == "self"
    assert detect_decider("привет") is None


def test_detect_categories():
    assert "Котлы" in detect_categories("нужен газовый котёл")
    assert "Котлы" in detect_categories("котельная под ключ")
    cats = detect_categories("трубы и фитинги для отопления")
    assert "Трубы и фитинги" in cats
    cats = detect_categories("котёл и насос")
    assert "Котлы" in cats and "Насосы" in cats
    # «тепловой насос» → Котлы, а не Насосы
    assert "Насосы" not in detect_categories("тепловой насос")
    assert detect_categories("здравствуйте") == []


# ------------------------------------------------------------- автопилот

def _mgr(name, role=m.ROLE_MANAGER):
    return m.User(username=name, password_hash="x", full_name=name, role=role)


def test_apply_autopilot_fills_empty_fields(db):
    _db.session.add(_mgr("Менеджер А"))
    _db.session.add(m.Client(name="Оля", phone="89995556677"))
    lead = m.Lead(
        client_id=None,
        source="tiktok",
        comment="Котёл + монтаж, бюджет 50к, срочно, для компании",
    )
    client = m.Client.query.filter_by(phone="89995556677").first()
    lead.client_id = client.id
    _db.session.add(lead)
    _db.session.flush()

    actions = apply_autopilot(lead)
    _db.session.commit()

    assert "Котлы" in lead.need
    "монтаж" in lead.need
    assert float(lead.budget) == 50000
    assert lead.deadline == "asap"
    assert lead.decider == "company"
    assert lead.assigned_to is not None
    assert lead.autofill
    # телефон нормализован
    assert client.phone == "+79995556677"
    # задача на звонок создана
    task = m.Task.query.filter_by(lead_id=lead.id).first()
    assert task is not None
    assert task.kind == "звонок"
    assert task.status == "open"


def test_apply_autopilot_does_not_override_manual(db):
    _db.session.add(_mgr("Менеджер Б"))
    lead = m.Lead(
        source="сайт",
        comment="котёл, 10 тыс",
        budget=999999,          # менеджер уже внёс
        deadline="planning",    # и сроки
        decider="self",
    )
    _db.session.add(lead)
    _db.session.flush()
    apply_autopilot(lead, create_task=False)
    _db.session.commit()
    _db.session.refresh(lead)
    assert float(lead.budget) == 999999
    assert lead.deadline == "planning"
    assert lead.decider == "self"


def test_pick_manager_least_loaded(db):
    a = _mgr("Менеджер А")
    b = _mgr("Менеджер Б")
    _db.session.add_all([a, b])
    _db.session.commit()
    # у А уже есть открытая заявка
    _db.session.add(m.Lead(source="телефон", assigned_to=a.id, status="new"))
    _db.session.commit()
    picked = pick_manager()
    assert picked.id == b.id


def test_autopilot_disabled_via_config(app, db):
    app.config["AUTOPILOT_ENABLED"] = False
    c = app.test_client()
    c.post("/login", data={"username": "admin", "password": "admin123"})
    _db.session.add(_mgr("Менеджер В"))
    _db.session.commit()
    r = c.post("/crm/leads/add", data={
        "source": "телефон", "name": "Пётр", "phone": "89991112233",
        "comment": "котёл срочно 40к",
    })
    assert r.status_code == 302
    lead = m.Lead.query.order_by(m.Lead.id.desc()).first()
    assert lead.autofill == ""
    assert float(lead.budget) == 0
    assert lead.assigned_to is None


# ------------------------------------------------------------- сквозное: webhook

def test_webhook_full_autopilot(app, db):
    app.config["WEBHOOK_TOKEN"] = "t"
    c = app.test_client()
    _db.session.add(_mgr("Менеджер Г"))
    _db.session.commit()
    r = c.post("/webhooks/lead", json={
        "name": "Сергей",
        "phone": "8 999 222-33-44",
        "source": "tiktok",
        "need": "",
        "comment": "Газовый котёл + монтаж. Бюджет 80 тыс. Срочно. Решает компания.",
    }, headers={"X-Webhook-Token": "t"})
    assert r.status_code == 200
    lead = m.Lead.query.first()
    client = m.Client.query.filter_by(name="Сергей").first()
    assert client.phone == "+79992223344"
    assert "Котлы" in lead.need and "монтаж" in lead.need
    assert float(lead.budget) == 80000
    assert lead.deadline == "asap"
    assert lead.decider == "company"
    assert lead.assigned_to is not None
    assert m.Task.query.filter_by(lead_id=lead.id).count() == 1
    assert lead.heat in ("hot", "warm")

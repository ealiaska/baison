from werkzeug.security import generate_password_hash

from app import models as m


def login(client, username="admin", password="admin123"):
    return client.post("/login", data={"username": username, "password": password})


def test_reports_admin(client, sample):
    login(client)
    r = client.get("/reports/")
    assert r.status_code == 200
    h = r.get_data(as_text=True)
    assert "Отчёты" in h
    assert "Выручка" in h
    assert "по менеджерам" in h


def test_reports_period_param(client, sample):
    login(client)
    r = client.get("/reports/?month=2025-01")
    assert r.status_code == 200
    assert "2025-01" in r.get_data(as_text=True)


def test_reports_cashier_forbidden(client, sample, db):
    u = m.User(username="cash1",
               password_hash=generate_password_hash("pw12345"),
               role=m.ROLE_CASHIER, full_name="Кассир")
    db.session.add(u)
    db.session.commit()
    client.post("/logout")
    login(client, "cash1", "pw12345")
    r = client.get("/reports/")
    assert r.status_code == 302  # перекидывает на главную
    assert "/reports" not in r.headers["Location"]

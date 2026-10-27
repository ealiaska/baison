from app import models as m


def login(client, username="admin", password="admin123"):
    return client.post("/login", data={"username": username, "password": password},
                       follow_redirects=False)


def test_anonymous_redirects_to_login(client):
    r = client.get("/")
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_login_success(client):
    r = login(client)
    assert r.status_code == 302
    assert r.headers["Location"] == "/"
    page = client.get("/")
    assert page.status_code == 200
    assert "baisón" in page.get_data(as_text=True)


def test_login_wrong_password(client):
    r = client.post("/login", data={"username": "admin", "password": "bad"})
    assert r.status_code == 200
    assert "Неверный" in r.get_data(as_text=True)


def test_logout(client):
    login(client)
    client.get("/logout")
    r = client.get("/")
    assert r.status_code == 302


def test_lead_create_and_status(client, sample):
    login(client)
    r = client.post("/crm/leads/add", data={
        "name": "Пётр", "phone": "+79991112233", "source": "авито",
        "deal_amount": 50000, "comment": "Котёл и монтаж",
    })
    assert r.status_code == 302
    lead = m.Lead.query.first()
    assert lead.status == "new"
    assert lead.client.name == "Пётр"

    r = client.post(f"/crm/leads/{lead.id}/status", data={"status": "won"})
    assert r.status_code == 302
    from app import db
    db.session.refresh(lead)
    assert lead.status == "won"


def test_task_create_and_done(client, sample):
    login(client)
    client.post("/crm/leads/add", data={"name": "Оля", "phone": "+79990000002"})
    lead = m.Lead.query.first()
    r = client.post(f"/crm/leads/{lead.id}/tasks/add", data={
        "title": "Позвонить", "kind": "звонок",
    })
    assert r.status_code == 302
    task = m.Task.query.first()
    assert task.status == "open"
    client.post(f"/crm/tasks/{task.id}/done")
    from app import db
    db.session.refresh(task)
    assert task.status == "done"


def test_client_search(client, sample):
    login(client)
    r = client.get("/crm/clients?q=Иван")
    text = r.get_data(as_text=True)
    assert "Иван" in text


def test_users_admin_only(client, sample):
    login(client)
    r = client.get("/users")
    assert r.status_code == 200
    # кассир не может зайти
    cashier = m.User(username="cash", full_name="Касса")
    from werkzeug.security import generate_password_hash
    cashier.password_hash = generate_password_hash("secret1")
    cashier.role = m.ROLE_CASHIER
    from app import db
    db.session.add(cashier)
    db.session.commit()
    client.get("/logout")
    login(client, "cash", "secret1")
    r = client.get("/users")
    assert r.status_code == 403

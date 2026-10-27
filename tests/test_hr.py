from datetime import date, datetime, time, timedelta

from app import models as m


def login(client):
    return client.post("/login", data={"username": "admin", "password": "admin123"})


def make_employee(db, name="Пётр П.", shift="09:00", end="18:00", work_days="1111110"):
    emp = m.Employee(name=name, position="монтажник", shift_start=shift,
                     shift_end=end, work_days=work_days)
    db.session.add(emp)
    db.session.flush()
    return emp


def fake_now(monkeypatch, when):
    class FakeDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return when

    monkeypatch.setattr("app.hr.routes.datetime", FakeDT)


def test_employee_add(client, db):
    login(client)
    r = client.post("/hr/employees/add", data={
        "name": "Сидор", "position": "продавец", "shift_start": "10:00",
    })
    assert r.status_code == 302
    emp = m.Employee.query.filter_by(name="Сидор").first()
    assert emp is not None and emp.position == "продавец"


def test_punch_in_on_time(client, db, monkeypatch):
    login(client)
    emp = make_employee(db)
    today = date.today()
    monkeypatch.setattr("app.hr.routes.datetime",
                        type("FakeDT", (datetime,), {
                            "now": classmethod(lambda cls, tz=None: datetime.combine(today, time(9, 5)))
                        }))
    r = client.post(f"/hr/attendance/{emp.id}/in")
    assert r.status_code == 302
    rec = m.Attendance.query.filter_by(employee_id=emp.id).first()
    assert rec.status == "on_time"
    assert rec.actual_start == datetime.combine(today, time(9, 5))
    assert rec.planned_start == datetime.combine(today, time(9, 0))


def test_punch_in_late(client, db, monkeypatch):
    login(client)
    emp = make_employee(db)
    fake_now(monkeypatch, datetime.combine(date.today(), time(9, 30)))
    client.post(f"/hr/attendance/{emp.id}/in")
    rec = m.Attendance.query.filter_by(employee_id=emp.id).first()
    assert rec.status == "late"


def test_punch_out_requires_in(client, db):
    login(client)
    emp = make_employee(db)
    r = client.post(f"/hr/attendance/{emp.id}/out", follow_redirects=True)
    assert "Сначала отметьте приход" in r.get_data(as_text=True)


def test_full_day_and_report(client, db, monkeypatch):
    login(client)
    emp = make_employee(db)
    today = date.today()

    fake_now(monkeypatch, datetime.combine(today, time(9, 0)))
    client.post(f"/hr/attendance/{emp.id}/in")
    fake_now(monkeypatch, datetime.combine(today, time(18, 0)))
    client.post(f"/hr/attendance/{emp.id}/out")

    # прошлый рабочий день без отметки — считается отсутствием
    yesterday = today - timedelta(days=1)
    r = client.get("/hr/")
    text = r.get_data(as_text=True)
    assert "Пётр П." in text
    assert str(yesterday.strftime("%d.%m")) in text
    # вчера (рабочий день по маске) — метка отсутствия, сегодня — отметка
    rec = m.Attendance.query.filter_by(employee_id=emp.id).first()
    assert rec.actual_end is not None
    assert rec.status_name == "отработал"


def test_cashier_cannot_access_hr(client, db):
    from werkzeug.security import generate_password_hash

    cashier = m.User(username="cash2", full_name="Касса",
                     password_hash=generate_password_hash("secret1"),
                     role=m.ROLE_CASHIER)
    db.session.add(cashier)
    db.session.commit()
    client.get("/logout")
    client.post("/login", data={"username": "cash2", "password": "secret1"})
    r = client.get("/hr/")
    assert r.status_code == 403

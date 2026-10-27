import sys
sys.stdout.reconfigure(encoding="utf-8")

from app import create_app
from app import models as m

app = create_app()
app.config["WEBHOOK_TOKEN"] = "smoke-token"
c = app.test_client()

with app.app_context():
    # менеджер для назначения
    if not m.User.query.filter_by(username="m1").first():
        m.db.session.add(m.User(username="m1", password_hash="x",
                                full_name="Менеджер Один", role=m.ROLE_MANAGER))
        m.db.session.commit()

r = c.post("/webhooks/lead", json={
    "name": "Виктор",
    "phone": "8 999 333-44-55",
    "source": "tiktok",
    "comment": "Газовый котёл 24 кВт + монтаж отопления. Бюджет 150 тыс. Срочно, в этом месяце. Решаем с женой.",
}, headers={"X-Webhook-Token": "smoke-token"})
print("webhook:", r.status_code, r.get_json())

with app.app_context():
    lead = m.Lead.query.filter_by(source="tiktok").order_by(m.Lead.id.desc()).first()
    print("client phone:", lead.client.phone)
    print("need:       ", lead.need)
    print("budget:     ", lead.budget)
    print("deadline:   ", lead.deadline)
    print("decider:    ", lead.decider)
    print("manager:    ", lead.assignee.full_name if lead.assignee else None)
    print("heat:       ", lead.heat_name)
    print("autofill:   ", lead.autofill)
    task = m.Task.query.filter_by(lead_id=lead.id).first()
    print("task:       ", task.title, "|", task.kind, "|", task.due_at)

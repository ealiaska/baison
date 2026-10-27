import re

from app import create_app

app = create_app()
app.config["WEBHOOK_TOKEN"] = "smoke-token"
c = app.test_client()

# публичная форма
r = c.get("/lead?source=instagram")
print("public form:", r.status_code, "Отправить заявку" in r.text)
t = None
r = c.post("/lead?source=instagram",
           data={"name": "Мария", "phone": "+79997777777",
                 "need": "Котёл + монтаж", "source": "instagram"})
print("lead submit:", r.status_code, r.headers.get("Location"))

# webhook
r = c.post("/webhooks/lead", json={"name": "Дима", "phone": "+79996666666",
                                   "source": "tiktok", "need": "Насос"},
           headers={"X-Webhook-Token": "smoke-token"})
print("webhook:", r.status_code, r.get_json())
r = c.post("/webhooks/lead", json={"name": "Х", "phone": "1"},
           headers={"X-Webhook-Token": "wrong"})
print("webhook bad token:", r.status_code)

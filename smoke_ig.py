"""Живой smoke: Instagram-вебхук на production-сервере (waitress + PostgreSQL)."""
import json
import sys
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:5000"

# токен читаем из .env
tok = ""
with open(".env", "r", encoding="utf-8") as f:
    for line in f:
        if line.startswith("IG_VERIFY_TOKEN="):
            tok = line.strip().split("=", 1)[1]
print("0) verify token из .env:", tok[:8] + "..." if tok else "ПУСТО")

# 1) handshake, как делает Meta
q = urllib.parse.urlencode({
    "hub.mode": "subscribe", "hub.verify_token": tok, "hub.challenge": "SMOKE42"})
r = urllib.request.urlopen(BASE + "/webhooks/ig?" + q, timeout=10)
body = r.read().decode()
print("1) GET handshake:", r.status, "->", repr(body), "OK" if body == "SMOKE42" else "FAIL")

# 2) DM от «клиента»
payload = {
    "object": "instagram",
    "entry": [{
        "id": "7770000000000",
        "time": 1793000000,
        "messaging": [{
            "sender": {"id": "8881234567890"},
            "recipient": {"id": "7770000000000"},
            "timestamp": 1793000000,
            "messages": [{"mid": "m_smoke", "timestamp": 1793000000,
                          "type": "text",
                          "text": "Здравствуйте! Котёл газовый 24 кВт нужен, "
                                  "с монтажом, срочно. Бюджет 300 тыс. "
                                  "Решаем с женой. Тел 89992223344"}],
        }],
    }],
}
data = json.dumps(payload).encode()
req = urllib.request.Request(BASE + "/webhooks/ig", data=data,
                             headers={"Content-Type": "application/json"},
                             method="POST")
r = urllib.request.urlopen(req, timeout=15)
print("2) POST DM:", r.status, "->", r.read().decode()[:300])

# 3) комментарий к посту
payload2 = {
    "object": "instagram",
    "entry": [{
        "id": "7770000000000",
        "time": 1793000001,
        "value": [{
            "id": "c_smoke",
            "created_time": 1793000001,
            "from": {"id": "8889990001111", "username": "smoke_user"},
            "text": "Сколько стоит насос для скважины с доставкой?",
            "parent_id": "p_1",
            "permalink": "https://www.instagram.com/p/SMOKE/",
        }],
    }],
}
req = urllib.request.Request(BASE + "/webhooks/ig",
                             data=json.dumps(payload2).encode(),
                             headers={"Content-Type": "application/json"},
                             method="POST")
r = urllib.request.urlopen(req, timeout=15)
print("3) POST comment:", r.status, "->", r.read().decode()[:300])

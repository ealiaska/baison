"""Клиент amoCRM API v4.

Документация: https://www.amocrm.ru/developers
Авторизация: HTTP Basic (API-ключ и API-секрет из Настройки amoCRM).
"""
import base64

import requests


class AmoCrmError(Exception):
    pass


class AmoCrmClient:
    def __init__(self, base_url, api_key, api_secret, timeout=20):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        token = base64.b64encode(f"{api_key}:{api_secret}".encode()).decode()
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Basic {token}"
        self.session.headers["Content-Type"] = "application/json"

    def _get(self, path, params=None):
        r = self.session.get(self.base_url + "/api/v4" + path,
                             params=params, timeout=self.timeout)
        if r.status_code >= 400:
            raise AmoCrmError(f"amoCRM {r.status_code}: {r.text[:300]}")
        return r.json()

    def _post(self, path, payload):
        r = self.session.post(self.base_url + "/api/v4" + path,
                              json=payload, timeout=self.timeout)
        if r.status_code >= 400:
            raise AmoCrmError(f"amoCRM {r.status_code}: {r.text[:300]}")
        return r.json()

    def _put(self, path, payload):
        r = self.session.put(self.base_url + "/api/v4" + path,
                             json=payload, timeout=self.timeout)
        if r.status_code >= 400:
            raise AmoCrmError(f"amoCRM {r.status_code}: {r.text[:300]}")
        return r.json()

    # --- запросы ---

    def get_pipelines(self):
        return self._get("/pipelines").get("data", [])

    def get_stages(self, pipeline_id):
        return self._get(f"/pipelines/{pipeline_id}/stages").get("data", [])

    def get_deals(self, limit=100):
        return self._get("/deals", {"limit": limit, "with_deleted": "0"}).get("data", [])

    def get_contacts(self, limit=100):
        return self._get("/contacts", {"limit": limit}).get("data", [])

    # --- команды ---

    def create_deal(self, pipeline_id, stage_id, name,
                    company=None, phone=None, comment=None):
        deal = {"name": name, "pipeline_id": pipeline_id, "status_id": stage_id,
                "custom_fields": []}
        fields = deal["custom_fields"]
        if company:
            fields.append({"id": 5, "values": [{"name": company}]})
        if phone:
            fields.append({"id": 13, "values": [{"value": phone}]})
        if comment:
            fields.append({"id": 100132232, "values": [{"text": comment}]})
        return self._post("/deals", deal)

    def update_stage(self, deal_id, stage_id):
        return self._put(f"/deals/{deal_id}", {"status_id": stage_id})

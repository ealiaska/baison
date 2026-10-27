"""Клиент REST Web Services 1С.

Ожидает REST-сервис, настроенный на стороне 1С (внешние отчеты или
HTTP-сервис). Формат запросов/ответов зависит от того, как написан
REST-сервис в 1С — базовые методы ниже покрывают JSON; для XML есть post_xml.
"""
import base64

import requests


class OneCError(Exception):
    pass


class OneCClient:
    def __init__(self, base_url, username="", password="", timeout=30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        if username:
            token = base64.b64encode(f"{username}:{password}".encode()).decode()
            self.session.headers["Authorization"] = f"Basic {token}"

    def _request(self, method, path, params=None, json_body=None, xml_body=None):
        url = self.base_url + path
        headers = {}
        data = None
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        if xml_body is not None:
            headers["Content-Type"] = "application/xml"
            data = xml_body
        r = self.session.request(method, url, params=params, json=json_body,
                                 data=data, headers=headers, timeout=self.timeout)
        if r.status_code >= 400:
            raise OneCError(f"1С {r.status_code}: {r.text[:300]}")
        if xml_body is not None:
            return r.text
        try:
            return r.json()
        except ValueError:
            return {"raw": r.text}

    # --- базовый транспорт ---

    def get_json(self, path, params=None):
        return self._request("GET", path, params=params)

    def post_json(self, path, payload):
        return self._request("POST", path, json_body=payload)

    def post_xml(self, path, xml_text):
        return self._request("POST", path, xml_body=xml_text)

    # --- типовые сценарии (пути задаются в конфиге) ---

    def get_products(self, catalog_path):
        data = self.get_json(catalog_path)
        return data if isinstance(data, list) else data.get("data", data.get("rows", []))

    def get_stocks(self, stocks_path):
        data = self.get_json(stocks_path)
        return data if isinstance(data, list) else data.get("data", data.get("rows", []))

    def push_document(self, doc_path, xml_text):
        return self.post_xml(doc_path, xml_text)

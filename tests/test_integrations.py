from types import SimpleNamespace

import pytest

import app.integrations.amocrm as amocrm_mod
import app.integrations.ones as ones_mod
from app import models as m
from app.integrations import sync


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200
        self.text = str(payload)

    def json(self):
        return self._payload


def make_fake_session(handlers):
    class FakeSession:
        def __init__(self):
            self.headers = {}

        def _find(self, url):
            for pattern, payload in handlers.items():
                if pattern in url:
                    return FakeResponse(payload)
            raise AssertionError(f"неожиданный запрос {url}")

        def get(self, url, params=None, timeout=None):
            return self._find(url)

        def post(self, url, json=None, timeout=None, **kw):
            return self._find(url)

        def put(self, url, json=None, timeout=None, **kw):
            return FakeResponse({"ok": True})

        def request(self, method, url, **kw):
            if method == "GET":
                return self.get(url)
            if method == "POST":
                return self.post(url)
            return self._find(url)

    return FakeSession


def test_amocrm_client_auth_header(monkeypatch):
    fake_session = make_fake_session({})
    monkeypatch.setattr(amocrm_mod.requests, "Session", fake_session)
    c = amocrm_mod.AmoCrmClient("https://x.amocrm.ru", "key", "secret")
    import base64
    expected = "Basic " + base64.b64encode(b"key:secret").decode()
    assert c.session.headers["Authorization"] == expected


def test_sync_amocrm_leads(db, monkeypatch):
    handlers = {
        "/stages": {"data": [{"id": 1, "name": "Новая"}, {"id": 2, "name": "Сделка"}]},
        "/deals": {"data": [{"id": "100", "status_id": 2, "name": "Котёл 24 кВт"}]},
    }
    monkeypatch.setattr(amocrm_mod.requests, "Session", make_fake_session(handlers))
    client = amocrm_mod.AmoCrmClient("https://x.amocrm.ru", "k", "s")
    result = sync.sync_amocrm_leads(client, pipeline_id=1)
    assert result["created"] == 1
    lead = m.Lead.query.filter_by(amocrm_id="100").first()
    assert lead is not None
    assert lead.status == "won"

    # повторный импорт — обновление, а не дубль
    result2 = sync.sync_amocrm_leads(client, pipeline_id=1)
    assert result2["updated"] == 1
    assert m.Lead.query.count() == 1


def test_sync_1c_products_and_stocks(db, monkeypatch):
    handlers = {
        "nomenklatura": {"data": [
            {"sku": "P-1", "name": "Насос", "price": 5000},
            {"sku": "P-2", "name": "Труба", "price": "100.5"},
        ]},
        "ozh": {"data": [
            {"sku": "P-1", "qty": 7},
            {"sku": "P-2", "qty": 30},
        ]},
    }
    monkeypatch.setattr(ones_mod.requests, "Session", make_fake_session(handlers))
    client = ones_mod.OneCClient("https://ones.example", "u", "p")

    r1 = sync.sync_1c_products(client, "/rest/nomenklatura")
    assert r1["created"] == 2
    r2 = sync.sync_1c_products(client, "/rest/nomenklatura")
    assert r2["updated"] == 2

    rs = sync.sync_1c_stocks(client, "/rest/ozh")
    assert rs["updated"] == 2
    p1 = m.Product.query.filter_by(sku="P-1").first()
    stock = m.Stock.query.filter_by(product_id=p1.id).first()
    assert stock is not None and stock.qty == 7
    assert stock.storage.name == "1С (остатки)"


def test_onec_client_error(monkeypatch, db):
    class BoomSession:
        def __init__(self):
            self.headers = {}

        def request(self, *a, **kw):
            class R:
                status_code = 401
                text = "Unauthorized"
            return R()

    monkeypatch.setattr(ones_mod.requests, "Session", BoomSession)
    client = ones_mod.OneCClient("https://bad.example", "u", "p")
    with pytest.raises(ones_mod.OneCError):
        client.get_json("/rest/x")

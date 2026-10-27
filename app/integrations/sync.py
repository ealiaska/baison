"""Синхронизация: amoCRM и 1С → наша БД.

Импорты запускаются вручную с страницы /integrations (админ).
Позже сюда можно добавить автозапуск (celery / cron / планировщик).
"""
import logging

from .. import db
from .. import models as m

log = logging.getLogger(__name__)


def _amocrm_stage_to_status(name):
    n = (name or "").lower()
    if any(k in n for k in ("выигран", "сделан", "оплачен", "сделка")):
        return "won"
    if any(k in n for k in ("срыв", "потерян", "отказ", "закрыт")):
        return "lost"
    if any(k in n for k in ("переговор", "согласов", "подписан")):
        return "negotiation"
    if any(k in n for k in ("счет", "счёт", "оценк", "расч")):
        return "quoted"
    if any(k in n for k in ("связ", "контакт", "выясн", "договор")):
        return "contacted"
    return "new"


def sync_amocrm_leads(client, pipeline_id):
    """Читаем сделки из amoCRM и создаём/обновляем заявки."""
    stages = {s["id"]: s.get("name", "") for s in client.get_stages(pipeline_id)}
    deals = client.get_deals()
    created = updated = 0
    errors = []
    for deal in deals:
        try:
            stage_name = stages.get(deal.get("status_id"), "")
            status = _amocrm_stage_to_status(stage_name)
            lead = m.Lead.query.filter_by(amocrm_id=str(deal["id"])).first()
            if lead is None:
                lead = m.Lead(amocrm_id=str(deal["id"]), status=status,
                              comment=f"amoCRM: {deal.get('name', '')}")
                db.session.add(lead)
                created += 1
            else:
                lead.status = status
                updated += 1
        except Exception as e:  # noqa: BLE001
            errors.append(str(e))
            log.warning("amoCRM deal %s: %s", deal.get("id"), e)
    db.session.commit()
    return {"source": "amoCRM", "created": created, "updated": updated,
            "errors": errors[:20]}


def sync_1c_products(client, catalog_path):
    """Номенклатура из 1С → товары (по артикулу)."""
    rows = client.get_products(catalog_path)
    created = updated = 0
    errors = []
    for row in rows:
        try:
            sku = str(row.get("sku") or row.get("article") or row.get("nomenklatura", "")).strip()
            name = str(row.get("name") or row.get("naimenovanie", "")).strip()
            if not sku or not name:
                continue
            price = row.get("price") or row.get("tsena") or 0
            product = m.Product.query.filter_by(sku=sku).first()
            if product is None:
                product = m.Product(sku=sku, name=name)
                db.session.add(product)
                created += 1
            else:
                product.name = name
                updated += 1
            try:
                product.price = float(price)
            except (TypeError, ValueError):
                pass
        except Exception as e:  # noqa: BLE001
            errors.append(str(e))
    db.session.commit()
    return {"source": "1С (номенклатура)", "created": created, "updated": updated,
            "errors": errors[:20]}


def sync_1c_stocks(client, stocks_path):
    """Остатки из 1С → склад '1С' (абсолютные значения)."""
    rows = client.get_stocks(stocks_path)
    storage = m.Storage.query.filter_by(name="1С (остатки)").first()
    if storage is None:
        storage = m.Storage(name="1С (остатки)", type="склад")
        db.session.add(storage)
        db.session.flush()
    updated = 0
    errors = []
    for row in rows:
        try:
            sku = str(row.get("sku") or row.get("article") or "", ).strip()
            if not sku:
                continue
            product = m.Product.query.filter_by(sku=sku).first()
            if product is None:
                continue
            qty = int(float(row.get("qty") or row.get("ostatak") or 0))
            stock = db.session.get(m.Stock, (storage.id, product.id))
            if stock is None:
                stock = m.Stock(storage_id=storage.id, product_id=product.id, qty=qty)
                db.session.add(stock)
            else:
                stock.qty = qty
            updated += 1
        except Exception as e:  # noqa: BLE001
            errors.append(str(e))
    db.session.commit()
    return {"source": "1С (остатки)", "updated": updated, "errors": errors[:20]}

"""Генерирует демо-PDF счёта из тестовой БД и сохраняет в pdf_preview.pdf."""
import sys

sys.stdout.reconfigure(encoding="utf-8")
import app._env  # noqa

from app import create_app, db
from app import models as m
from app.sales.pdf import build_invoice_pdf

app = create_app("app.config.TestConfig")
with app.app_context():
    client = m.Client(name="Иванов Иван", phone="+7 775 123 45 67",
                      company="ЧП «ТеплоДом»")
    db.session.add(client)
    db.session.flush()
    inv = m.Invoice(number="СЧ-2026-0042", client_id=client.id,
                    status="sent", comment="Монтаж включён в стоимость.")
    db.session.add(inv)
    db.session.flush()
    for name, qty, price in [
        ("Котёл газовый Baxi Main 2400", 1, 385000),
        ("Монтаж котельной под ключ", 1, 240000),
        ("Труба ППР 32 мм, м.п.", 46, 850),
        ("Коллекторный узел 4 линии LUSSO", 1, 12400),
    ]:
        db.session.add(m.InvoiceItem(
            invoice_id=inv.id, product_name=name, qty=qty, price=price))
    db.session.commit()

    data = build_invoice_pdf(inv)
    open("pdf_preview.pdf", "wb").write(data)
    print("PDF size:", len(data), "bytes ->", "pdf_preview.pdf")

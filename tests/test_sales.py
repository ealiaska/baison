from app import models as m


def login(client):
    return client.post("/login", data={"username": "admin", "password": "admin123"})


def make_invoice(client, **extra):
    data = {
        "client_id": str(extra.get("client_id", "")),
        "lead_id": "",
        "product_id": [str(extra["product_id"]), ""],
        "product_name": ["", ""],
        "qty": ["2", ""],
        "price": ["900", ""],
    }
    return client.post("/sales/invoices/add", data=data)


def test_invoice_pdf(client, sample):
    login(client)
    r = make_invoice(client, client_id=sample["client"].id,
                     product_id=sample["product"].id)
    assert r.status_code == 302
    inv = m.Invoice.query.first()
    r = client.get(f"/sales/invoices/{inv.id}/pdf")
    assert r.status_code == 200
    assert r.content_type == "application/pdf"
    assert r.data.startswith(b"%PDF")
    assert len(r.data) > 1000  # не пустой файл


def test_invoice_flow(client, sample):
    login(client)
    r = make_invoice(client, client_id=sample["client"].id,
                     product_id=sample["product"].id)
    assert r.status_code == 302
    inv = m.Invoice.query.first()
    assert inv.total == 1800.0
    assert inv.number.startswith("СЧ-")

    r = client.post(f"/sales/invoices/{inv.id}/to-order")
    assert r.status_code == 302
    order = m.Order.query.first()
    assert order is not None
    assert order.total == 1800.0
    assert len(order.items) == 1
    from app import db
    db.session.refresh(inv)
    assert inv.status == "accepted"


def test_order_ship_flow(client, sample):
    login(client)
    # заявка, чтобы проверить закрытие сделки
    client.post("/crm/leads/add", data={
        "name": "Мария", "phone": "+79990000003",
    })
    lead = m.Lead.query.first()
    r = client.post("/sales/orders/add", data={
        "client_id": str(sample["client"].id),
        "lead_id": str(lead.id),
        "product_id": [str(sample["product"].id), ""],
        "product_name": ["", ""],
        "qty": ["4", ""],
        "price": ["1000", ""],
        "discount": ["0", ""],
    })
    assert r.status_code == 302
    order = m.Order.query.first()
    assert order.status == "draft"
    assert order.total == 4000.0

    r = client.post(f"/sales/orders/{order.id}/status", data={"status": "shipped"})
    assert r.status_code == 302
    from app import db
    db.session.refresh(order)
    db.session.refresh(lead)
    stock = m.Stock.query.get((sample["storage"].id, sample["product"].id))
    assert stock.qty == 1  # 5 - 4
    assert order.status == "shipped"
    assert lead.status == "won"


def test_order_ship_insufficient_stock_shows_error(client, sample):
    login(client)
    r = client.post("/sales/orders/add", data={
        "client_id": str(sample["client"].id),
        "product_id": [str(sample["product"].id)],
        "product_name": [""],
        "qty": ["99"],
        "price": ["1000"],
        "discount": ["0"],
    })
    assert r.status_code == 302
    order = m.Order.query.first()
    r = client.post(f"/sales/orders/{order.id}/status", data={"status": "shipped"},
                    follow_redirects=True)
    assert "Недостаточно остатка" in r.get_data(as_text=True)
    from app import db
    db.session.refresh(order)
    assert order.status == "draft"
    stock = m.Stock.query.get((sample["storage"].id, sample["product"].id))
    assert stock.qty == 5

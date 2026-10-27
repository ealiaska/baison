from datetime import date

from app import models as m
from app.utils import next_number, parse_items


def test_next_number_sequence(db):
    n1 = next_number("ЗК", m.Order, m.Order.number)
    year = date.today().year
    assert n1 == f"ЗК-{year}-0001"
    db.session.add(m.Order(number=n1))
    db.session.commit()
    n2 = next_number("ЗК", m.Order, m.Order.number)
    assert n2 == f"ЗК-{year}-0002"


def test_order_total(sample, db):
    order = m.Order(number="ЗК-2026-0001")
    item = m.OrderItem(product_id=sample["product"].id, qty=2, price=1000, discount=100)
    order.items.append(item)
    db.session.add(order)
    db.session.commit()
    assert order.total == 1800.0


def test_parse_items():
    class FakeForm(dict):
        def getlist(self, key):
            return list(self.get(key, []))

    form = FakeForm({
        "product_id": ["1", ""],
        "product_name": ["", "Монтаж"],
        "qty": ["2", "1"],
        "price": ["500", "3000"],
        "discount": ["", "0"],
    })
    items = parse_items(form)
    assert items == [(1, "", 2.0, 500.0, 0.0), (None, "Монтаж", 1.0, 3000.0, 0.0)]


def test_ship_reduces_stock(sample, db):
    from app.sales.routes import _ship

    order = m.Order(number="ЗК-2026-0001")
    db.session.add(order)
    db.session.flush()
    db.session.add(m.OrderItem(order_id=order.id, product_id=sample["product"].id,
                               qty=2, price=1000))
    db.session.commit()
    _ship(order)
    db.session.commit()
    stock = m.Stock.query.get((sample["storage"].id, sample["product"].id))
    assert stock.qty == 3
    moves = m.StockMovement.query.filter_by(kind="out").all()
    assert len(moves) == 1 and moves[0].qty == 2


def test_ship_insufficient_raises(sample, db):
    from app.sales.routes import _ship

    order = m.Order(number="ЗК-2026-0001")
    db.session.add(order)
    db.session.flush()
    db.session.add(m.OrderItem(order_id=order.id, product_id=sample["product"].id,
                               qty=99, price=1000))
    db.session.commit()
    try:
        _ship(order)
        assert False, "ожидалась ValueError"
    except ValueError:
        db.session.rollback()

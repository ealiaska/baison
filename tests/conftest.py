import pytest

from app import create_app
from app import db as _db


@pytest.fixture()
def app():
    return create_app("app.config.TestConfig")


@pytest.fixture()
def db(app):
    with app.app_context():
        yield _db


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def sample(db):
    """Админ, склад, категория, товар с остатком, клиент."""
    from app import models as m

    admin = m.User.query.filter_by(username="admin").first()
    storage = m.Storage.query.first()
    cat = m.Category.query.filter_by(name="Котлы").first()
    if cat is None:
        cat = m.Category(name="Котлы")
        _db.session.add(cat)
        _db.session.flush()
    product = m.Product(sku="K-100", name="Котёл 24 кВт", category_id=cat.id,
                        price=1000, cost=700, min_stock=1)
    _db.session.add(product)
    _db.session.flush()
    _db.session.add(m.Stock(storage_id=storage.id, product_id=product.id, qty=5))
    client_ = m.Client(name="Иван", phone="+79990000001")
    _db.session.add(client_)
    _db.session.commit()
    return {
        "admin": admin,
        "storage": storage,
        "product": product,
        "client": client_,
    }

from flask import Blueprint, flash, redirect, render_template, request, url_for

from .. import db
from .. import models as m
from ..auth import current_user, login_required

catalog_bp = Blueprint("catalog", __name__)


@catalog_bp.route("/products")
@login_required
def products():
    q = request.args.get("q", "").strip()
    cat = request.args.get("cat", type=int)
    query = m.Product.query
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(m.Product.name.like(like), m.Product.sku.like(like),
                                    m.Product.brand.like(like)))
    if cat:
        query = query.filter(m.Product.category_id == cat)
    return render_template(
        "catalog/products.html",
        products=query.order_by(m.Product.name).all(),
        categories=m.Category.query.order_by(m.Category.name).all(),
        q=q, cat=cat,
    )


@catalog_bp.route("/products/<int:product_id>")
@login_required
def product_detail(product_id):
    product = m.Product.query.get_or_404(product_id)
    movements = (
        m.StockMovement.query.filter_by(product_id=product.id)
        .order_by(m.StockMovement.created_at.desc()).limit(30).all()
    )
    return render_template(
        "catalog/product_detail.html",
        product=product,
        movements=movements,
        storages=m.Storage.query.all(),
        categories=m.Category.query.order_by(m.Category.name).all(),
    )


@catalog_bp.route("/products/add", methods=["POST"])
@login_required
def product_add():
    sku = request.form.get("sku", "").strip()
    name = request.form.get("name", "").strip()
    if not sku or not name:
        flash("Артикул и название обязательны", "error")
        return redirect(url_for("catalog.products"))
    if m.Product.query.filter_by(sku=sku).first():
        flash("Артикул уже занят", "error")
        return redirect(url_for("catalog.products"))
    p = m.Product(
        sku=sku, name=name,
        category_id=request.form.get("category_id", type=int) or None,
        brand=request.form.get("brand", "").strip(),
        unit=request.form.get("unit", "шт").strip() or "шт",
        price=request.form.get("price", 0),
        cost=request.form.get("cost", 0),
        min_stock=request.form.get("min_stock", 0, type=int),
    )
    db.session.add(p)
    db.session.commit()
    flash("Товар добавлен", "success")
    return redirect(url_for("catalog.products"))


@catalog_bp.route("/products/<int:product_id>/update", methods=["POST"])
@login_required
def product_update(product_id):
    p = m.Product.query.get_or_404(product_id)
    p.name = request.form.get("name", p.name).strip() or p.name
    p.category_id = request.form.get("category_id", type=int) or None
    p.brand = request.form.get("brand", "").strip()
    p.unit = request.form.get("unit", "шт").strip() or "шт"
    p.price = request.form.get("price", 0)
    p.cost = request.form.get("cost", 0)
    p.min_stock = request.form.get("min_stock", 0, type=int)
    db.session.commit()
    flash("Товар обновлён", "success")
    return redirect(url_for("catalog.product_detail", product_id=p.id))


@catalog_bp.route("/stocks")
@login_required
def stocks():
    storage_id = request.args.get("storage", type=int)
    stocks = (
        db.session.query(m.Stock, m.Product, m.Storage)
        .join(m.Product, m.Product.id == m.Stock.product_id)
        .join(m.Storage, m.Storage.id == m.Stock.storage_id)
    )
    if storage_id:
        stocks = stocks.filter(m.Storage.id == storage_id)
    rows = stocks.all()
    return render_template(
        "catalog/stocks.html",
        rows=rows,
        storages=m.Storage.query.order_by(m.Storage.name).all(),
        products=m.Product.query.order_by(m.Product.name).all(),
        storage_id=storage_id,
    )


@catalog_bp.route("/storages/add", methods=["POST"])
@login_required
def storage_add():
    name = request.form.get("name", "").strip()
    if name:
        db.session.add(m.Storage(
            name=name,
            type=request.form.get("type", "склад"),
            address=request.form.get("address", "").strip(),
        ))
        db.session.commit()
        flash("Склад добавлен", "success")
    return redirect(url_for("catalog.stocks"))


@catalog_bp.route("/movements/add", methods=["POST"])
@login_required
def movement_add():
    product_id = request.form.get("product_id", type=int)
    storage_id = request.form.get("storage_id", type=int)
    kind = request.form.get("kind", "in")
    qty = request.form.get("qty", 0, type=int)
    comment = request.form.get("comment", "").strip()
    product = db.session.get(m.Product, product_id)
    storage = db.session.get(m.Storage, storage_id)
    if not product or not storage or qty == 0 or kind not in ("in", "out", "correction"):
        flash("Некорректные данные движения", "error")
        return redirect(url_for("catalog.stocks"))
    stock = db.session.get(m.Stock, (storage_id, product_id))
    new_qty = (stock.qty if stock else 0) + (qty if kind in ("in", "correction") else -qty)
    if new_qty < 0:
        flash("Недостаточно остатка", "error")
        return redirect(url_for("catalog.stocks"))
    if stock:
        stock.qty = new_qty
    else:
        db.session.add(m.Stock(storage_id=storage_id, product_id=product_id, qty=new_qty))
    db.session.add(m.StockMovement(
        product_id=product_id, storage_id=storage_id, kind=kind, qty=qty,
        comment=comment, user_id=current_user().id if current_user() else None,
    ))
    db.session.commit()
    flash("Движение проведено", "success")
    return redirect(url_for("catalog.stocks"))

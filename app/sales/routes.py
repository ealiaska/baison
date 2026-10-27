from datetime import date, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for

from .. import db
from .. import models as m
from ..auth import current_user, login_required
from ..utils import next_number, parse_items

sales_bp = Blueprint("sales", __name__)


def _get_client_or_none(client_id):
    return db.session.get(m.Client, client_id) if client_id else None


# ---------- Счета ----------

@sales_bp.route("/invoices")
@login_required
def invoices():
    status = request.args.get("status", "")
    query = m.Invoice.query.order_by(m.Invoice.created_at.desc())
    if status in m.INVOICE_STATUSES:
        query = query.filter(m.Invoice.status == status)
    return render_template(
        "sales/invoices.html",
        invoices=query.all(),
        status=status,
        statuses=m.INVOICE_STATUS_NAMES,
    )


@sales_bp.route("/invoices/new")
@login_required
def invoice_new():
    return render_template(
        "sales/invoice_form.html",
        clients=m.Client.query.filter_by(is_active=True).order_by(m.Client.name).all(),
        leads=m.Lead.query.order_by(m.Lead.updated_at.desc()).limit(100).all(),
        products=m.Product.query.order_by(m.Product.name).all(),
    )


@sales_bp.route("/invoices/add", methods=["POST"])
@login_required
def invoice_add():
    client_id = request.form.get("client_id", type=int)
    lead_id = request.form.get("lead_id", type=int)
    items = parse_items(request.form)
    if not items:
        flash("Добавьте хотя бы одну позицию", "error")
        return redirect(url_for("sales.invoices"))
    inv = m.Invoice(
        number=next_number("СЧ", m.Invoice, m.Invoice.number),
        client_id=client_id,
        lead_id=lead_id,
        valid_until=date.today() + timedelta(days=14),
        comment=request.form.get("comment", "").strip(),
        created_by=current_user().id if current_user() else None,
    )
    db.session.add(inv)
    db.session.flush()
    for product_id, name, qty, price, _disc in items:
        db.session.add(m.InvoiceItem(
            invoice_id=inv.id, product_id=product_id,
            product_name=name, qty=qty, price=price,
        ))
    db.session.commit()
    flash(f"Счёт {inv.number} создан", "success")
    return redirect(url_for("sales.invoice_detail", invoice_id=inv.id))


@sales_bp.route("/invoices/<int:invoice_id>")
@login_required
def invoice_detail(invoice_id):
    inv = m.Invoice.query.get_or_404(invoice_id)
    return render_template(
        "sales/invoice_detail.html", inv=inv,
        statuses=m.INVOICE_STATUS_NAMES,
    )


@sales_bp.route("/invoices/<int:invoice_id>/status", methods=["POST"])
@login_required
def invoice_status(invoice_id):
    inv = m.Invoice.query.get_or_404(invoice_id)
    status = request.form.get("status", "")
    if status in m.INVOICE_STATUSES:
        inv.status = status
        if status == "sent":
            lead = inv.lead and db.session.get(m.Lead, inv.lead_id)
            if lead and lead.status == "new":
                lead.status = "quoted"
                lead.deal_amount = max(lead.deal_amount or 0, inv.total)
        db.session.commit()
        flash("Статус: " + m.INVOICE_STATUS_NAMES[status], "success")
    return redirect(url_for("sales.invoice_detail", invoice_id=inv.id))


@sales_bp.route("/invoices/<int:invoice_id>/to-order", methods=["POST"])
@login_required
def invoice_to_order(invoice_id):
    inv = m.Invoice.query.get_or_404(invoice_id)
    order = m.Order(
        number=next_number("ЗК", m.Order, m.Order.number),
        client_id=inv.client_id,
        lead_id=inv.lead_id,
        status="confirmed",
        comment=f"По счёту {inv.number}",
        created_by=current_user().id if current_user() else None,
    )
    db.session.add(order)
    db.session.flush()
    for item in inv.items:
        db.session.add(m.OrderItem(
            order_id=order.id, product_id=item.product_id,
            product_name=item.product_name, qty=item.qty, price=item.price,
        ))
    inv.status = "accepted"
    db.session.commit()
    flash(f"Заказ {order.number} создан по счёту {inv.number}", "success")
    return redirect(url_for("sales.order_detail", order_id=order.id))


# ---------- Заказы ----------

@sales_bp.route("/orders")
@login_required
def orders():
    status = request.args.get("status", "")
    query = m.Order.query.order_by(m.Order.created_at.desc())
    if status in m.ORDER_STATUSES:
        query = query.filter(m.Order.status == status)
    return render_template(
        "sales/orders.html",
        orders=query.all(),
        status=status,
        statuses=m.ORDER_STATUS_NAMES,
    )


@sales_bp.route("/orders/new")
@login_required
def order_new():
    return render_template(
        "sales/order_form.html",
        clients=m.Client.query.filter_by(is_active=True).order_by(m.Client.name).all(),
        leads=m.Lead.query.order_by(m.Lead.updated_at.desc()).limit(100).all(),
        products=m.Product.query.order_by(m.Product.name).all(),
    )


@sales_bp.route("/orders/add", methods=["POST"])
@login_required
def order_add():
    client_id = request.form.get("client_id", type=int)
    lead_id = request.form.get("lead_id", type=int)
    items = parse_items(request.form)
    if not items:
        flash("Добавьте хотя бы одну позицию", "error")
        return redirect(url_for("sales.orders"))
    order = m.Order(
        number=next_number("ЗК", m.Order, m.Order.number),
        client_id=client_id,
        lead_id=lead_id,
        comment=request.form.get("comment", "").strip(),
        created_by=current_user().id if current_user() else None,
    )
    if request.form.get("delivery_date"):
        try:
            order.delivery_date = date.fromisoformat(request.form["delivery_date"])
        except ValueError:
            pass
    db.session.add(order)
    db.session.flush()
    for product_id, name, qty, price, discount in items:
        db.session.add(m.OrderItem(
            order_id=order.id, product_id=product_id,
            product_name=name, qty=qty, price=price, discount=discount,
        ))
    db.session.commit()
    flash(f"Заказ {order.number} создан", "success")
    return redirect(url_for("sales.order_detail", order_id=order.id))


@sales_bp.route("/orders/<int:order_id>")
@login_required
def order_detail(order_id):
    order = m.Order.query.get_or_404(order_id)
    return render_template(
        "sales/order_detail.html", order=order,
        statuses=m.ORDER_STATUS_NAMES,
    )


def _ship(order):
    """Списать остатки по всем позициям; бросает ValueError при нехватке."""
    storage_ids = [s.id for s in m.Storage.query.all()]
    for item in order.items:
        if not item.product_id:
            continue
        need = int(item.qty)
        for sid in storage_ids:
            stock = db.session.get(m.Stock, (sid, item.product_id))
            if stock and stock.qty >= need:
                stock.qty -= need
                db.session.add(m.StockMovement(
                    product_id=item.product_id, storage_id=sid, kind="out",
                    qty=need, comment=f"Заказ {order.number}",
                    user_id=current_user().id if current_user() else None,
                ))
                need = 0
                break
        if need > 0:
            label = item.product_name or (item.product.name if item.product else str(item.product_id))
            raise ValueError(
                f"Недостаточно остатка: {label} (нужно {item.qty:g})"
            )


@sales_bp.route("/orders/<int:order_id>/status", methods=["POST"])
@login_required
def order_status(order_id):
    order = m.Order.query.get_or_404(order_id)
    status = request.form.get("status", "")
    if status not in m.ORDER_STATUSES:
        return redirect(url_for("sales.order_detail", order_id=order.id))
    if status == "shipped":
        if order.status not in ("draft", "confirmed", "paid"):
            flash("Отгрузить можно только незакрытый заказ", "error")
            return redirect(url_for("sales.order_detail", order_id=order.id))
        try:
            _ship(order)
        except ValueError as e:
            db.session.rollback()
            flash(str(e), "error")
            return redirect(url_for("sales.order_detail", order_id=order.id))
        lead = db.session.get(m.Lead, order.lead_id) if order.lead_id else None
        if lead:
            lead.status = "won"
            lead.deal_amount = max(lead.deal_amount or 0, order.total)
    order.status = status
    db.session.commit()
    flash("Статус: " + m.ORDER_STATUS_NAMES[status], "success")
    return redirect(url_for("sales.order_detail", order_id=order.id))

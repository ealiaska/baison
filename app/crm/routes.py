from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for

from .. import db
from .. import models as m
from ..auth import current_user, login_required
from .autopilot import apply_autopilot, normalize_phone

crm_bp = Blueprint("crm", __name__)


@crm_bp.route("/leads")
@login_required
def leads():
    status = request.args.get("status", "")
    query = m.Lead.query.order_by(m.Lead.updated_at.desc())
    if status in m.LEAD_STATUSES:
        query = query.filter(m.Lead.status == status)
    return render_template(
        "crm/leads.html",
        leads=query.all(),
        status=status,
        statuses=m.LEAD_STATUS_NAMES,
        sources=m.LEAD_SOURCES,
        clients=m.Client.query.filter_by(is_active=True).order_by(m.Client.name).all(),
        users=m.User.query.filter_by(is_active=True).order_by(m.User.username).all(),
    )


@crm_bp.route("/leads/add", methods=["POST"])
@login_required
def lead_add():
    client_id = request.form.get("client_id", type=int)
    phone = normalize_phone(request.form.get("phone", "").strip())
    name = request.form.get("name", "").strip()
    client = None
    if client_id:
        client = db.session.get(m.Client, client_id)
        if client and client.phone:
            client.phone = normalize_phone(client.phone)
    elif phone:
        client = m.Client.query.filter_by(phone=phone).first()
    if client is None and (name or phone):
        client = m.Client(name=name or phone, phone=phone)
        db.session.add(client)
        db.session.flush()

    lead = m.Lead(
        client_id=client.id if client else None,
        source=request.form.get("source", "телефон"),
        assigned_to=request.form.get("assigned_to", type=int) or None,
        deal_amount=request.form.get("deal_amount", 0),
        comment=request.form.get("comment", "").strip(),
    )
    db.session.add(lead)

    from flask import current_app
    if current_app.config.get("AUTOPILOT_ENABLED", True):
        apply_autopilot(lead)

    db.session.commit()
    flash("Заявка создана", "success")
    return redirect(url_for("crm.lead_detail", lead_id=lead.id))


@crm_bp.route("/leads/<int:lead_id>")
@login_required
def lead_detail(lead_id):
    lead = m.Lead.query.get_or_404(lead_id)
    return render_template(
        "crm/lead_detail.html",
        lead=lead,
        sources=m.LEAD_SOURCES,
        statuses=m.LEAD_STATUS_NAMES,
        deadline_choices=m.DEADLINE_CHOICES,
        decider_choices=m.DECIDER_CHOICES,
        tasks=m.Task.query.filter_by(lead_id=lead.id)
        .order_by(m.Task.due_at.asc().nulls_last()).all(),
        users=m.User.query.filter_by(is_active=True).order_by(m.User.username).all(),
        task_kinds=m.TASK_KINDS,
    )


@crm_bp.route("/leads/<int:lead_id>/update", methods=["POST"])
@login_required
def lead_update(lead_id):
    lead = m.Lead.query.get_or_404(lead_id)
    lead.source = request.form.get("source", lead.source)
    lead.assigned_to = request.form.get("assigned_to", type=int) or None
    lead.deal_amount = request.form.get("deal_amount", 0)
    lead.comment = request.form.get("comment", "").strip()
    # квалификация
    lead.need = request.form.get("need", "").strip()
    lead.budget = request.form.get("budget", 0)
    lead.deadline = request.form.get("deadline", "")
    lead.decider = request.form.get("decider", "")
    lead.updated_at = datetime.now()
    db.session.commit()
    flash("Заявка обновлена", "success")
    return redirect(url_for("crm.lead_detail", lead_id=lead.id))


@crm_bp.route("/leads/<int:lead_id>/status", methods=["POST"])
@login_required
def lead_status(lead_id):
    lead = m.Lead.query.get_or_404(lead_id)
    status = request.form.get("status", "")
    if status in m.LEAD_STATUSES:
        lead.status = status
        lead.updated_at = datetime.now()
        db.session.commit()
        flash(f"Этап: {m.LEAD_STATUS_NAMES[status]}", "success")
    return redirect(url_for("crm.lead_detail", lead_id=lead.id))


@crm_bp.route("/leads/<int:lead_id>/tasks/add", methods=["POST"])
@login_required
def task_add(lead_id):
    lead = m.Lead.query.get_or_404(lead_id)
    title = request.form.get("title", "").strip()
    if not title:
        flash("Название задачи обязательно", "error")
        return redirect(url_for("crm.lead_detail", lead_id=lead.id))
    due = request.form.get("due_at", "").strip()
    due_at = None
    if due:
        for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                due_at = datetime.strptime(due, fmt)
                break
            except ValueError:
                continue
    db.session.add(m.Task(
        title=title,
        kind=request.form.get("kind", "звонок"),
        due_at=due_at,
        lead_id=lead.id,
        client_id=lead.client_id,
        assigned_to=request.form.get("assigned_to", type=int) or None,
        created_by=current_user().id if current_user() else None,
    ))
    db.session.commit()
    flash("Задача создана", "success")
    return redirect(url_for("crm.lead_detail", lead_id=lead.id))


@crm_bp.route("/tasks/<int:task_id>/<action>", methods=["POST"])
@login_required
def task_action(task_id, action):
    task = m.Task.query.get_or_404(task_id)
    if action == "done":
        task.status = "done"
        task.done_at = datetime.now()
    elif action == "canceled":
        task.status = "canceled"
    db.session.commit()
    return redirect(request.form.get("next") or url_for("crm.leads"))


@crm_bp.route("/tasks")
@login_required
def tasks():
    status = request.args.get("status", "open")
    query = m.Task.query
    if status in m.TASK_STATUSES:
        query = query.filter(m.Task.status == status)
    return render_template(
        "crm/tasks.html",
        tasks=query.order_by(m.Task.due_at.asc().nulls_last()).all(),
        status=status,
        statuses=m.TASK_STATUS_NAMES,
    )


@crm_bp.route("/clients")
@login_required
def clients():
    q = request.args.get("q", "").strip()
    query = m.Client.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(m.Client.name.like(like), m.Client.phone.like(like),
                   m.Client.company.like(like))
        )
    return render_template("crm/clients.html", clients=query.order_by(m.Client.name).all(), q=q)


@crm_bp.route("/clients/<int:client_id>")
@login_required
def client_detail(client_id):
    client = m.Client.query.get_or_404(client_id)
    leads = m.Lead.query.filter_by(client_id=client.id)
    orders = m.Order.query.filter_by(client_id=client.id).order_by(m.Order.created_at.desc()).all()
    invoices = m.Invoice.query.filter_by(client_id=client.id).order_by(m.Invoice.created_at.desc()).all()
    tasks = (m.Task.query.filter(m.Task.client_id == client.id)
             .filter(m.Task.status == "open").all())
    return render_template("crm/client_detail.html",
                           client=client, leads=leads, orders=orders,
                           invoices=invoices, tasks=tasks)


@crm_bp.route("/clients/<int:client_id>/update", methods=["POST"])
@login_required
def client_update(client_id):
    client = m.Client.query.get_or_404(client_id)
    client.name = request.form.get("name", client.name).strip() or client.name
    client.phone = request.form.get("phone", "").strip()
    client.email = request.form.get("email", "").strip()
    client.company = request.form.get("company", "").strip()
    client.address = request.form.get("address", "").strip()
    client.notes = request.form.get("notes", "").strip()
    db.session.commit()
    flash("Карточка клиента обновлена", "success")
    return redirect(url_for("crm.client_detail", client_id=client.id))


@crm_bp.route("/clients/add", methods=["POST"])
@login_required
def client_add():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Имя обязательно", "error")
        return redirect(url_for("crm.clients"))
    db.session.add(m.Client(
        name=name,
        phone=request.form.get("phone", "").strip(),
        email=request.form.get("email", "").strip(),
        company=request.form.get("company", "").strip(),
        address=request.form.get("address", "").strip(),
        notes=request.form.get("notes", "").strip(),
    ))
    db.session.commit()
    flash("Клиент добавлен", "success")
    return redirect(url_for("crm.clients"))

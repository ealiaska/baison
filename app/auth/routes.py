from flask import (
    Blueprint, flash, redirect, render_template, request, session, url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from .. import db
from .. import models as m
from . import login_required, role_required

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = m.User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            if not user.is_active:
                error = "Пользователь заблокирован"
            else:
                session["user_id"] = user.id
                nxt = session.pop("_next", "/")
                return redirect(nxt)
        else:
            error = "Неверный логин или пароль"
    return render_template("auth/login.html", error=error)


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


# ---------- Пользователи (только админ) ----------

@auth_bp.route("/users")
@role_required(m.ROLE_ADMIN)
def users():
    return render_template("users.html", users=m.User.query.order_by(m.User.username).all())


@auth_bp.route("/users/add", methods=["POST"])
@role_required(m.ROLE_ADMIN)
def user_add():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    full_name = request.form.get("full_name", "").strip()
    role = request.form.get("role", m.ROLE_MANAGER)
    if not username or len(password) < 6:
        flash("Логин обязателен, пароль не короче 6 символов", "error")
        return redirect(url_for("auth.users"))
    if m.User.query.filter_by(username=username).first():
        flash("Такой логин уже есть", "error")
        return redirect(url_for("auth.users"))
    db.session.add(m.User(
        username=username,
        password_hash=generate_password_hash(password),
        full_name=full_name,
        role=role if role in m.ROLES else m.ROLE_MANAGER,
    ))
    db.session.commit()
    flash(f"Пользователь {username} создан", "success")
    return redirect(url_for("auth.users"))


@auth_bp.route("/users/<int:user_id>/toggle", methods=["POST"])
@role_required(m.ROLE_ADMIN)
def user_toggle(user_id):
    user = m.User.query.get_or_404(user_id)
    if user.id == session.get("user_id"):
        flash("Нельзя заблокировать себя", "error")
        return redirect(url_for("auth.users"))
    user.is_active = not user.is_active
    db.session.commit()
    flash("Статус изменён", "success")
    return redirect(url_for("auth.users"))


@auth_bp.route("/users/<int:user_id>/role", methods=["POST"])
@role_required(m.ROLE_ADMIN)
def user_role(user_id):
    user = m.User.query.get_or_404(user_id)
    role = request.form.get("role", "")
    if role in m.ROLES:
        user.role = role
        db.session.commit()
        flash("Роль обновлена", "success")
    return redirect(url_for("auth.users"))

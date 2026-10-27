from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import func

from . import _env  # noqa: F401,E402  — подхватывает .env до чтения конфига

db = SQLAlchemy()
csrf = CSRFProtect()


def current_app_config():
    from flask import current_app
    return current_app.config


def create_app(config_object="app.config.Config"):
    app = Flask(__name__)
    app.config.from_object(config_object)

    db.init_app(app)
    csrf.init_app(app)

    from .auth.routes import auth_bp
    from .crm.routes import crm_bp
    from .catalog.routes import catalog_bp
    from .sales.routes import sales_bp
    from .integrations.routes import integrations_bp
    from .hr.routes import hr_bp
    from .public.routes import public_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(crm_bp, url_prefix="/crm")
    app.register_blueprint(catalog_bp, url_prefix="/catalog")
    app.register_blueprint(sales_bp, url_prefix="/sales")
    app.register_blueprint(integrations_bp, url_prefix="/integrations")
    app.register_blueprint(hr_bp, url_prefix="/hr")
    app.register_blueprint(public_bp)

    @app.template_filter("fmoney")
    def fmt_money(value):
        try:
            return f"{float(value or 0):,.0f} ₽"
        except (TypeError, ValueError):
            return "0 ₽"

    @app.context_processor
    def inject_user():
        from .auth import current_user
        return {"user": current_user()}

    @app.route("/")
    def dashboard():
        from . import models as m
        from flask import render_template
        from .auth import current_user

        user = current_user()
        if user is None or not user.is_active:
            from flask import redirect, url_for
            return redirect(url_for("auth.login"))
        leads_open = m.Lead.query.filter(m.Lead.status.notin_(["won", "lost"])).count()
        leads_won = m.Lead.query.filter(m.Lead.status == "won").count()
        tasks_open = m.Task.query.filter_by(status="open").count()
        orders_open = m.Order.query.filter(m.Order.status.in_(
            ["draft", "confirmed", "paid"])).count()
        low_stock = (
            db.session.query(m.Product.name, m.Product.sku)
            .join(m.Stock, m.Stock.product_id == m.Product.id)
            .group_by(m.Product.id)
            .having(func.sum(m.Stock.qty) < func.max(m.Product.min_stock))
            .limit(20)
            .all()
        ) if m.Storage.query.first() else []
        recent_leads = m.Lead.query.order_by(m.Lead.updated_at.desc()).limit(10).all()
        from datetime import date
        _d = date.today()
        _months = ["января", "февраля", "марта", "апреля", "мая", "июня",
                   "июля", "августа", "сентября", "октября", "ноября", "декабря"]
        _days = ["понедельник", "вторник", "среда", "четверг", "пятница",
                 "суббота", "воскресенье"]
        today = f"{_days[_d.weekday()]} {_d.day} {_months[_d.month - 1]} {_d.year}"
        return render_template(
            "dashboard.html",
            leads_open=leads_open, leads_won=leads_won, tasks_open=tasks_open,
            orders_open=orders_open, low_stock=low_stock, recent_leads=recent_leads,
            today=today,
        )

    with app.app_context():
        db.create_all()
        _auto_migrate()
        _seed_admin()

    return app


def _auto_migrate():
    """Минимальная «самоподстройка» схемы: добавляет недостающие колонки.

    Покрыты только аддитивные изменения (новые поля) — для переделки типов
    и таблиц в будущем понадобится Alembic.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    for table in db.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {c["name"] for c in inspector.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing or col.primary_key:
                continue
            coltype = col.type.compile(dialect=db.engine.dialect)
            with db.engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {col.name} {coltype}"))


def _seed_admin():
    from . import models as m
    from werkzeug.security import generate_password_hash

    if not m.User.query.first():
        user = m.User(
            username="admin",
            password_hash=generate_password_hash("admin123"),
            full_name="Администратор",
            role=m.ROLE_ADMIN,
        )
        db.session.add(user)
        stor = m.Storage(name="Основной склад", type="склад")
        db.session.add(stor)
        for name in [
            "Котлы", "Сантехника", "Санфаянс", "Кафель/плитка",
            "Насосы", "Трубы и фитинги", "Запчасти и мелочь",
        ]:
            db.session.add(m.Category(name=name))
        db.session.commit()

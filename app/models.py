from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Numeric, Boolean, Text, Date, DateTime,
    ForeignKey, Float,
)
from sqlalchemy.orm import relationship

from . import db

ROLE_ADMIN = "admin"
ROLE_MANAGER = "manager"
ROLE_CASHIER = "cashier"
ROLES = [ROLE_ADMIN, ROLE_MANAGER, ROLE_CASHIER]

LEAD_SOURCES = ["авито", "сайт", "телефон", "instagram", "tiktok", "telegram",
                "рекомендация", "выставка", "другое"]
LEAD_STATUSES = ["new", "contacted", "quoted", "negotiation", "won", "lost"]
LEAD_STATUS_NAMES = {
    "new": "Новый",
    "contacted": "Связались",
    "quoted": "Посчитали счёт",
    "negotiation": "Переговоры",
    "won": "Сделка",
    "lost": "Срыв",
}

TASK_KINDS = ["звонок", "созвон", "встреча", "доставка", "монтаж", "догон-контроль"]
TASK_STATUSES = ["open", "done", "canceled"]
TASK_STATUS_NAMES = {"open": "Открыта", "done": "Выполнена", "canceled": "Отменена"}

# Квалификация лида (упрощённый BANT)
DEADLINE_CHOICES = [("asap", "Срочно"), ("month", "В этом месяце"), ("planning", "Просто смотрю")]
DECIDER_CHOICES = [("self", "Сам(а)"), ("family", "Семья"), ("company", "Компания")]
HEAT_NAMES = {"hot": "Горячий", "warm": "Тёплый", "cold": "Холодный"}

ORDER_STATUSES = ["draft", "confirmed", "paid", "shipped", "completed", "canceled"]
ORDER_STATUS_NAMES = {
    "draft": "Черновик",
    "confirmed": "Подтверждён",
    "paid": "Оплачен",
    "shipped": "Отгружен",
    "completed": "Закрыт",
    "canceled": "Отменён",
}

INVOICE_STATUSES = ["draft", "sent", "accepted", "paid", "canceled"]
INVOICE_STATUS_NAMES = {
    "draft": "Черновик",
    "sent": "Отправлен",
    "accepted": "Подписан",
    "paid": "Оплачен",
    "canceled": "Отменён",
}

STORAGE_TYPES = ["склад", "магазин", "точка выдачи"]


class User(db.Model):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    full_name = Column(String(128), default="")
    role = Column(String(16), nullable=False, default=ROLE_MANAGER)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)


class Storage(db.Model):
    __tablename__ = "storages"
    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    type = Column(String(32), default="склад")
    address = Column(String(256), default="")


class Category(db.Model):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True)
    name = Column(String(128), unique=True, nullable=False)


class Product(db.Model):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    sku = Column(String(64), unique=True, nullable=False)
    name = Column(String(256), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    brand = Column(String(64), default="")
    unit = Column(String(16), default="шт")
    price = Column(Numeric(12, 2), default=0)
    cost = Column(Numeric(12, 2), default=0)
    min_stock = Column(Integer, default=0)

    category = relationship("Category")
    stocks = relationship("Stock", back_populates="product", cascade="all, delete-orphan")

    @property
    def total_stock(self):
        return sum(s.qty for s in self.stocks)

    def price_float(self):
        return float(self.price or 0)


class Stock(db.Model):
    __tablename__ = "stocks"
    storage_id = Column(Integer, ForeignKey("storages.id"), primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), primary_key=True)
    qty = Column(Integer, default=0)

    product = relationship("Product", back_populates="stocks")
    storage = relationship("Storage")


class StockMovement(db.Model):
    __tablename__ = "stock_movements"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    storage_id = Column(Integer, ForeignKey("storages.id"), nullable=False)
    kind = Column(String(16), nullable=False)  # in / out / correction
    qty = Column(Integer, nullable=False)
    comment = Column(String(256), default="")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    storage = relationship("Storage")
    product = relationship("Product")
    user = relationship("User")


class Client(db.Model):
    __tablename__ = "clients"
    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    phone = Column(String(32), default="")
    email = Column(String(128), default="")
    company = Column(String(128), default="")
    address = Column(String(256), default="")
    notes = Column(Text, default="")
    is_active = Column(Boolean, default=True)

    leads = relationship("Lead", back_populates="client")
    orders = relationship("Order", back_populates="client")
    invoices = relationship("Invoice", back_populates="client")


class Lead(db.Model):
    __tablename__ = "leads"
    id = Column(Integer, primary_key=True)
    amocrm_id = Column(String(64), unique=True, nullable=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True)
    source = Column(String(32), default="телефон")
    status = Column(String(32), default="new", nullable=False)
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)
    deal_amount = Column(Numeric(12, 2), default=0)
    comment = Column(Text, default="")
    # квалификация
    need = Column(String(256), default="")          # что ищет
    budget = Column(Numeric(12, 2), default=0)      # бюджет, ₽
    deadline = Column(String(32), default="")       # asap/month/planning
    decider = Column(String(32), default="")        # self/family/company
    autofill = Column(Text, default="")             # что заполнил автопилот
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    client = relationship("Client", back_populates="leads")
    assignee = relationship("User", foreign_keys=[assigned_to])
    tasks = relationship("Task", back_populates="lead", cascade="all, delete-orphan")

    def status_name(self):
        return LEAD_STATUS_NAMES.get(self.status, self.status)

    @property
    def heat(self):
        """Скоринг: hot / warm / cold по бюджету, срокам и принятию решения."""
        score = 0
        b = float(self.budget or 0)
        if b >= 50000:
            score += 40
        elif b >= 10000:
            score += 25
        elif b > 0:
            score += 10
        if self.deadline == "asap":
            score += 35
        elif self.deadline == "month":
            score += 25
        elif self.deadline == "planning":
            score += 10
        if self.decider == "self":
            score += 25
        elif self.decider == "company":
            score += 15
        elif self.decider == "family":
            score += 10
        if score >= 60:
            return "hot"
        if score >= 30:
            return "warm"
        return "cold"

    @property
    def heat_name(self):
        return HEAT_NAMES.get(self.heat, "Холодный")


class Task(db.Model):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    title = Column(String(256), nullable=False)
    kind = Column(String(32), default="звонок")
    status = Column(String(16), default="open")
    due_at = Column(DateTime, nullable=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True)
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    done_at = Column(DateTime, nullable=True)

    lead = relationship("Lead", back_populates="tasks")
    client = relationship("Client")
    assignee = relationship("User", foreign_keys=[assigned_to])
    creator = relationship("User", foreign_keys=[created_by])


class OrderItem(db.Model):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    product_name = Column(String(256), default="")  # для позиций «услуга/монтаж»
    qty = Column(Numeric(10, 2), default=1)
    price = Column(Numeric(12, 2), default=0)
    discount = Column(Numeric(12, 2), default=0)

    order = relationship("Order", back_populates="items")
    product = relationship("Product")

    @property
    def total(self):
        return (float(self.price or 0) - float(self.discount or 0)) * float(self.qty or 0)


class Order(db.Model):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    number = Column(String(32), unique=True, nullable=False)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    status = Column(String(16), default="draft")
    order_date = Column(Date, default=date.today)
    delivery_date = Column(Date, nullable=True)
    comment = Column(Text, default="")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    client = relationship("Client", back_populates="orders")
    lead = relationship("Lead")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

    @property
    def total(self):
        return sum(i.total for i in self.items)

    @property
    def status_name(self):
        return ORDER_STATUS_NAMES.get(self.status, self.status)


class InvoiceItem(db.Model):
    __tablename__ = "invoice_items"
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    product_name = Column(String(256), default="")
    qty = Column(Numeric(10, 2), default=1)
    price = Column(Numeric(12, 2), default=0)

    invoice = relationship("Invoice", back_populates="items")
    product = relationship("Product")

    @property
    def total(self):
        return float(self.price or 0) * float(self.qty or 0)


class Invoice(db.Model):
    __tablename__ = "invoices"
    id = Column(Integer, primary_key=True)
    number = Column(String(32), unique=True, nullable=False)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    status = Column(String(16), default="draft")
    valid_until = Column(Date, nullable=True)
    comment = Column(Text, default="")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    client = relationship("Client", back_populates="invoices")
    lead = relationship("Lead")
    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")

    @property
    def total(self):
        return sum(i.total for i in self.items)

    @property
    def status_name(self):
        return INVOICE_STATUS_NAMES.get(self.status, self.status)


ATTENDANCE_STATUSES = {"planned": "план", "on_time": "вовремя", "late": "опоздал", "absent": "прогул"}


class Employee(db.Model):
    """Сотрудник (модуль «Прополис» — контроль команды)."""
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    position = Column(String(64), default="")
    shift_start = Column(String(5), default="09:00")  # "HH:MM"
    shift_end = Column(String(5), default="18:00")
    work_days = Column(String(7), default="1111110")  # Пн..Вс
    phone = Column(String(32), default="")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)

    attendances = relationship("Attendance", back_populates="employee", cascade="all, delete-orphan")

    def works_on(self, weekday: int) -> bool:
        """weekday: 0=Пн..6=Вс"""
        s = (self.work_days or "")[:7].ljust(7, "0")
        return s[weekday] == "1"


class Attendance(db.Model):
    """Явка за день: план и фактические отметки прихода/ухода."""
    __tablename__ = "attendances"
    __table_args__ = (db.UniqueConstraint("employee_id", "date", name="uq_attendance_emp_date"),)
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    date = Column(Date, nullable=False)
    planned_start = Column(DateTime, nullable=False)
    planned_end = Column(DateTime, nullable=False)
    actual_start = Column(DateTime, nullable=True)
    actual_end = Column(DateTime, nullable=True)
    status = Column(String(16), default="planned")  # planned/on_time/late
    comment = Column(String(256), default="")

    employee = relationship("Employee", back_populates="attendances")

    @property
    def status_name(self):
        if self.actual_start is not None and self.actual_end is not None:
            return "отработал"
        return ATTENDANCE_STATUSES.get(self.status, self.status)

    @property
    def was_late(self):
        return self.status == "late"

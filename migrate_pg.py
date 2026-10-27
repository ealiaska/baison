"""Перенос данных с локальной SQLite (instance/teplodom.db) на PostgreSQL.

Запуск:  py migrate_pg.py
Прочитает DATABASE_URL из .env (или переменной окружения).
Повторный запуск очищает таблицы и копирует заново.
"""
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

# читаем .env
for line in io.open(".env", encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

url = os.environ.get("DATABASE_URL", "")
if "postgresql" not in url:
    sys.exit("DATABASE_URL должен указывать PostgreSQL (postgresql+psycopg2://...)")

from app import create_app, db
from app import models as m
from sqlalchemy import Boolean, Integer, create_engine, inspect, text
import inspect as pyinspect

# table_name -> ORM-класс
CLASS_BY_TABLE = {
    cls.__table__.name: cls
    for name, cls in vars(m).items()
    if pyinspect.isclass(cls) and issubclass(cls, db.Model) and hasattr(cls, "__table__")
}

app = create_app()
app.config["SQLALCHEMY_DATABASE_URI"] = url

with app.app_context():
    print("Создаю схему в PostgreSQL...")
    db.drop_all()
    db.create_all()

    src_engine = create_engine("sqlite:///instance/teplodom.db")
    dst = db.session

    # порядок по зависимостям (внешние ключи)
    tables = [t for t in db.metadata.sorted_tables if t.name != "alembic_version"]
    copied = 0
    with src_engine.connect() as conn:
        for t in tables:
            try:
                # порядок колонок читаем ИЗ SQLITE (у него он может отличаться
                # от метадаты PG, т.к. часть полей добавлялась авто-миграцией)
                info = conn.execute(text(f"PRAGMA table_info({t.name})")).fetchall()
                if not info:
                    print(f"  {t.name:20s} — пусто")
                    continue
                cols = [r[1] for r in info]  # (cid, name, type, ...)
                rows = conn.execute(text(f"SELECT * FROM {t.name}")).fetchall()
            except Exception:
                print(f"  {t.name:20s} — нет в SQLite, пропуск")
                continue
            if not rows:
                print(f"  {t.name:20s} — пусто")
                continue
            pg_cols = [c.name for c in t.columns]
            prepared = []
            for row in rows:
                raw = dict(zip(cols, row))
                # оставляем только колонки, которые есть в схеме PG
                rec = {k: raw.get(k) for k in pg_cols}
                for c in t.columns:
                    v = rec.get(c.name)
                    if v is None:
                        continue
                    ct = c.type
                    if isinstance(ct, Boolean):
                        v = bool(int(v))
                    elif isinstance(ct, Integer):
                        v = int(v)
                    rec[c.name] = v
                prepared.append(rec)
            cls = CLASS_BY_TABLE.get(t.name)
            dst.bulk_insert_mappings(cls, prepared)
            print(f"  {t.name:20s} — {len(prepared)} строк")
            copied += len(prepared)
        dst.commit()

    # PostgreSQL-секвенции: после вставки явных id сдвигаем nextval,
    # иначе новые записи получат id, которые уже заняты
    print("\nСинхронизирую последовательности...")
    for t in tables:
        pk = [c for c in t.columns if c.primary_key]
        if len(pk) != 1 or pk[0].name != "id":
            continue
        with db.engine.begin() as e:
            row = e.execute(text(
                f"SELECT pg_get_serial_sequence('{t.name}', 'id') AS seq, "
                f"COALESCE(MAX(id), 0) + 1 AS next_id FROM {t.name}"
            )).first()
            if row and row[0]:
                e.execute(text(
                    f"SELECT setval('{row[0]}', {int(row[1])}, false)"))
    print("done")

    print(f"\nГотово: перенесено {copied} строк из {len(tables)} таблиц.")
    for model in (m.User, m.Client, m.Lead, m.Product, m.Category, m.Storage, m.Employee, m.Task):
        print(f"  {model.__name__:12s} {db.session.query(model).count()}")

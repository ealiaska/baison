"""Автопилот заявок (карточек лидов).

При создании заявки (публичная форма, webhook, вручную) система сама:
  1. нормализует телефон клиента (+7XXXXXXXXXX) и дублирует по нему;
  2. разбирает свободный текст (что ищет + комментарий) и заполняет
     пустые поля квалификации: категория, бюджет, сроки, кто решает;
  3. назначает менеджера с наименьшей загрузкой;
  4. создаёт задачу «Позвонить» на ближайшее время.

Заполняются только ПУСТЫЕ поля — ручные данные не перезаписываются.
Всё, что сделал автопилот, видно в lead.autofill (отметка «⚡ авто»).
"""
import re
from datetime import datetime, timedelta

from .. import db
from .. import models as m


# ---------------------------------------------------------------- телефон

def normalize_phone(raw):
    """'8 999 123-45-67' / '+7(999)123-45-67' / '9991234567' → '+79991234567'.

    Строки без цифр (например 'абв') — не телефон, ''."""
    d = re.sub(r"\D", "", raw or "")
    if not d:
        return ""
    if len(d) == 11 and d.startswith("8"):
        d = "7" + d[1:]
    elif len(d) == 10 and d.startswith("9"):
        d = "7" + d
    if len(d) == 11 and d.startswith("7"):
        return "+" + d
    if 8 <= len(d) <= 15:  # иностранный/не распознанный формат — цифры как есть
        return "+" + d
    return d


# ---------------------------------------------------------------- категории

# Многословные фразы: распознаются первыми и «засвечиваются»,
# чтобы их части не сработали как другие категории.
CATEGORY_PHRASES = [
    (re.compile(r"тепловой\s+насос"), "Котлы"),
    (re.compile(r"тепл\w*\s+пол"), "Трубы и фитинги"),
    (re.compile(r"водоснабжени\w*"), "Трубы и фитинги"),
    (re.compile(r"отоплени\w*"), "Трубы и фитинги"),
    (re.compile(r"водоподготовк\w*|обессоливан\w*|умягчени\w*"), "Запчасти и мелочь"),
]

CATEGORY_STEMS = [
    ("Котлы", ["котел", "котельн", "водонагр", "бойлер", "газов", "электрокотл",
               "конденсацион", "дизельн"]),
    ("Насосы", ["насос", "циркуляц", "гидрофор", "скважинн", "погружн",
                "самовсас", "элеват", "гидроуз"]),
    ("Санфаянс", ["унитаз", "санфаянс", "раковин", "ванна", "душевая",
                  "кабинк", "биде", "чаша"]),
    ("Сантехника", ["смесит", "кран", "сифон", "гибк", "гидромассаж",
                    "трап", "сливн", "вентиль"]),
    ("Кафель/плитка", ["плитк", "кафель", "керамогранит", "керамич", "мозаик",
                       "затирк"]),
    ("Трубы и фитинги", ["труб", "фитинг", "радиатор", "батаре", "магистрал",
                         "теплонос", "пенофол", "компенсационн", "клапан"]),
    ("Запчасти и мелочь", ["прокладк", "уплотнител", "герметик", "манжет", "гайк",
                           "хомут", "фильтр", "редуктор", "арматур", "запчаст",
                           "шпильк", "креп"]),
]

_INSTALL_RE = re.compile(r"\бмонтаж\w*\b|монтаж|установк|подключен")


def detect_categories(text):
    """Возвращает список категорий (до 2) по тексту, в порядке обнаружения."""
    t = (text or "").lower().replace("ё", "е")
    found = []
    masked = t
    for rx, cat in CATEGORY_PHRASES:
        for mm in rx.finditer(t):
            if cat not in found:
                found.append(cat)
        masked = rx.sub(" ", masked)
    for cat, stems in CATEGORY_STEMS:
        if any(s in masked for s in stems):
            if cat not in found:
                found.append(cat)
    return found[:2]


def has_install(text):
    return bool(_INSTALL_RE.search((text or "").lower().replace("ё", "е")))


# ---------------------------------------------------------------- бюджет

def _to_num(s):
    s = s.replace(" ", "").replace("\u00a0", "").replace(".", "").replace(",", "")
    if s.isdigit() and s:
        return int(s)
    return 0


def detect_budget(text):
    """'бюджет 50к' → 50000; 'до 100000 руб' → 100000; '24 кВт' → None."""
    t = (text or "").lower().replace("ё", "е")
    vals = []
    for mm in re.finditer(r"(\d[\d\s]{0,7}?)\s*(?:тыс|тысяч|к)\b", t):
        v = _to_num(mm.group(1))
        if v:
            vals.append(v * 1000)
    for mm in re.finditer(r"\b(\d{3}(?:[ .]\d{3}){1,3})\b", t):
        v = _to_num(mm.group(1))
        if v:
            vals.append(v)
    for mm in re.finditer(r"\b(\d{5,6})\b", t):
        vals.append(int(mm.group(1)))
    for mm in re.finditer(r"(\d[\d\s]{2,9}?)\s*руб", t):
        v = _to_num(mm.group(1))
        if v:
            vals.append(v)
    vals = [v for v in vals if v and v < 100_000_000]
    return max(vals) if vals else None


# ---------------------------------------------------------------- сроки

_DEADLINE_RULES = [
    ("planning", ["не срочн", "просто смотр", "смотрю", "думает", "обдумыва",
                  "рассматрива", "сравнива", "ориентир", "когда-нибудь",
                  "когда будут деньги", "еще не реш", "позже", "через месяц",
                  "через два", "через год", "когда-то", "просто интерес",
                  "решим потом"]),
    ("asap", ["срочн", "сегодня", "завтра", "на этой недел", "в течени",
              "в ближайши дни", "недел", "как можно быстр", "немедленн",
              "сразу", "срочно"]),
    ("month", ["в этом месяце", "в месяц", "месяц", "скоро", "в ближайш",
               "ближайшее время", "в течении месяца"]),
]


def detect_deadline(text):
    t = (text or "").lower().replace("ё", "е")
    for value, words in _DEADLINE_RULES:
        if any(w in t for w in words):
            return value
    return None


# ---------------------------------------------------------------- кто решает

_DECIDER_RULES = [
    ("company", ["компани", "фирм", "ооо", "организаци", "производств",
                 "на работу", "для работы", "бизнес", "торгов", "кафе",
                 "ресторан", "офис", "цех", "склад", "гостиниц",
                 "апартамент", "ип", "самозанят"]),
    ("family", ["жено", "муж", "семь", "родител", "бабушк", "дочер", "сын",
                "мама", "папа", "на двоих", "совместн", "квартир", "дом",
                "дач"]),
]
_DECIDER_SELF_RE = re.compile(r"\bсам[а]?\b|\bсебе\b|\bсвоей\b|\bсво[ёмем]\b")


def detect_decider(text):
    t = (text or "").lower().replace("ё", "е")
    for value, words in _DECIDER_RULES:
        if any(w in t for w in words):
            return value
    if _DECIDER_SELF_RE.search(t):
        return "self"
    return None


# ---------------------------------------------------------------- менеджер

def pick_manager():
    """Менеджер с наименьшим числом открытых заявок (round-robin по нагрузке)."""
    users = m.User.query.filter(
        m.User.is_active.is_(True), m.User.role == m.ROLE_MANAGER).all()
    if not users:
        users = m.User.query.filter(m.User.is_active.is_(True)).all()
    if not users:
        return None

    def open_count(u):
        return m.Lead.query.filter(
            m.Lead.assigned_to == u.id,
            m.Lead.status.notin_(["won", "lost"]),
        ).count()

    return sorted(users, key=lambda u: (open_count(u), u.id))[0]


# ---------------------------------------------------------------- задача

def _call_due():
    """Время звонка: через час (округление вверх до :00/:30); после 20:00 — завтра 10:00."""
    now = datetime.now()
    due = now + timedelta(hours=1)
    due = due.replace(minute=30 if due.minute > 30 else 0, second=0, microsecond=0)
    if now.hour >= 20 or now.hour < 8:
        due = (now + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    return due


# ---------------------------------------------------------------- автопилот

def apply_autopilot(lead, create_task=None):
    """Заполняет пустые поля заявки и ставит задачу на звонок.

    Возвращает список действий (попадут в lead.autofill).
    Вызывать после db.session.add(lead), до commit (внутрь flush делает сам).
    """
    from flask import current_app
    if create_task is None:
        create_task = current_app.config.get("AUTOPILOT_CREATE_TASK", True)

    actions = []
    text = " ".join(filter(None, [(lead.need or ""), (lead.comment or "")]))

    # 1. Телефон клиента: нормализуем на месте (только строки, похожие
    #    на телефон; идентификаторы вида 'ig:123' не трогаем)
    if lead.client_id and not lead.client:
        lead.client = db.session.get(m.Client, lead.client_id)
    if lead.client and lead.client.phone and re.fullmatch(r"[\d+()\-\s]+", lead.client.phone):
        norm = normalize_phone(lead.client.phone)
        if norm and norm != lead.client.phone:
            lead.client.phone = norm
            actions.append("телефон нормализован")

    # 2. Что ищет — если пустое, собираем из текста
    if not (lead.need or "").strip():
        cats = detect_categories(text)
        if cats:
            need = " + ".join(cats)
            if has_install(text):
                need += " + монтаж"
            lead.need = need
            actions.append("категория: " + need)
        elif has_install(text):
            lead.need = "монтаж"
            actions.append("категория: монтаж")

    # 3. Квалификация из текста — только пустые поля
    if not lead.budget:
        budget = detect_budget(text)
        if budget:
            lead.budget = budget
            actions.append(f"бюджет: {budget:,} ₸".replace(",", " "))
    if not lead.deadline:
        deadline = detect_deadline(text)
        if deadline:
            lead.deadline = deadline
            labels = {"asap": "сроки: срочно", "month": "сроки: в этом месяце",
                      "planning": "сроки: не срочно"}
            actions.append(labels[deadline])
    if not lead.decider:
        decider = detect_decider(text)
        if decider:
            lead.decider = decider
            labels = {"self": "решает сам", "family": "решает семья",
                      "company": "решает компания"}
            actions.append(labels[decider])

    # 4. Менеджер
    if not lead.assigned_to:
        mgr = pick_manager()
        if mgr:
            lead.assigned_to = mgr.id
            actions.append("менеджер: " + (mgr.full_name or mgr.username))

    # 5. Задача на звонок (если её ещё нет)
    if create_task and not lead.id:
        db.session.flush()
    if create_task and lead.id:
        has_task = m.Task.query.filter(
            m.Task.lead_id == lead.id, m.Task.status == "open").first()
        if not has_task:
            who = lead.client.name if lead.client else "клиент"
            phone = lead.client.phone if lead.client and lead.client.phone else ""
            title = f"Позвонить: {who}" + (f" {phone}" if phone else "")
            db.session.add(m.Task(
                title=title,
                kind="звонок",
                lead_id=lead.id,
                client_id=lead.client_id,
                assigned_to=lead.assigned_to,
                due_at=_call_due(),
            ))
            actions.append("задача «Позвонить»")

    if actions:
        lead.autofill = "; ".join(actions)
        lead.updated_at = datetime.now()
    return actions

from datetime import date


def next_number(prefix, model, number_col):
    year = date.today().year
    like = f"{prefix}-{year}-%"
    last = model.query.filter(number_col.like(like)).order_by(number_col.desc()).first()
    seq = 0
    if last:
        try:
            seq = int(str(last.number).rsplit("-", 1)[-1])
        except ValueError:
            seq = 0
    return f"{prefix}-{year}-{seq + 1:04d}"


def parse_items(form):
    """Читает строки формы: product_id[], product_name[], qty[], price[], discount[]"""
    items = []
    for i in range(len(form.getlist("product_id")) + len(form.getlist("product_name"))):
        try:
            product_id = form.getlist("product_id")[i] or None
            product_id = int(product_id) if product_id else None
            name = (form.getlist("product_name") or [""] * (i + 1))[i].strip()
            qty = float((form.getlist("qty") or [""] * (i + 1))[i] or 0)
            price = float((form.getlist("price") or [""] * (i + 1))[i] or 0)
            discount_list = form.getlist("discount")
            discount = float(discount_list[i]) if i < len(discount_list) and discount_list[i] else 0.0
        except (ValueError, IndexError):
            break
        if not product_id and not name:
            continue
        if qty <= 0:
            continue
        items.append((product_id, name, qty, price, discount))
    return items

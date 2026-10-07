import json
import os
import re
import sqlite3
from datetime import date, datetime

from flask import Flask, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import extract, func, inspect, text


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.join(os.path.dirname(BASE_DIR), "data")
os.makedirs(INSTANCE_DIR, exist_ok=True)

def env_flag(name, default=False):
    value = (os.environ.get(name) or "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def sqlite_path_from_url(database_url):
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        return None
    path = database_url[len(prefix) :]
    if not path or path == ":memory:":
        return None
    return os.path.abspath(os.path.expanduser(path))


def assert_existing_database(database_url):
    if not env_flag("GASTOS_REQUIRE_EXISTING_DB", False):
        return
    database_path = sqlite_path_from_url(database_url)
    if not database_path:
        raise RuntimeError(
            "GASTOS_REQUIRE_EXISTING_DB=1 requiere una base SQLite en disco"
        )
    if not os.path.isfile(database_path) or os.path.getsize(database_path) == 0:
        raise RuntimeError(
            f"No existe una base de Gastos válida en {database_path}. "
            "Se ha detenido el arranque para no crear una base vacía por accidente."
        )
    uri = f"file:{database_path}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    except sqlite3.Error as exc:
        raise RuntimeError(
            f"No se pudo validar la base existente de Gastos en {database_path}: {exc}"
        ) from exc
    finally:
        try:
            connection.close()
        except (NameError, UnboundLocalError):
            pass
    missing = {"ticket", "ticket_item"} - tables
    if missing:
        raise RuntimeError(
            "La base indicada no parece ser una base de Gastos de comida "
            f"(faltan tablas: {', '.join(sorted(missing))})."
        )


DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(INSTANCE_DIR, 'gastos.db')}",
)
assert_existing_database(DATABASE_URL)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    purchase_date = db.Column(db.Date, nullable=False, index=True)
    supermarket = db.Column(db.String(120), nullable=False, index=True)
    total = db.Column(db.Float, nullable=False, default=0.0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    items = db.relationship(
        "TicketItem",
        backref="ticket",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="TicketItem.id",
    )


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True, index=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class TicketItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("ticket.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=True, index=True)
    product = db.relationship("Product", backref=db.backref("ticket_items", lazy=True))
    article = db.Column(db.String(200), nullable=False, index=True)
    quantity = db.Column(db.Float, nullable=False, default=1.0)
    price = db.Column(db.Float, nullable=False, default=0.0)
    net_price = db.Column(db.Float, nullable=True)
    discount = db.Column(db.Float, nullable=False, default=0.0)
    discount_percent = db.Column(db.Float, nullable=False, default=0.0)
    total = db.Column(db.Float, nullable=False, default=0.0)
    user_name = db.Column(db.String(120), nullable=False, index=True)


class LookupExclusion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(40), nullable=False, index=True)
    value = db.Column(db.String(200), nullable=False, index=True)


def parse_float(value, default=0.0):
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default


def parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


TRAILING_WEIGHT_PATTERN = re.compile(
    r"(?:\s|,)+(?:\d+(?:[.,]\d+)?)\s*(?:g|gr|kg|ml|l|st|er)\.?$",
    re.IGNORECASE,
)
TRAILING_NUMERIC_PATTERN = re.compile(r"(?:\s|,)+(?:\d+(?:[.,]\d+)?)(?:\s*)$", re.IGNORECASE)
KNOWN_PREFIXES = (
    "ASC ",
    "MSC ",
    "AMA ",
    "AT ",
    "PG ",
    "Prix Garantie ",
)


def normalize_user_name(value):
    cleaned = (value or "").strip()
    if cleaned.lower() == "amps":
        return "ambos"
    return cleaned


def normalize_article_name(value):
    article = (value or "").strip()
    if not article:
        return article

    for prefix in KNOWN_PREFIXES:
        if article.startswith(prefix):
            article = article[len(prefix) :].strip()
            break

    article = article.replace(",", " ")
    article = re.sub(r"\s*-\s*", " ", article)
    article = re.sub(r"\s+", " ", article).strip()

    previous = None
    while previous != article:
        previous = article
        article = TRAILING_WEIGHT_PATTERN.sub("", article).strip()
        article = TRAILING_NUMERIC_PATTERN.sub("", article).strip()

    return re.sub(r"\s+", " ", article).strip(" -")


def find_or_create_product(article):
    name = normalize_article_name(article)
    if not name:
        return None
    product = Product.query.filter(func.lower(Product.name) == name.lower()).first()
    if product is None:
        product = Product(name=name, active=True, updated_at=datetime.utcnow())
        db.session.add(product)
        db.session.flush()
    elif not product.active:
        product.active = True
        product.updated_at = datetime.utcnow()
    return product


def attach_products(items):
    for item in items:
        product = find_or_create_product(item.article)
        if product is not None:
            item.product = product
            item.product_id = product.id


def backfill_products():
    changed = False
    products_by_name = {product.name.casefold(): product for product in Product.query.all()}
    for item in TicketItem.query.order_by(TicketItem.id.asc()).all():
        name = normalize_article_name(item.article)
        if not name:
            continue
        product = products_by_name.get(name.casefold())
        if product is None:
            product = Product(name=name, active=True, updated_at=datetime.utcnow())
            db.session.add(product)
            db.session.flush()
            products_by_name[name.casefold()] = product
            changed = True
        if item.product_id != product.id:
            item.product_id = product.id
            changed = True
    if changed:
        db.session.commit()


def compute_effective_unit_price(price, net_price=None, discount=0.0, discount_percent=0.0):
    if net_price is not None:
        return float(net_price)
    if discount:
        return float(price) - float(discount)
    if discount_percent:
        return float(price) * (1 - (float(discount_percent) / 100.0))
    return float(price)


def build_filtered_results_title(article, user_name, supermarket, start_date, end_date, has_selected_period):
    title = "Gastos"
    if article:
        title += f" de {article}"
    if has_selected_period and start_date and end_date:
        title += f" entre {start_date.strftime('%Y-%m-%d')} y {end_date.strftime('%Y-%m-%d')}"
    if user_name:
        title += f" de {user_name}"
    if supermarket:
        title += f" en el supermercado {supermarket}"
    return title


def ticket_to_dict(ticket):
    return {
        "id": ticket.id,
        "date": ticket.purchase_date.strftime("%Y-%m-%d"),
        "supermarket": ticket.supermarket,
        "total": round(ticket.total, 2),
        "updated_at": (
            ticket.updated_at.isoformat(timespec="microseconds")
            if ticket.updated_at is not None
            else None
        ),
        "items": [
            {
                "product_id": item.product_id,
                "article": item.article,
                "quantity": item.quantity,
                "price": item.price,
                "net_price": item.net_price,
                "discount": item.discount,
                "discount_percent": item.discount_percent,
                "total": item.total,
                "user_name": item.user_name,
            }
            for item in ticket.items
        ],
    }


def parse_ticket_form(form):
    purchase_date = parse_date(form.get("purchase_date"))
    supermarket = (form.get("supermarket") or "").strip()

    articles = form.getlist("article[]")
    quantities = form.getlist("quantity[]")
    prices = form.getlist("price[]")
    net_prices = form.getlist("net_price[]")
    discounts = form.getlist("discount[]")
    discount_percents = form.getlist("discount_percent[]")
    users = form.getlist("user_name[]")

    if not purchase_date or not supermarket:
        return None, None, None

    items = []
    ticket_total = 0.0
    for idx, article in enumerate(articles):
        article = normalize_article_name(article)
        if not article:
            continue
        quantity = parse_float(quantities[idx] if idx < len(quantities) else 0, 0.0)
        price = parse_float(prices[idx] if idx < len(prices) else 0, 0.0)
        net_price_raw = (net_prices[idx] if idx < len(net_prices) else "").strip()
        discount_raw = (discounts[idx] if idx < len(discounts) else "").strip()
        discount_percent_raw = (discount_percents[idx] if idx < len(discount_percents) else "").strip()
        net_price = parse_float(net_price_raw, 0.0) if net_price_raw else None
        discount = parse_float(discount_raw, 0.0) if discount_raw else 0.0
        discount_percent = parse_float(discount_percent_raw, 0.0) if discount_percent_raw else 0.0
        user_name = normalize_user_name((users[idx] if idx < len(users) else "").strip()) or "Sin asignar"
        effective_unit_price = compute_effective_unit_price(
            price,
            net_price=net_price,
            discount=discount,
            discount_percent=discount_percent,
        )
        line_total = round(quantity * effective_unit_price, 2)
        ticket_total += line_total
        items.append(
            TicketItem(
                article=article,
                quantity=quantity,
                price=price,
                net_price=net_price,
                discount=discount,
                discount_percent=discount_percent,
                total=line_total,
                user_name=user_name,
            )
        )

    if not items:
        return None, None, None

    return purchase_date, supermarket, (items, round(ticket_total, 2))


def build_monthly_chart(year):
    total_rows = (
        db.session.query(extract("month", Ticket.purchase_date), func.sum(Ticket.total))
        .filter(extract("year", Ticket.purchase_date) == year)
        .group_by(extract("month", Ticket.purchase_date))
        .order_by(extract("month", Ticket.purchase_date))
        .all()
    )
    user_rows = (
        db.session.query(
            extract("month", Ticket.purchase_date),
            TicketItem.user_name,
            func.sum(TicketItem.total),
        )
        .join(TicketItem, Ticket.id == TicketItem.ticket_id)
        .filter(extract("year", Ticket.purchase_date) == year)
        .group_by(extract("month", Ticket.purchase_date), TicketItem.user_name)
        .order_by(extract("month", Ticket.purchase_date), TicketItem.user_name.asc())
        .all()
    )

    month_map = {int(month): float(total or 0.0) for month, total in total_rows}
    user_names = sorted({user_name for _month, user_name, _total in user_rows if user_name})
    user_month_map = {user_name: {} for user_name in user_names}
    for month, user_name, total in user_rows:
        if user_name:
            user_month_map[user_name][int(month)] = float(total or 0.0)

    labels = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    datasets = [
        {
            "label": "Total mensual",
            "data": [round(month_map.get(index, 0.0), 2) for index in range(1, 13)],
        }
    ]
    for user_name in user_names:
        datasets.append(
            {
                "label": user_name,
                "data": [round(user_month_map[user_name].get(index, 0.0), 2) for index in range(1, 13)],
            }
        )
    return labels, datasets


def build_metrics():
    total_spend = db.session.query(func.coalesce(func.sum(Ticket.total), 0.0)).scalar() or 0.0
    gross_spend = (
        db.session.query(func.coalesce(func.sum(TicketItem.quantity * TicketItem.price), 0.0)).scalar() or 0.0
    )
    monthly_rows = (
        db.session.query(
            extract("year", Ticket.purchase_date),
            extract("month", Ticket.purchase_date),
            func.sum(Ticket.total),
        )
        .group_by(extract("year", Ticket.purchase_date), extract("month", Ticket.purchase_date))
        .all()
    )
    weekly_rows = (
        db.session.query(
            func.strftime("%Y", Ticket.purchase_date),
            func.strftime("%W", Ticket.purchase_date),
            func.sum(Ticket.total),
        )
        .group_by(func.strftime("%Y", Ticket.purchase_date), func.strftime("%W", Ticket.purchase_date))
        .all()
    )
    annual_rows = (
        db.session.query(extract("year", Ticket.purchase_date), func.sum(Ticket.total))
        .group_by(extract("year", Ticket.purchase_date))
        .all()
    )
    user_total_rows = (
        db.session.query(TicketItem.user_name, func.sum(TicketItem.total))
        .group_by(TicketItem.user_name)
        .all()
    )
    user_gross_rows = (
        db.session.query(TicketItem.user_name, func.sum(TicketItem.quantity * TicketItem.price))
        .group_by(TicketItem.user_name)
        .all()
    )
    weekly_average = 0.0
    monthly_average = 0.0
    annual_average = 0.0
    week_count = len(weekly_rows)
    month_count = len(monthly_rows)
    year_count = len(annual_rows)
    if weekly_rows:
        weekly_average = sum(float(row[2] or 0.0) for row in weekly_rows) / len(weekly_rows)
    if monthly_rows:
        monthly_average = sum(float(row[2] or 0.0) for row in monthly_rows) / len(monthly_rows)
    if annual_rows:
        annual_average = sum(float(row[1] or 0.0) for row in annual_rows) / len(annual_rows)
    total_saved = max(float(gross_spend) - float(total_spend), 0.0)
    user_total_map = {str(user_name): float(total or 0.0) for user_name, total in user_total_rows if user_name}
    user_gross_map = {str(user_name): float(total or 0.0) for user_name, total in user_gross_rows if user_name}
    user_names = sorted(set(user_total_map) | set(user_gross_map))

    def format_user_values(values):
        return [
            {"user_name": user_name, "value": round(float(values.get(user_name, 0.0)), 2)}
            for user_name in user_names
            if abs(float(values.get(user_name, 0.0))) > 0.004
        ]

    metric_cards = [
        {
            "label": "Total acumulado",
            "value": round(total_spend, 2),
            "user_values": format_user_values(user_total_map),
        },
        {
            "label": "Total sin descuentos",
            "value": round(gross_spend, 2),
            "user_values": format_user_values(user_gross_map),
        },
        {
            "label": "Total ahorrado",
            "value": round(total_saved, 2),
            "user_values": format_user_values(
                {
                    user_name: max(user_gross_map.get(user_name, 0.0) - user_total_map.get(user_name, 0.0), 0.0)
                    for user_name in user_names
                }
            ),
        },
        {
            "label": "Media semanal",
            "value": round(weekly_average, 2),
            "user_values": format_user_values(
                {
                    user_name: (user_total_map.get(user_name, 0.0) / week_count) if week_count else 0.0
                    for user_name in user_names
                }
            ),
        },
        {
            "label": "Media mensual",
            "value": round(monthly_average, 2),
            "user_values": format_user_values(
                {
                    user_name: (user_total_map.get(user_name, 0.0) / month_count) if month_count else 0.0
                    for user_name in user_names
                }
            ),
        },
        {
            "label": "Media anual",
            "value": round(annual_average, 2),
            "user_values": format_user_values(
                {
                    user_name: (user_total_map.get(user_name, 0.0) / year_count) if year_count else 0.0
                    for user_name in user_names
                }
            ),
        },
    ]
    return metric_cards


def build_lookup_values():
    excluded_values = {"article": set(), "user": set(), "supermarket": set()}
    for row in LookupExclusion.query.all():
        excluded_values.setdefault(row.category, set()).add(row.value)
    articles = [
        value
        for value, _count in db.session.query(TicketItem.article, func.count(TicketItem.id))
        .filter(TicketItem.article.isnot(None))
        .group_by(TicketItem.article)
        .order_by(func.count(TicketItem.id).desc(), TicketItem.article.asc())
        .all()
        if value and value not in excluded_values.get("article", set())
    ]
    users = [
        value
        for value, _count in db.session.query(TicketItem.user_name, func.count(TicketItem.id))
        .filter(TicketItem.user_name.isnot(None))
        .group_by(TicketItem.user_name)
        .order_by(func.count(TicketItem.id).desc(), TicketItem.user_name.asc())
        .all()
        if value and value not in excluded_values.get("user", set())
    ]
    supermarkets = [
        value
        for value, _count in db.session.query(Ticket.supermarket, func.count(Ticket.id))
        .filter(Ticket.supermarket.isnot(None))
        .group_by(Ticket.supermarket)
        .order_by(func.count(Ticket.id).desc(), Ticket.supermarket.asc())
        .all()
        if value and value not in excluded_values.get("supermarket", set())
    ]
    return articles, users, supermarkets


def restore_hidden_lookup_values(supermarket, items):
    used_values = {
        "supermarket": {supermarket} if supermarket else set(),
        "article": {item.article for item in items if item.article},
        "user": {item.user_name for item in items if item.user_name},
    }
    for category, values in used_values.items():
        if not values:
            continue
        LookupExclusion.query.filter(
            LookupExclusion.category == category,
            LookupExclusion.value.in_(values),
        ).delete(synchronize_session=False)


def ensure_ticket_schema():
    inspector = inspect(db.engine)
    columns = {column["name"] for column in inspector.get_columns("ticket")}
    if "updated_at" not in columns:
        with db.engine.begin() as connection:
            connection.execute(text("ALTER TABLE ticket ADD COLUMN updated_at DATETIME"))
            connection.execute(
                text("UPDATE ticket SET updated_at = COALESCE(created_at, CURRENT_TIMESTAMP)")
            )
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_ticket_updated_at ON ticket (updated_at)")
            )


def ensure_ticket_item_schema():
    inspector = inspect(db.engine)
    columns = {column["name"] for column in inspector.get_columns("ticket_item")}
    if "net_price" not in columns:
        with db.engine.begin() as connection:
            connection.execute(text("ALTER TABLE ticket_item ADD COLUMN net_price FLOAT"))
            connection.execute(text("UPDATE ticket_item SET net_price = discount"))
            connection.execute(text("UPDATE ticket_item SET discount = 0 WHERE discount IS NOT NULL"))
    if "discount_percent" not in columns:
        with db.engine.begin() as connection:
            connection.execute(text("ALTER TABLE ticket_item ADD COLUMN discount_percent FLOAT DEFAULT 0"))
            connection.execute(text("UPDATE ticket_item SET discount_percent = 0 WHERE discount_percent IS NULL"))
    if "product_id" not in columns:
        with db.engine.begin() as connection:
            connection.execute(text("ALTER TABLE ticket_item ADD COLUMN product_id INTEGER"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_ticket_item_product_id ON ticket_item (product_id)"))


def normalize_stored_items():
    changed = False
    for item in TicketItem.query.all():
        normalized_article = normalize_article_name(item.article)
        normalized_user = normalize_user_name(item.user_name)
        if normalized_article and normalized_article != item.article:
            item.article = normalized_article
            changed = True
        if normalized_user and normalized_user != item.user_name:
            item.user_name = normalized_user
            changed = True
    if changed:
        db.session.commit()


def normalize_discount_values():
    for item in TicketItem.query.all():
        quantity = float(item.quantity or 0.0)
        price = float(item.price or 0.0)
        item.discount = round(max(float(item.discount or 0.0), 0.0), 4)
        item.discount_percent = round(max(float(item.discount_percent or 0.0), 0.0), 4)
        if item.net_price is not None:
            item.net_price = round(max(float(item.net_price or 0.0), 0.0), 4)
        elif quantity > 0:
            inferred_unit_price = max(float(item.total or 0.0), 0.0) / quantity
            if abs(inferred_unit_price - price) > 0.0001:
                item.net_price = round(inferred_unit_price, 4)
            else:
                item.net_price = None
        effective_unit_price = compute_effective_unit_price(
            price,
            net_price=item.net_price,
            discount=item.discount,
            discount_percent=item.discount_percent,
        )
        item.total = round(quantity * effective_unit_price, 2)
    for ticket in Ticket.query.all():
        ticket.total = round(sum(item.total for item in ticket.items), 2)
    db.session.commit()


def collect_filters():
    article_query = request.args.get("article", "").strip()
    user_query = request.args.get("user", "").strip()
    supermarket_query = request.args.get("supermarket", "").strip()
    raw_start_date = (request.args.get("start_date") or "").strip()
    raw_end_date = (request.args.get("end_date") or "").strip()
    today = date.today()
    default_start = date(today.year, 1, 1)
    start_date = parse_date(raw_start_date) or default_start
    end_date = parse_date(raw_end_date) or today
    has_selected_period = bool(raw_start_date or raw_end_date)
    chart_year = request.args.get("chart_year", str(date.today().year)).strip()
    try:
        chart_year = int(chart_year)
    except ValueError:
        chart_year = date.today().year

    filtered_results = []
    filtered_results_total = None
    totals_between_dates = None
    totals_between_dates_by_user = None
    has_detail_filters = bool(article_query or user_query or supermarket_query or has_selected_period)
    if has_detail_filters:
        filtered_results_query = (
            db.session.query(
                Ticket.purchase_date,
                Ticket.supermarket,
                TicketItem.article,
                TicketItem.quantity,
                TicketItem.total,
                TicketItem.user_name,
            )
            .join(TicketItem, Ticket.id == TicketItem.ticket_id)
        )
        if article_query:
            filtered_results_query = filtered_results_query.filter(TicketItem.article.ilike(f"%{article_query}%"))
        if user_query:
            filtered_results_query = filtered_results_query.filter(TicketItem.user_name.ilike(f"%{user_query}%"))
        if has_selected_period and start_date and end_date:
            filtered_results_query = filtered_results_query.filter(
                Ticket.purchase_date >= start_date,
                Ticket.purchase_date <= end_date,
            )
        if supermarket_query:
            filtered_results_query = filtered_results_query.filter(Ticket.supermarket == supermarket_query)
        filtered_results = filtered_results_query.order_by(Ticket.purchase_date.desc(), Ticket.id.desc()).all()
        filtered_results_total = round(sum(float(row[4] or 0.0) for row in filtered_results), 2)

    if start_date and end_date:
        totals_between_dates = (
            db.session.query(func.coalesce(func.sum(Ticket.total), 0.0))
            .filter(Ticket.purchase_date >= start_date, Ticket.purchase_date <= end_date)
            .scalar()
            or 0.0
        )
        if user_query:
            totals_between_dates_by_user = (
                db.session.query(func.coalesce(func.sum(TicketItem.total), 0.0))
                .join(Ticket, Ticket.id == TicketItem.ticket_id)
                .filter(
                    Ticket.purchase_date >= start_date,
                    Ticket.purchase_date <= end_date,
                    TicketItem.user_name.ilike(f"%{user_query}%"),
                )
                .scalar()
                or 0.0
            )

    labels, datasets = build_monthly_chart(chart_year)
    return {
        "article": article_query,
        "user": user_query,
        "supermarket": supermarket_query,
        "has_selected_period": has_selected_period,
        "start_date_value": raw_start_date,
        "end_date_value": raw_end_date,
        "start_date_obj": start_date,
        "end_date_obj": end_date,
        "start_date": start_date.strftime("%Y-%m-%d") if start_date else "",
        "end_date": end_date.strftime("%Y-%m-%d") if end_date else "",
        "chart_year": chart_year,
        "filtered_results": filtered_results,
        "filtered_results_total": filtered_results_total,
        "filtered_results_title": build_filtered_results_title(
            article_query,
            user_query,
            supermarket_query,
            start_date,
            end_date,
            has_selected_period,
        ),
        "has_detail_filters": has_detail_filters,
        "totals_between_dates": round(float(totals_between_dates), 2) if totals_between_dates is not None else None,
        "totals_between_dates_by_user": round(float(totals_between_dates_by_user), 2)
        if totals_between_dates_by_user is not None
        else None,
        "chart_labels": labels,
        "chart_datasets": datasets,
    }


@app.route("/", methods=["GET"])
def index():
    metric_cards = build_metrics()
    filters = collect_filters()
    if filters["has_selected_period"]:
        recent_tickets = (
            Ticket.query.filter(
                Ticket.purchase_date >= filters["start_date_obj"],
                Ticket.purchase_date <= filters["end_date_obj"],
            )
            .order_by(Ticket.purchase_date.desc(), Ticket.id.desc())
            .all()
        )
    else:
        recent_tickets = Ticket.query.order_by(Ticket.purchase_date.desc(), Ticket.id.desc()).limit(10).all()
    all_tickets = Ticket.query.order_by(Ticket.purchase_date.desc(), Ticket.id.desc()).all()
    articles, users, supermarkets = build_lookup_values()
    edit_ticket_id = request.args.get("edit_ticket", "").strip()
    selected_ticket = None
    if edit_ticket_id.isdigit():
        selected_ticket = Ticket.query.get(int(edit_ticket_id))
    years = [
        int(year)
        for (year,) in db.session.query(extract("year", Ticket.purchase_date)).distinct().order_by(
            extract("year", Ticket.purchase_date).desc()
        )
    ]
    current_year = date.today().year
    if current_year not in years:
        years.insert(0, current_year)
    return render_template(
        "index.html",
        metric_cards=metric_cards,
        recent_tickets=recent_tickets,
        all_tickets=all_tickets,
        selected_ticket=selected_ticket,
        selected_ticket_payload=ticket_to_dict(selected_ticket) if selected_ticket else None,
        articles=articles,
        users=users,
        supermarkets=supermarkets,
        years=years,
        filters=filters,
    )


@app.route("/tickets", methods=["POST"])
def create_ticket():
    ticket_id = (request.form.get("ticket_id") or "").strip()
    purchase_date, supermarket, parsed = parse_ticket_form(request.form)
    if not parsed:
        return redirect(url_for("index"))
    items, ticket_total = parsed

    attach_products(items)
    restore_hidden_lookup_values(supermarket, items)
    if ticket_id.isdigit():
        ticket = Ticket.query.get_or_404(int(ticket_id))
        ticket.purchase_date = purchase_date
        ticket.supermarket = supermarket
        ticket.total = ticket_total
        ticket.updated_at = datetime.utcnow()
        ticket.items.clear()
        for item in items:
            ticket.items.append(item)
    else:
        ticket = Ticket(
            purchase_date=purchase_date,
            supermarket=supermarket,
            total=ticket_total,
            items=items,
            updated_at=datetime.utcnow(),
        )
        db.session.add(ticket)
    db.session.commit()
    return redirect(url_for("index"))


@app.route("/tickets/<int:ticket_id>/delete", methods=["POST"])
def delete_ticket(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    db.session.delete(ticket)
    db.session.commit()
    return redirect(url_for("index"))


@app.route("/lookup-options/delete", methods=["POST"])
def delete_lookup_option():
    category = (request.form.get("category") or "").strip()
    value = (request.form.get("value") or "").strip()
    valid_categories = {"article", "user", "supermarket"}
    if category in valid_categories and value:
        exists = LookupExclusion.query.filter_by(category=category, value=value).first()
        if not exists:
            db.session.add(LookupExclusion(category=category, value=value))
            db.session.commit()
    return redirect(url_for("index"))


def json_response(payload, status=200):
    return app.response_class(
        response=json.dumps(payload, ensure_ascii=False),
        status=status,
        mimetype="application/json",
    )


def product_summary(product):
    purchase_count = (
        db.session.query(func.count(TicketItem.id))
        .filter(TicketItem.product_id == product.id)
        .scalar()
        or 0
    )
    last_row = (
        db.session.query(Ticket.purchase_date, Ticket.supermarket, TicketItem.total, TicketItem.quantity)
        .join(TicketItem, Ticket.id == TicketItem.ticket_id)
        .filter(TicketItem.product_id == product.id)
        .order_by(Ticket.purchase_date.desc(), Ticket.id.desc(), TicketItem.id.desc())
        .first()
    )
    last_purchase = None
    if last_row:
        last_purchase = {
            "date": last_row[0].strftime("%Y-%m-%d"),
            "supermarket": last_row[1],
            "line_total": round(float(last_row[2] or 0.0), 2),
            "quantity": float(last_row[3] or 0.0),
        }
    return {
        "id": product.id,
        "name": product.name,
        "active": bool(product.active),
        "purchase_count": int(purchase_count),
        "last_purchase": last_purchase,
    }



def parse_ticket_json(payload):
    if not isinstance(payload, dict):
        return None, None, None, "El cuerpo debe ser un objeto JSON"

    purchase_date = parse_date(payload.get("purchase_date") or payload.get("date"))
    supermarket = str(payload.get("supermarket") or "").strip()
    raw_items = payload.get("items")

    if not purchase_date:
        return None, None, None, "Fecha de compra no válida"
    if not supermarket:
        return None, None, None, "El supermercado es obligatorio"
    if not isinstance(raw_items, list) or not raw_items:
        return None, None, None, "El ticket debe contener al menos un artículo"

    items = []
    ticket_total = 0.0
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        article = normalize_article_name(raw.get("article"))
        if not article:
            continue
        quantity = max(parse_float(raw.get("quantity"), 0.0), 0.0)
        price = max(parse_float(raw.get("price"), 0.0), 0.0)
        net_raw = raw.get("net_price")
        net_price = None if net_raw in (None, "") else max(parse_float(net_raw, 0.0), 0.0)
        discount = max(parse_float(raw.get("discount"), 0.0), 0.0)
        discount_percent = max(parse_float(raw.get("discount_percent"), 0.0), 0.0)
        user_name = normalize_user_name(raw.get("user_name")) or "Sin asignar"
        effective_unit_price = compute_effective_unit_price(
            price,
            net_price=net_price,
            discount=discount,
            discount_percent=discount_percent,
        )
        line_total = round(quantity * effective_unit_price, 2)
        ticket_total += line_total
        items.append(
            TicketItem(
                article=article,
                quantity=quantity,
                price=price,
                net_price=net_price,
                discount=discount,
                discount_percent=discount_percent,
                total=line_total,
                user_name=user_name,
            )
        )

    if not items:
        return None, None, None, "El ticket debe contener al menos un artículo válido"
    return purchase_date, supermarket, (items, round(ticket_total, 2)), None


def save_ticket_json(payload, ticket=None):
    purchase_date, supermarket, parsed, error = parse_ticket_json(payload)
    if error:
        return None, error
    items, ticket_total = parsed
    attach_products(items)
    restore_hidden_lookup_values(supermarket, items)
    if ticket is None:
        ticket = Ticket(
            purchase_date=purchase_date,
            supermarket=supermarket,
            total=ticket_total,
            items=items,
            updated_at=datetime.utcnow(),
        )
        db.session.add(ticket)
    else:
        ticket.purchase_date = purchase_date
        ticket.supermarket = supermarket
        ticket.total = ticket_total
        ticket.updated_at = datetime.utcnow()
        ticket.items.clear()
        for item in items:
            ticket.items.append(item)
    db.session.commit()
    return ticket, None


def filters_to_json(filters):
    return {
        "article": filters["article"],
        "user": filters["user"],
        "supermarket": filters["supermarket"],
        "start_date": filters["start_date"],
        "end_date": filters["end_date"],
        "has_selected_period": filters["has_selected_period"],
        "chart_year": filters["chart_year"],
        "filtered_results_title": filters["filtered_results_title"],
        "filtered_results_total": filters["filtered_results_total"],
        "has_detail_filters": filters["has_detail_filters"],
        "totals_between_dates": filters["totals_between_dates"],
        "totals_between_dates_by_user": filters["totals_between_dates_by_user"],
        "chart_labels": filters["chart_labels"],
        "chart_datasets": filters["chart_datasets"],
        "filtered_results": [
            {
                "date": row[0].strftime("%Y-%m-%d"),
                "supermarket": row[1],
                "article": row[2],
                "quantity": float(row[3] or 0.0),
                "total": round(float(row[4] or 0.0), 2),
                "user_name": row[5],
            }
            for row in filters["filtered_results"]
        ],
    }


@app.route("/api/v1/dashboard", methods=["GET"])
def api_v1_dashboard():
    filters = collect_filters()
    articles, users, supermarkets = build_lookup_values()
    if filters["has_selected_period"]:
        recent_tickets = (
            Ticket.query.filter(
                Ticket.purchase_date >= filters["start_date_obj"],
                Ticket.purchase_date <= filters["end_date_obj"],
            )
            .order_by(Ticket.purchase_date.desc(), Ticket.id.desc())
            .limit(50)
            .all()
        )
    else:
        recent_tickets = (
            Ticket.query.order_by(Ticket.purchase_date.desc(), Ticket.id.desc())
            .limit(10)
            .all()
        )
    years = [
        int(year)
        for (year,) in db.session.query(extract("year", Ticket.purchase_date))
        .distinct()
        .order_by(extract("year", Ticket.purchase_date).desc())
    ]
    current_year = date.today().year
    if current_year not in years:
        years.insert(0, current_year)
    return json_response(
        {
            "metrics": build_metrics(),
            "filters": filters_to_json(filters),
            "lookups": {
                "articles": articles,
                "users": users,
                "supermarkets": supermarkets,
            },
            "years": years,
            "recent_tickets": [ticket_to_dict(ticket) for ticket in recent_tickets],
            "counts": {
                "products": Product.query.count(),
                "tickets": Ticket.query.count(),
                "items": TicketItem.query.count(),
            },
        }
    )


@app.route("/api/v1/tickets", methods=["GET", "POST"])
def api_v1_tickets():
    if request.method == "POST":
        ticket, error = save_ticket_json(request.get_json(silent=True))
        if error:
            return json_response({"detail": error}, 400)
        return json_response({"ok": True, "ticket": ticket_to_dict(ticket)}, 201)

    try:
        limit = max(1, min(1000, int(request.args.get("limit", "200"))))
    except ValueError:
        limit = 200
    tickets = (
        Ticket.query.order_by(Ticket.purchase_date.desc(), Ticket.id.desc())
        .limit(limit)
        .all()
    )
    return json_response(
        {"items": [ticket_to_dict(ticket) for ticket in tickets], "count": len(tickets)}
    )


@app.route("/api/v1/tickets/<int:ticket_id>", methods=["GET", "PUT", "DELETE"])
def api_v1_ticket(ticket_id):
    ticket = Ticket.query.get(ticket_id)
    if ticket is None:
        return json_response({"detail": "Ticket no encontrado"}, 404)
    if request.method == "GET":
        return json_response(ticket_to_dict(ticket))
    if request.method == "DELETE":
        db.session.delete(ticket)
        db.session.commit()
        return json_response({"ok": True, "deleted_ticket_id": ticket_id})

    ticket, error = save_ticket_json(request.get_json(silent=True), ticket=ticket)
    if error:
        return json_response({"detail": error}, 400)
    return json_response({"ok": True, "ticket": ticket_to_dict(ticket)})


@app.route("/api/v1/lookups", methods=["GET"])
def api_v1_lookups():
    articles, users, supermarkets = build_lookup_values()
    return json_response(
        {"articles": articles, "users": users, "supermarkets": supermarkets}
    )


@app.route("/api/v1/lookups/<category>", methods=["DELETE"])
def api_v1_delete_lookup(category):
    valid_categories = {"article", "user", "supermarket"}
    value = (request.args.get("value") or "").strip()
    if category not in valid_categories:
        return json_response({"detail": "Categoría de lista no válida"}, 400)
    if not value:
        return json_response({"detail": "Indica el valor que quieres ocultar"}, 400)
    exists = LookupExclusion.query.filter_by(category=category, value=value).first()
    if not exists:
        db.session.add(LookupExclusion(category=category, value=value))
        db.session.commit()
    return json_response({"ok": True, "category": category, "value": value})


@app.route("/api/tickets", methods=["GET"])
def tickets_api():
    tickets = Ticket.query.order_by(Ticket.purchase_date.desc(), Ticket.id.desc()).all()
    return json_response([ticket_to_dict(ticket) for ticket in tickets])


@app.route("/api/v1/admin/reset", methods=["POST"])
def api_reset_database():
    payload = request.get_json(silent=True) or {}
    if payload.get("confirmation") != "BORRAR GASTOS":
        return json_response({"detail": "Confirmación incorrecta"}, 400)
    try:
        db.session.query(TicketItem).delete(synchronize_session=False)
        db.session.query(Ticket).delete(synchronize_session=False)
        db.session.query(Product).delete(synchronize_session=False)
        db.session.query(LookupExclusion).delete(synchronize_session=False)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return json_response({"ok": True, "tickets": 0, "items": 0, "products": 0})


@app.route("/api/v1/health", methods=["GET"])
def api_v1_health():
    return json_response(
        {
            "ok": True,
            "service": "gastos-comida",
            "api_version": "1",
            "products": Product.query.count(),
            "tickets": Ticket.query.count(),
            "items": TicketItem.query.count(),
        }
    )


@app.route("/api/v1/products", methods=["GET"])
def api_v1_products():
    query = (request.args.get("q") or "").strip()
    try:
        limit = max(1, min(500, int(request.args.get("limit", "100"))))
    except ValueError:
        limit = 100
    products_query = Product.query.filter_by(active=True)
    if query:
        products_query = products_query.filter(Product.name.ilike(f"%{query}%"))
    total = products_query.count()
    products = products_query.order_by(Product.name.asc(), Product.id.asc()).limit(limit).all()
    return json_response(
        {
            "items": [product_summary(product) for product in products],
            "count": len(products),
            "total": total,
        }
    )


@app.route("/api/v1/products/<int:product_id>", methods=["GET"])
def api_v1_product(product_id):
    product = Product.query.get(product_id)
    if product is None:
        return json_response({"detail": "Producto no encontrado"}, 404)
    return json_response(product_summary(product))


@app.route("/api/v1/products/<int:product_id>/stats", methods=["GET"])
def api_v1_product_stats(product_id):
    product = Product.query.get(product_id)
    if product is None:
        return json_response({"detail": "Producto no encontrado"}, 404)
    rows = (
        db.session.query(
            Ticket.purchase_date,
            Ticket.supermarket,
            TicketItem.quantity,
            TicketItem.total,
        )
        .join(TicketItem, Ticket.id == TicketItem.ticket_id)
        .filter(TicketItem.product_id == product.id)
        .order_by(Ticket.purchase_date.desc(), Ticket.id.desc(), TicketItem.id.desc())
        .all()
    )
    quantity_total = sum(float(row[2] or 0.0) for row in rows)
    spend_total = sum(float(row[3] or 0.0) for row in rows)
    priced_rows = []
    supermarket_map = {}

    reference_date = rows[0][0] if rows else None

    def recency_weight(purchase_date):
        if reference_date is None or purchase_date is None:
            return 1.0
        age_days = max(0, (reference_date - purchase_date).days)
        if age_days <= 30:
            return 1.0
        if age_days <= 90:
            return 0.8
        if age_days <= 180:
            return 0.55
        if age_days <= 365:
            return 0.3
        return 0.15

    def confidence_label(priced_count, recent_priced_count):
        if priced_count >= 4 and recent_priced_count >= 2:
            return "high"
        if priced_count >= 2 and recent_priced_count >= 1:
            return "medium"
        return "low"

    for purchase_date, supermarket, quantity, line_total in rows:
        quantity = float(quantity or 0.0)
        line_total = float(line_total or 0.0)
        unit_price = (line_total / quantity) if quantity > 0 else None
        stats = supermarket_map.setdefault(
            supermarket,
            {
                "supermarket": supermarket,
                "purchase_count": 0,
                "unit_price_total": 0.0,
                "priced_count": 0,
                "recent_unit_price_total": 0.0,
                "recent_priced_count": 0,
                "weighted_unit_price_total": 0.0,
                "weight_total": 0.0,
                "last_unit_price": None,
                "last_date": None,
            },
        )
        stats["purchase_count"] += 1

        if unit_price is not None:
            priced_rows.append(
                {
                    "date": purchase_date,
                    "supermarket": supermarket,
                    "unit_price": unit_price,
                }
            )
            weight = recency_weight(purchase_date)
            stats["unit_price_total"] += unit_price
            stats["priced_count"] += 1
            stats["weighted_unit_price_total"] += unit_price * weight
            stats["weight_total"] += weight
            if reference_date is not None and (reference_date - purchase_date).days <= 180:
                stats["recent_unit_price_total"] += unit_price
                stats["recent_priced_count"] += 1
            if stats["last_date"] is None or purchase_date > stats["last_date"]:
                stats["last_date"] = purchase_date
                stats["last_unit_price"] = unit_price

    supermarket_stats = []
    for stats in supermarket_map.values():
        average_unit_price = (
            stats["unit_price_total"] / stats["priced_count"]
            if stats["priced_count"]
            else None
        )
        recent_average_unit_price = (
            stats["recent_unit_price_total"] / stats["recent_priced_count"]
            if stats["recent_priced_count"]
            else None
        )
        recommendation_unit_price = (
            stats["weighted_unit_price_total"] / stats["weight_total"]
            if stats["weight_total"]
            else None
        )
        supermarket_stats.append(
            {
                "supermarket": stats["supermarket"],
                "purchase_count": stats["purchase_count"],
                "priced_count": stats["priced_count"],
                "recent_priced_count": stats["recent_priced_count"],
                "average_unit_price": (
                    round(average_unit_price, 2)
                    if average_unit_price is not None
                    else None
                ),
                "recent_average_unit_price": (
                    round(recent_average_unit_price, 2)
                    if recent_average_unit_price is not None
                    else None
                ),
                "recommendation_unit_price": (
                    round(recommendation_unit_price, 2)
                    if recommendation_unit_price is not None
                    else None
                ),
                "recommendation_confidence": confidence_label(
                    stats["priced_count"], stats["recent_priced_count"]
                ),
                "last_unit_price": (
                    round(stats["last_unit_price"], 2)
                    if stats["last_unit_price"] is not None
                    else None
                ),
                "last_date": (
                    stats["last_date"].strftime("%Y-%m-%d")
                    if stats["last_date"] is not None
                    else None
                ),
            }
        )
    supermarket_stats.sort(
        key=lambda item: (
            item["recommendation_unit_price"] is None,
            item["recommendation_unit_price"]
            if item["recommendation_unit_price"] is not None
            else 999999,
            item["supermarket"].casefold(),
        )
    )

    habitual = None
    if supermarket_stats:
        habitual = sorted(
            supermarket_stats,
            key=lambda item: (-item["purchase_count"], item["supermarket"].casefold()),
        )[0]

    priced_candidates = [
        item for item in supermarket_stats if item["recommendation_unit_price"] is not None
    ]
    best_candidate = priced_candidates[0] if priced_candidates else None
    recommended = best_candidate
    recommendation_reason = "best_recent_value" if best_candidate else None

    if habitual and habitual.get("recommendation_unit_price") is not None:
        if best_candidate is None:
            recommended = habitual
            recommendation_reason = "habitual_only_priced"
        elif best_candidate["supermarket"] == habitual["supermarket"]:
            recommended = habitual
            recommendation_reason = "habitual_is_best"
        else:
            habitual_price = float(habitual["recommendation_unit_price"])
            candidate_price = float(best_candidate["recommendation_unit_price"])
            saving = habitual_price - candidate_price
            minimum_saving = max(0.10, habitual_price * 0.05)
            candidate_has_evidence = (
                int(best_candidate.get("priced_count") or 0) >= 2
                and int(best_candidate.get("recent_priced_count") or 0) >= 1
            )
            habitual_has_evidence = int(habitual.get("priced_count") or 0) >= 2

            if saving <= 0 or saving < minimum_saving:
                recommended = habitual
                recommendation_reason = "habitual_small_difference"
            elif not candidate_has_evidence and habitual_has_evidence:
                recommended = habitual
                recommendation_reason = "habitual_insufficient_alternative_evidence"
            else:
                recommended = best_candidate
                recommendation_reason = "best_recent_value"

    if recommended is not None:
        recommended = dict(recommended)
        recommended["recommendation_reason"] = recommendation_reason

    latest = None
    if rows:
        latest_unit_price = (
            float(rows[0][3] or 0.0) / float(rows[0][2] or 0.0)
            if float(rows[0][2] or 0.0) > 0
            else None
        )
        latest = {
            "date": rows[0][0].strftime("%Y-%m-%d"),
            "supermarket": rows[0][1],
            "quantity": float(rows[0][2] or 0.0),
            "line_total": round(float(rows[0][3] or 0.0), 2),
            "unit_price": round(latest_unit_price, 2) if latest_unit_price is not None else None,
        }

    unit_prices = [row["unit_price"] for row in priced_rows]
    latest_unit_price = unit_prices[0] if unit_prices else None
    previous_unit_price = unit_prices[1] if len(unit_prices) > 1 else None
    price_change_percent = None
    if latest_unit_price is not None and previous_unit_price not in (None, 0):
        price_change_percent = round(
            ((latest_unit_price - previous_unit_price) / previous_unit_price) * 100,
            1,
        )

    return json_response(
        {
            "id": product.id,
            "name": product.name,
            "purchase_count": len(rows),
            "quantity_total": round(quantity_total, 3),
            "spend_total": round(spend_total, 2),
            "average_line_total": round(spend_total / len(rows), 2) if rows else 0.0,
            "average_unit_price": round(sum(unit_prices) / len(unit_prices), 2) if unit_prices else None,
            "lowest_unit_price": round(min(unit_prices), 2) if unit_prices else None,
            "highest_unit_price": round(max(unit_prices), 2) if unit_prices else None,
            "price_change_percent": price_change_percent,
            "recommended_supermarket": recommended,
            "habitual_supermarket": habitual,
            "supermarket_stats": supermarket_stats,
            "recommendation": {
                "reason": recommendation_reason,
                "confidence": (
                    recommended.get("recommendation_confidence")
                    if recommended is not None
                    else None
                ),
                "reference_date": (
                    reference_date.strftime("%Y-%m-%d")
                    if reference_date is not None
                    else None
                ),
                "recent_window_days": 180,
                "minimum_saving_percent": 5.0,
                "minimum_saving_unit": 0.10,
            },
            "last_purchase": latest,
        }
    )

@app.route("/api/v1/spending/summary", methods=["GET"])
def api_v1_spending_summary():
    start = parse_date(request.args.get("from"))
    end = parse_date(request.args.get("to"))
    query = db.session.query(func.coalesce(func.sum(Ticket.total), 0.0))
    if start:
        query = query.filter(Ticket.purchase_date >= start)
    if end:
        query = query.filter(Ticket.purchase_date <= end)
    total = float(query.scalar() or 0.0)
    ticket_query = Ticket.query
    if start:
        ticket_query = ticket_query.filter(Ticket.purchase_date >= start)
    if end:
        ticket_query = ticket_query.filter(Ticket.purchase_date <= end)
    return json_response(
        {
            "from": start.strftime("%Y-%m-%d") if start else None,
            "to": end.strftime("%Y-%m-%d") if end else None,
            "total": round(total, 2),
            "ticket_count": ticket_query.count(),
        }
    )


@app.route("/api/v1/purchases/changes", methods=["GET"])
def api_v1_purchase_changes():
    after_raw = (request.args.get("after") or "").strip()
    try:
        after_id = max(0, int(request.args.get("after_id", "0")))
    except ValueError:
        after_id = 0
    try:
        limit = max(1, min(200, int(request.args.get("limit", "50"))))
    except ValueError:
        limit = 50

    after = None
    if after_raw:
        try:
            after = datetime.fromisoformat(after_raw.replace("Z", "+00:00"))
            if after.tzinfo is not None:
                after = after.replace(tzinfo=None)
        except ValueError:
            return json_response({"detail": "Cursor de sincronización no válido"}, 400)

    query = Ticket.query
    if after is not None:
        query = query.filter(
            db.or_(
                Ticket.updated_at > after,
                db.and_(Ticket.updated_at == after, Ticket.id > after_id),
            )
        )

    tickets = (
        query.order_by(Ticket.updated_at.asc(), Ticket.id.asc())
        .limit(limit)
        .all()
    )
    items = [ticket_to_dict(ticket) for ticket in tickets]
    if tickets:
        cursor_ticket = tickets[-1]
        cursor = {
            "updated_at": cursor_ticket.updated_at.isoformat(timespec="microseconds"),
            "ticket_id": cursor_ticket.id,
        }
    else:
        cursor = {
            "updated_at": after.isoformat(timespec="microseconds") if after else None,
            "ticket_id": after_id,
        }
    return json_response(
        {
            "items": items,
            "count": len(items),
            "cursor": cursor,
            "has_more": len(items) == limit,
        }
    )


@app.route("/api/v1/purchases/recent", methods=["GET"])
def api_v1_recent_purchases():
    try:
        after_ticket_id = max(0, int(request.args.get("after_ticket_id", "0")))
    except ValueError:
        after_ticket_id = 0
    try:
        limit = max(1, min(200, int(request.args.get("limit", "50"))))
    except ValueError:
        limit = 50
    tickets = (
        Ticket.query.filter(Ticket.id > after_ticket_id)
        .order_by(Ticket.id.asc())
        .limit(limit)
        .all()
    )
    return json_response(
        {
            "items": [ticket_to_dict(ticket) for ticket in tickets],
            "count": len(tickets),
            "last_ticket_id": tickets[-1].id if tickets else after_ticket_id,
        }
    )


with app.app_context():
    db.create_all()
    ensure_ticket_schema()
    ensure_ticket_item_schema()
    normalize_stored_items()
    backfill_products()
    normalize_discount_values()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)

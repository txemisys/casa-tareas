import json
import os
import re
from datetime import date, datetime

from flask import Flask, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import extract, func, inspect, text


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.join(os.path.dirname(BASE_DIR), "data")
os.makedirs(INSTANCE_DIR, exist_ok=True)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(INSTANCE_DIR, 'gastos.db')}",
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    purchase_date = db.Column(db.Date, nullable=False, index=True)
    supermarket = db.Column(db.String(120), nullable=False, index=True)
    total = db.Column(db.Float, nullable=False, default=0.0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    items = db.relationship(
        "TicketItem",
        backref="ticket",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="TicketItem.id",
    )


class TicketItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("ticket.id"), nullable=False, index=True)
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
        "items": [
            {
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

    restore_hidden_lookup_values(supermarket, items)
    if ticket_id.isdigit():
        ticket = Ticket.query.get_or_404(int(ticket_id))
        ticket.purchase_date = purchase_date
        ticket.supermarket = supermarket
        ticket.total = ticket_total
        ticket.items.clear()
        for item in items:
            ticket.items.append(item)
    else:
        ticket = Ticket(purchase_date=purchase_date, supermarket=supermarket, total=ticket_total, items=items)
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


@app.route("/api/tickets", methods=["GET"])
def tickets_api():
    tickets = Ticket.query.order_by(Ticket.purchase_date.desc(), Ticket.id.desc()).all()
    return app.response_class(
        response=json.dumps([ticket_to_dict(ticket) for ticket in tickets], ensure_ascii=True),
        mimetype="application/json",
    )


with app.app_context():
    db.create_all()
    ensure_ticket_item_schema()
    normalize_stored_items()
    normalize_discount_values()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)

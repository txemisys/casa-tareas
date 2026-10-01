import importlib.util
import os
import sys
import uuid
from pathlib import Path


APP_PATH = Path(__file__).resolve().parents[1] / "app" / "app.py"


def load_gastos_app(tmp_path):
    db_path = tmp_path / "gastos.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    module_name = f"gastos_app_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def ticket_form(article="Leche 1 l", supermarket="Coop", purchase_date="2026-10-01"):
    return {
        "purchase_date": purchase_date,
        "supermarket": supermarket,
        "article[]": [article],
        "quantity[]": ["2"],
        "price[]": ["1.95"],
        "net_price[]": [""],
        "discount[]": [""],
        "discount_percent[]": [""],
        "user_name[]": ["Jose"],
    }


def test_product_identity_is_created_and_reused(tmp_path):
    module = load_gastos_app(tmp_path)
    client = module.app.test_client()

    first = client.post("/tickets", data=ticket_form())
    assert first.status_code == 302

    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json == {
        "ok": True,
        "service": "gastos-comida",
        "api_version": "1",
        "products": 1,
        "tickets": 1,
        "items": 1,
    }

    products = client.get("/api/v1/products?q=leche")
    assert products.status_code == 200
    assert products.json["total"] == 1
    product = products.json["items"][0]
    assert product["name"] == "Leche"
    product_id = product["id"]

    second = client.post(
        "/tickets",
        data=ticket_form(
            article="Leche 500 ml",
            supermarket="Migros",
            purchase_date="2026-10-02",
        ),
    )
    assert second.status_code == 302

    products = client.get("/api/v1/products?q=leche").json
    assert products["total"] == 1
    assert products["items"][0]["id"] == product_id
    assert products["items"][0]["purchase_count"] == 2

    stats = client.get(f"/api/v1/products/{product_id}/stats")
    assert stats.status_code == 200
    assert stats.json["purchase_count"] == 2
    assert stats.json["last_purchase"]["supermarket"] == "Migros"

    recent = client.get("/api/v1/purchases/recent?after_ticket_id=0")
    assert recent.status_code == 200
    assert recent.json["count"] == 2
    assert all(
        item["product_id"] == product_id
        for ticket in recent.json["items"]
        for item in ticket["items"]
    )


def test_backfill_links_unassigned_historical_items(tmp_path):
    module = load_gastos_app(tmp_path)

    with module.app.app_context():
        ticket = module.Ticket(
            purchase_date=module.date(2026, 1, 15),
            supermarket="Lidl",
            total=3.5,
        )
        item = module.TicketItem(
            article="Pan 500 g",
            quantity=1,
            price=3.5,
            total=3.5,
            user_name="Cosi",
            product_id=None,
        )
        ticket.items.append(item)
        module.db.session.add(ticket)
        module.db.session.commit()

        assert item.product_id is None
        module.backfill_products()
        module.db.session.refresh(item)

        assert item.product_id is not None
        product = module.Product.query.get(item.product_id)
        assert product.name == "Pan"

        before = module.Product.query.count()
        module.backfill_products()
        assert module.Product.query.count() == before

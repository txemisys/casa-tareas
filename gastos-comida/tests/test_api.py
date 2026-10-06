import importlib.util
import os
import sqlite3
import sys
import uuid
from pathlib import Path

import pytest


APP_PATH = Path(__file__).resolve().parents[1] / "app" / "app.py"


def load_gastos_app(tmp_path, require_existing=False, db_path=None):
    db_path = db_path or (tmp_path / "gastos.db")
    previous_url = os.environ.get("DATABASE_URL")
    previous_guard = os.environ.get("GASTOS_REQUIRE_EXISTING_DB")
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["GASTOS_REQUIRE_EXISTING_DB"] = "1" if require_existing else ""
    module_name = f"gastos_app_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url
        if previous_guard is None:
            os.environ.pop("GASTOS_REQUIRE_EXISTING_DB", None)
        else:
            os.environ["GASTOS_REQUIRE_EXISTING_DB"] = previous_guard


def create_legacy_database(path):
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE ticket (
            id INTEGER PRIMARY KEY,
            purchase_date DATE NOT NULL,
            supermarket VARCHAR(120) NOT NULL,
            total FLOAT NOT NULL DEFAULT 0,
            created_at DATETIME NOT NULL
        );
        CREATE TABLE ticket_item (
            id INTEGER PRIMARY KEY,
            ticket_id INTEGER NOT NULL,
            article VARCHAR(200) NOT NULL,
            quantity FLOAT NOT NULL DEFAULT 1,
            price FLOAT NOT NULL DEFAULT 0,
            net_price FLOAT,
            discount FLOAT NOT NULL DEFAULT 0,
            discount_percent FLOAT NOT NULL DEFAULT 0,
            total FLOAT NOT NULL DEFAULT 0,
            user_name VARCHAR(120) NOT NULL,
            FOREIGN KEY(ticket_id) REFERENCES ticket(id)
        );
        CREATE TABLE lookup_exclusion (
            id INTEGER PRIMARY KEY,
            category VARCHAR(40) NOT NULL,
            value VARCHAR(200) NOT NULL
        );
        INSERT INTO ticket(id,purchase_date,supermarket,total,created_at)
        VALUES(1,'2026-07-31','Coop',5.85,'2026-07-31 12:00:00');
        INSERT INTO ticket_item(
            id,ticket_id,article,quantity,price,net_price,discount,
            discount_percent,total,user_name
        ) VALUES(1,1,'Leche',3,1.95,NULL,0,0,5.85,'Jose');
        """
    )
    connection.commit()
    connection.close()


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



def test_protected_mode_refuses_missing_database(tmp_path):
    missing = tmp_path / "missing.db"
    with pytest.raises(RuntimeError, match="no crear una base vacía"):
        load_gastos_app(tmp_path, require_existing=True, db_path=missing)
    assert not missing.exists()


def test_protected_mode_migrates_existing_legacy_database_without_losing_rows(tmp_path):
    legacy = tmp_path / "legacy.db"
    create_legacy_database(legacy)

    before = sqlite3.connect(legacy)
    before_ticket_count = before.execute("SELECT COUNT(*) FROM ticket").fetchone()[0]
    before_item_count = before.execute("SELECT COUNT(*) FROM ticket_item").fetchone()[0]
    before_total = before.execute("SELECT SUM(total) FROM ticket").fetchone()[0]
    before.close()

    module = load_gastos_app(tmp_path, require_existing=True, db_path=legacy)

    with module.app.app_context():
        assert module.Ticket.query.count() == before_ticket_count == 1
        assert module.TicketItem.query.count() == before_item_count == 1
        assert module.db.session.query(module.func.sum(module.Ticket.total)).scalar() == before_total == 5.85
        assert module.Product.query.count() == 1
        item = module.TicketItem.query.one()
        assert item.product_id is not None
        assert item.product.name == "Leche"


def test_json_ticket_crud_dashboard_and_lookup_api(tmp_path):
    module = load_gastos_app(tmp_path)
    client = module.app.test_client()

    payload = {
        "purchase_date": "2026-10-04",
        "supermarket": "Coop",
        "items": [
            {
                "article": "Yogur 500 g",
                "quantity": 2,
                "price": 2.0,
                "net_price": "",
                "discount": 0.25,
                "discount_percent": "",
                "user_name": "Jose",
            },
            {
                "article": "Pan",
                "quantity": 1,
                "price": 3.0,
                "net_price": 2.5,
                "discount": "",
                "discount_percent": "",
                "user_name": "Cosi",
            },
        ],
    }

    created = client.post("/api/v1/tickets", json=payload)
    assert created.status_code == 201
    ticket = created.json["ticket"]
    assert ticket["supermarket"] == "Coop"
    assert ticket["total"] == 6.0
    ticket_id = ticket["id"]

    fetched = client.get(f"/api/v1/tickets/{ticket_id}")
    assert fetched.status_code == 200
    assert len(fetched.json["items"]) == 2

    dashboard = client.get("/api/v1/dashboard?user=Jose&chart_year=2026")
    assert dashboard.status_code == 200
    body = dashboard.json
    assert len(body["metrics"]) == 6
    assert body["counts"]["tickets"] == 1
    assert body["filters"]["user"] == "Jose"
    assert body["filters"]["filtered_results_total"] == 3.5
    assert "Yogur" in body["lookups"]["articles"]
    assert len(body["filters"]["chart_labels"]) == 12

    updated_payload = {
        **payload,
        "supermarket": "Migros",
        "items": [
            {
                "article": "Pan",
                "quantity": 2,
                "price": 3.0,
                "net_price": "",
                "discount": "",
                "discount_percent": 10,
                "user_name": "Cosi",
            }
        ],
    }
    updated = client.put(f"/api/v1/tickets/{ticket_id}", json=updated_payload)
    assert updated.status_code == 200
    assert updated.json["ticket"]["supermarket"] == "Migros"
    assert updated.json["ticket"]["total"] == 5.4

    lookups = client.get("/api/v1/lookups")
    assert lookups.status_code == 200
    assert "Migros" in lookups.json["supermarkets"]

    hidden = client.delete("/api/v1/lookups/supermarket?value=Migros")
    assert hidden.status_code == 200
    assert "Migros" not in client.get("/api/v1/lookups").json["supermarkets"]

    deleted = client.delete(f"/api/v1/tickets/{ticket_id}")
    assert deleted.status_code == 200
    assert client.get(f"/api/v1/tickets/{ticket_id}").status_code == 404


def test_json_ticket_api_rejects_invalid_payload(tmp_path):
    module = load_gastos_app(tmp_path)
    client = module.app.test_client()

    response = client.post(
        "/api/v1/tickets",
        json={"purchase_date": "bad", "supermarket": "", "items": []},
    )
    assert response.status_code == 400
    assert "Fecha" in response.json["detail"]


def test_admin_reset_requires_confirmation_and_clears_gastos(tmp_path):
    module = load_gastos_app(tmp_path)
    client = module.app.test_client()

    created = client.post("/tickets", data=ticket_form())
    assert created.status_code == 302
    assert client.get("/api/v1/health").json["tickets"] == 1

    rejected = client.post("/api/v1/admin/reset", json={"confirmation": "no"})
    assert rejected.status_code == 400
    assert client.get("/api/v1/health").json["tickets"] == 1

    reset = client.post(
        "/api/v1/admin/reset",
        json={"confirmation": "BORRAR GASTOS"},
    )
    assert reset.status_code == 200
    assert reset.json["ok"] is True

    health = client.get("/api/v1/health").json
    assert health["tickets"] == 0
    assert health["items"] == 0
    assert health["products"] == 0

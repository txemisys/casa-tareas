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


def test_purchase_changes_tracks_new_and_edited_tickets(tmp_path):
    module = load_gastos_app(tmp_path)
    client = module.app.test_client()

    created = client.post(
        "/api/v1/tickets",
        json={
            "purchase_date": "2026-10-01",
            "supermarket": "Coop",
            "items": [
                {
                    "article": "Leche 1 l",
                    "quantity": 1,
                    "price": 2.0,
                    "user_name": "Jose",
                }
            ],
        },
    )
    assert created.status_code == 201
    ticket = created.json["ticket"]
    assert ticket["updated_at"]

    latest = client.get("/api/v1/purchases/changes?latest=1")
    assert latest.status_code == 200
    cursor = latest.json["cursor"]
    assert latest.json["items"] == []
    assert cursor["ticket_id"] == ticket["id"]

    updated = client.put(
        f"/api/v1/tickets/{ticket['id']}",
        json={
            "purchase_date": "2026-10-02",
            "supermarket": "Migros",
            "items": [
                {
                    "article": "Leche 1 l",
                    "quantity": 2,
                    "price": 1.8,
                    "user_name": "Jose",
                }
            ],
        },
    )
    assert updated.status_code == 200
    assert updated.json["ticket"]["updated_at"] >= ticket["updated_at"]

    changes = client.get(
        "/api/v1/purchases/changes",
        query_string={
            "after": cursor["updated_at"],
            "after_id": cursor["ticket_id"],
        },
    )
    assert changes.status_code == 200
    assert changes.json["count"] == 1
    changed = changes.json["items"][0]
    assert changed["id"] == ticket["id"]
    assert changed["date"] == "2026-10-02"
    assert changed["supermarket"] == "Migros"
    assert changes.json["cursor"]["ticket_id"] == ticket["id"]


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
        ticket = module.Ticket.query.one()
        assert ticket.updated_at is not None


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

    spending = client.get("/api/v1/spending/summary?from=2026-10-01&to=2026-10-31")
    assert spending.status_code == 200
    assert spending.json["total"] == 6.0
    assert spending.json["ticket_count"] == 1
    assert spending.json["by_user"] == [
        {"user_name": "Jose", "total": 3.5, "line_count": 1},
        {"user_name": "Cosi", "total": 2.5, "line_count": 1},
    ]

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


def test_product_stats_include_price_and_supermarket_recommendations(tmp_path):
    module = load_gastos_app(tmp_path)
    client = module.app.test_client()

    assert client.post(
        "/tickets",
        data=ticket_form(article="Café 500 g", supermarket="Coop", purchase_date="2026-09-01")
        | {"quantity[]": ["1"], "price[]": ["10.00"]},
    ).status_code == 302
    assert client.post(
        "/tickets",
        data=ticket_form(article="Café 500 g", supermarket="Migros", purchase_date="2026-09-10")
        | {"quantity[]": ["1"], "price[]": ["8.00"]},
    ).status_code == 302
    assert client.post(
        "/tickets",
        data=ticket_form(article="Café 500 g", supermarket="Migros", purchase_date="2026-10-01")
        | {"quantity[]": ["1"], "price[]": ["9.00"]},
    ).status_code == 302

    product = client.get("/api/v1/products?q=caf").json["items"][0]
    stats = client.get(f"/api/v1/products/{product['id']}/stats")
    assert stats.status_code == 200
    data = stats.json

    assert data["purchase_count"] == 3
    assert data["lowest_unit_price"] == 8.0
    assert data["highest_unit_price"] == 10.0
    assert data["average_unit_price"] == 9.0
    assert data["last_purchase"]["unit_price"] == 9.0
    assert data["price_change_percent"] == 12.5
    assert data["recommended_supermarket"]["supermarket"] == "Migros"
    assert data["recommended_supermarket"]["average_unit_price"] == 8.5
    assert data["habitual_supermarket"]["supermarket"] == "Migros"
    assert data["habitual_supermarket"]["purchase_count"] == 2
    assert data["recommended_supermarket"]["recommendation_unit_price"] == 8.5
    assert data["recommendation"]["confidence"] == "medium"
    assert data["recommendation"]["reason"] == "habitual_is_best"
    assert data["recommendation"]["recent_window_days"] == 180


def test_product_recommendation_ignores_single_old_bargain_when_habitual_has_evidence(tmp_path):
    module = load_gastos_app(tmp_path)
    client = module.app.test_client()

    purchases = [
        ("Coop", "2026-08-15", "4.00"),
        ("Coop", "2026-09-15", "4.10"),
        ("Coop", "2026-10-01", "4.00"),
        ("Migros", "2025-01-01", "1.00"),
    ]
    for supermarket, purchase_date, price in purchases:
        response = client.post(
            "/tickets",
            data=ticket_form(
                article="Detergente 1 l",
                supermarket=supermarket,
                purchase_date=purchase_date,
            )
            | {"quantity[]": ["1"], "price[]": [price]},
        )
        assert response.status_code == 302

    product = client.get("/api/v1/products?q=detergente").json["items"][0]
    data = client.get(f"/api/v1/products/{product['id']}/stats").json

    assert data["habitual_supermarket"]["supermarket"] == "Coop"
    assert data["recommended_supermarket"]["supermarket"] == "Coop"
    assert data["recommendation"]["reason"] == "habitual_insufficient_alternative_evidence"
    migros = next(x for x in data["supermarket_stats"] if x["supermarket"] == "Migros")
    assert migros["priced_count"] == 1
    assert migros["recent_priced_count"] == 0
    assert migros["recommendation_confidence"] == "low"


def test_product_recommendation_keeps_habitual_store_for_small_saving(tmp_path):
    module = load_gastos_app(tmp_path)
    client = module.app.test_client()

    purchases = [
        ("Coop", "2026-08-10", "5.00"),
        ("Coop", "2026-09-10", "5.00"),
        ("Coop", "2026-10-01", "5.00"),
        ("Migros", "2026-09-01", "4.85"),
        ("Migros", "2026-09-20", "4.85"),
    ]
    for supermarket, purchase_date, price in purchases:
        response = client.post(
            "/tickets",
            data=ticket_form(
                article="Arroz 1 kg",
                supermarket=supermarket,
                purchase_date=purchase_date,
            )
            | {"quantity[]": ["1"], "price[]": [price]},
        )
        assert response.status_code == 302

    product = client.get("/api/v1/products?q=arroz").json["items"][0]
    data = client.get(f"/api/v1/products/{product['id']}/stats").json

    assert data["habitual_supermarket"]["supermarket"] == "Coop"
    assert data["recommended_supermarket"]["supermarket"] == "Coop"
    assert data["recommendation"]["reason"] == "habitual_small_difference"
    assert data["recommended_supermarket"]["recommendation_confidence"] == "medium"


def test_product_recommendation_reports_high_confidence_with_repeated_recent_prices(tmp_path):
    module = load_gastos_app(tmp_path)
    client = module.app.test_client()

    for purchase_date, price in [
        ("2026-07-20", "3.20"),
        ("2026-08-15", "3.10"),
        ("2026-09-10", "3.00"),
        ("2026-10-01", "3.05"),
    ]:
        response = client.post(
            "/tickets",
            data=ticket_form(
                article="Pasta 500 g",
                supermarket="Lidl",
                purchase_date=purchase_date,
            )
            | {"quantity[]": ["1"], "price[]": [price]},
        )
        assert response.status_code == 302

    product = client.get("/api/v1/products?q=pasta").json["items"][0]
    data = client.get(f"/api/v1/products/{product['id']}/stats").json

    assert data["recommended_supermarket"]["supermarket"] == "Lidl"
    assert data["recommendation"]["confidence"] == "high"
    assert data["recommended_supermarket"]["recent_priced_count"] == 4

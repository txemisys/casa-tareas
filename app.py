from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import re
import socket
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from icalendar import Calendar
import recurring_ical_events
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("APP_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "chores.db"
ATTACHMENTS_DIR = DATA_DIR / "attachments"
ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_MAX_ATTACHMENT_BYTES = max(
    1024 * 1024,
    int(os.getenv("MAX_ATTACHMENT_BYTES", str(20 * 1024 * 1024)) or str(20 * 1024 * 1024)),
)
DEFAULT_TIMEZONE_NAME = os.getenv("APP_TIMEZONE", "Europe/Zurich").strip() or "Europe/Zurich"
DEFAULT_TELEGRAM_POLL_SECONDS = max(
    30, int(os.getenv("TELEGRAM_POLL_SECONDS", "60") or "60")
)
DEFAULT_ICAL_SYNC_MINUTES = max(
    5, int(os.getenv("ICAL_SYNC_MINUTES", "30") or "30")
)
DEFAULT_GASTOS_COMIDA_URL = os.getenv("GASTOS_COMIDA_URL", "").strip()
DEFAULT_GASTOS_SYNC_SECONDS = max(
    30, int(os.getenv("GASTOS_SYNC_SECONDS", "60") or "60")
)
MAX_ATTACHMENT_BYTES = DEFAULT_MAX_ATTACHMENT_BYTES
TZ = ZoneInfo(DEFAULT_TIMEZONE_NAME)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_POLL_SECONDS = DEFAULT_TELEGRAM_POLL_SECONDS
ICAL_SYNC_MINUTES = DEFAULT_ICAL_SYNC_MINUTES
GASTOS_SYNC_SECONDS = DEFAULT_GASTOS_SYNC_SECONDS
TELEGRAM_TASK = None
CALENDAR_TASK = None
GASTOS_SYNC_TASK = None

app = FastAPI(title="Casa Tareas", version="1.5.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def now_local():
    return datetime.now(TZ)


def today_local():
    return now_local().date()


def iso_now():
    return now_local().isoformat(timespec="seconds")


def ensure_column(conn, table, column, definition):
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS people(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL UNIQUE,
          color TEXT NOT NULL DEFAULT '#f7c8b6',
          icon TEXT NOT NULL DEFAULT '👤',
          gastos_user_name TEXT,
          active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS areas(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL UNIQUE,
          description TEXT NOT NULL DEFAULT '',
          color TEXT NOT NULL DEFAULT '#e7eefb',
          icon TEXT NOT NULL DEFAULT '🏠',
          owner_person_id INTEGER,
          pause_started_on TEXT,
          paused_until TEXT,
          pause_resume_mode TEXT,
          active INTEGER NOT NULL DEFAULT 1,
          FOREIGN KEY(owner_person_id) REFERENCES people(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS tasks(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          title TEXT NOT NULL,
          description TEXT NOT NULL DEFAULT '',
          category TEXT NOT NULL DEFAULT 'General',
          color TEXT NOT NULL DEFAULT '#dcecff',
          icon TEXT NOT NULL DEFAULT '🧹',
          recurrence_type TEXT NOT NULL DEFAULT 'none'
            CHECK(recurrence_type IN ('none','cycle','fixed')),
          frequency_days INTEGER,
          initial_due_date TEXT,
          anchor_date TEXT,
          area_id INTEGER,
          owner_person_id INTEGER,
          task_type TEXT NOT NULL DEFAULT 'execution',
          definition_of_done TEXT NOT NULL DEFAULT '',
          responsibility_notes TEXT NOT NULL DEFAULT '',
          estimated_minutes INTEGER,
          pause_started_on TEXT,
          paused_until TEXT,
          pause_resume_mode TEXT,
          active INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL,
          FOREIGN KEY(area_id) REFERENCES areas(id) ON DELETE SET NULL,
          FOREIGN KEY(owner_person_id) REFERENCES people(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS events(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          title TEXT NOT NULL,
          description TEXT NOT NULL DEFAULT '',
          area_id INTEGER,
          event_at TEXT NOT NULL,
          reminders_json TEXT NOT NULL DEFAULT '[]',
          active INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY(area_id) REFERENCES areas(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS event_alert_ack(
          event_id INTEGER NOT NULL,
          reminder_minutes INTEGER NOT NULL,
          acknowledged_at TEXT NOT NULL,
          PRIMARY KEY(event_id, reminder_minutes),
          FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS notification_deliveries(
          event_id INTEGER NOT NULL,
          reminder_minutes INTEGER NOT NULL,
          channel TEXT NOT NULL,
          delivered_at TEXT NOT NULL,
          PRIMARY KEY(event_id, reminder_minutes, channel),
          FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS telegram_chats_seen(
          chat_id INTEGER PRIMARY KEY,
          title TEXT NOT NULL DEFAULT '',
          chat_type TEXT NOT NULL DEFAULT 'unknown',
          last_seen_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS telegram_pending_actions(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          action_type TEXT NOT NULL,
          payload TEXT NOT NULL,
          chat_id INTEGER NOT NULL,
          created_at TEXT NOT NULL,
          used_at TEXT
        );
        CREATE TABLE IF NOT EXISTS completions(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          task_id INTEGER NOT NULL,
          person_id INTEGER NOT NULL,
          completed_at TEXT NOT NULL,
          FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
          FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE RESTRICT
        );
        CREATE TABLE IF NOT EXISTS schedule_overrides(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          task_id INTEGER NOT NULL,
          due_date TEXT NOT NULL,
          created_at TEXT NOT NULL,
          consumed_at TEXT,
          FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS today_queue(
          task_id INTEGER PRIMARY KEY,
          position REAL NOT NULL,
          forced INTEGER NOT NULL DEFAULT 1,
          added_at TEXT NOT NULL,
          FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS undo_actions(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          action_type TEXT NOT NULL,
          payload TEXT NOT NULL,
          label TEXT NOT NULL,
          created_at TEXT NOT NULL,
          undone_at TEXT
        );
        CREATE TABLE IF NOT EXISTS activity_log(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          kind TEXT NOT NULL,
          summary TEXT NOT NULL,
          detail TEXT NOT NULL DEFAULT '',
          entity_type TEXT,
          entity_id INTEGER,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS attachments(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          entity_type TEXT NOT NULL CHECK(entity_type IN ('task','area')),
          entity_id INTEGER NOT NULL,
          original_name TEXT NOT NULL,
          stored_name TEXT NOT NULL UNIQUE,
          content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
          size_bytes INTEGER NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS calendar_subscriptions(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL,
          url TEXT NOT NULL,
          area_id INTEGER,
          active INTEGER NOT NULL DEFAULT 1,
          last_sync_at TEXT,
          last_error TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY(area_id) REFERENCES areas(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS calendar_external_events(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          subscription_id INTEGER NOT NULL,
          uid TEXT NOT NULL,
          occurrence_key TEXT NOT NULL,
          title TEXT NOT NULL,
          description TEXT NOT NULL DEFAULT '',
          location TEXT NOT NULL DEFAULT '',
          start_at TEXT NOT NULL,
          end_at TEXT,
          all_day INTEGER NOT NULL DEFAULT 0,
          updated_at TEXT NOT NULL,
          UNIQUE(subscription_id,uid,occurrence_key),
          FOREIGN KEY(subscription_id) REFERENCES calendar_subscriptions(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS inventory_items(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL UNIQUE,
          category TEXT NOT NULL DEFAULT 'General',
          area_id INTEGER,
          unit TEXT NOT NULL DEFAULT '',
          purchase_quantity TEXT NOT NULL DEFAULT '',
          stock_status TEXT NOT NULL DEFAULT 'ok'
            CHECK(stock_status IN ('ok','low','out')),
          shopping_requested INTEGER NOT NULL DEFAULT 0,
          notes TEXT NOT NULL DEFAULT '',
          gastos_product_id INTEGER,
          last_purchased_at TEXT,
          last_purchase_ticket_id INTEGER,
          active INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY(area_id) REFERENCES areas(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS task_supplies(
          task_id INTEGER NOT NULL,
          item_id INTEGER NOT NULL,
          PRIMARY KEY(task_id,item_id),
          FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
          FOREIGN KEY(item_id) REFERENCES inventory_items(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS app_meta(
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_completions_task ON completions(task_id, completed_at DESC);
        CREATE INDEX IF NOT EXISTS idx_events_at ON events(active, event_at);
        CREATE INDEX IF NOT EXISTS idx_notification_deliveries
          ON notification_deliveries(channel, event_id, reminder_minutes);
        CREATE INDEX IF NOT EXISTS idx_telegram_pending_open
          ON telegram_pending_actions(used_at, id DESC);
        CREATE INDEX IF NOT EXISTS idx_undo_open ON undo_actions(undone_at, id DESC);
        CREATE INDEX IF NOT EXISTS idx_activity_created ON activity_log(created_at DESC,id DESC);
        CREATE INDEX IF NOT EXISTS idx_attachments_entity ON attachments(entity_type,entity_id,id);
        CREATE INDEX IF NOT EXISTS idx_calendar_events_start ON calendar_external_events(start_at,subscription_id);
        CREATE INDEX IF NOT EXISTS idx_inventory_active ON inventory_items(active,stock_status,name);
        CREATE INDEX IF NOT EXISTS idx_task_supplies_item ON task_supplies(item_id,task_id);
        """)

        # Migraciones aditivas para bases creadas por versiones anteriores.
        ensure_column(conn, "tasks", "area_id", "INTEGER REFERENCES areas(id) ON DELETE SET NULL")
        ensure_column(conn, "tasks", "owner_person_id", "INTEGER REFERENCES people(id) ON DELETE SET NULL")
        ensure_column(conn, "tasks", "task_type", "TEXT NOT NULL DEFAULT 'execution'")
        ensure_column(conn, "tasks", "definition_of_done", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "tasks", "responsibility_notes", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "tasks", "estimated_minutes", "INTEGER")
        ensure_column(conn, "tasks", "pause_started_on", "TEXT")
        ensure_column(conn, "tasks", "paused_until", "TEXT")
        ensure_column(conn, "tasks", "pause_resume_mode", "TEXT")
        ensure_column(conn, "areas", "pause_started_on", "TEXT")
        ensure_column(conn, "areas", "paused_until", "TEXT")
        ensure_column(conn, "areas", "pause_resume_mode", "TEXT")
        ensure_column(conn, "people", "gastos_user_name", "TEXT")
        ensure_column(conn, "inventory_items", "gastos_product_id", "INTEGER")
        ensure_column(conn, "inventory_items", "last_purchased_at", "TEXT")
        ensure_column(conn, "inventory_items", "last_purchase_ticket_id", "INTEGER")
        conn.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_inventory_gastos_product
               ON inventory_items(gastos_product_id)
               WHERE gastos_product_id IS NOT NULL"""
        )
        conn.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_people_gastos_user
               ON people(gastos_user_name)
               WHERE gastos_user_name IS NOT NULL AND gastos_user_name <> ''"""
        )

        sample_data_enabled = conn.execute(
            "SELECT value FROM app_meta WHERE key='sample_data_disabled'"
        ).fetchone() is None

        if sample_data_enabled and conn.execute("SELECT COUNT(*) FROM people").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO people(name,color,icon) VALUES(?,?,?)",
                [
                    ("Cosi", "#f7c8b6", "👩"),
                    ("Jose", "#b8d8ff", "👨"),
                    ("Li", "#d8c6ff", "👩‍🦰"),
                ],
            )

        if sample_data_enabled and conn.execute("SELECT COUNT(*) FROM areas").fetchone()[0] == 0:
            conn.executemany(
                """INSERT INTO areas(name,description,color,icon)
                   VALUES(?,?,?,?)""",
                [
                    ("Alimentación", "Planificación, compra, cocina y gestión de alimentos.", "#fff0c9", "🍳"),
                    ("Ropa y textil", "Lavado, sábanas, toallas y productos textiles.", "#ddf5e4", "🧺"),
                    ("Limpieza y mantenimiento", "Limpieza, consumibles y mantenimiento doméstico.", "#d9ecff", "🧹"),
                    ("Piso Fanalwegle", "Gestión y mantenimiento del piso Fanalwegle.", "#e7eefb", "🏢"),
                    ("Piso Im Gapetsch", "Gestión y mantenimiento del piso Im Gapetsch.", "#e7eefb", "🏢"),
                    ("Casa de Cosi", "Gestión, mantenimiento y asuntos relacionados con Casa de Cosi.", "#f7dde4", "🏠"),
                    ("Vehículos", "Mantenimiento, seguros, revisiones y gestiones de vehículos.", "#fff1c9", "🚗"),
                    ("Krankenkassen", "Seguros médicos, facturas, reembolsos y gestiones de Krankenkassen.", "#ddf5e4", "🩺"),
                ],
            )

        if sample_data_enabled and conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0:
            t = today_local()
            samples = [
                ("Limpiar baño","Lavabo, ducha, espejo e inodoro","Baño","#d9ecff","🛁","cycle",7,t-timedelta(days=2)),
                ("Poner lavadora","Ropa blanca","Ropa","#ddf5e4","🧺","cycle",4,t),
                ("Sacar basura","Contenedor general","Casa","#fff1c9","🗑️","cycle",3,t),
                ("Aspirar salón","Sofá, alfombras y zonas de paso","Salón","#fbe0e6","🧹","cycle",5,t-timedelta(days=1)),
                ("Cambiar sábanas","Dormitorio principal","Dormitorio","#f7dde4","🛏️","cycle",14,t+timedelta(days=1)),
                ("Limpiar frigorífico","Interior y estantes","Cocina","#fff1c9","🧊","cycle",30,t+timedelta(days=3)),
                ("Limpiar cristales","Ventanas y espejos","Casa","#ddf5e4","🪟","cycle",60,t+timedelta(days=6)),
                ("Limpiar horno","Interior y bandejas","Cocina","#dcecff","🔥","cycle",90,t+timedelta(days=12)),
            ]
            for title, desc, category, color, icon, rtype, freq, due in samples:
                conn.execute(
                    """INSERT INTO tasks(title,description,category,color,icon,recurrence_type,
                       frequency_days,initial_due_date,anchor_date,active,created_at)
                       VALUES(?,?,?,?,?,?,?,?,?,1,?)""",
                    (title,desc,category,color,icon,rtype,freq,due.isoformat(),due.isoformat(),iso_now()),
                )

        # v0.4: adapta los datos iniciales del hogar sin pisar cambios manuales.
        household_v4 = conn.execute(
            "SELECT value FROM app_meta WHERE key='household_defaults_v4'"
        ).fetchone()
        if sample_data_enabled and not household_v4:
            default_renames = {
                "Ana": "Cosi",
                "Juan": "Jose",
                "Lucía": "Li",
            }
            for old_name, new_name in default_renames.items():
                old = conn.execute(
                    "SELECT id FROM people WHERE name=?", (old_name,)
                ).fetchone()
                target = conn.execute(
                    "SELECT id FROM people WHERE name=?", (new_name,)
                ).fetchone()
                if old and not target:
                    conn.execute(
                        "UPDATE people SET name=? WHERE id=?",
                        (new_name, old["id"]),
                    )

            requested_areas = [
                ("Piso Fanalwegle", "Gestión y mantenimiento del piso Fanalwegle.", "#e7eefb", "🏢"),
                ("Piso Im Gapetsch", "Gestión y mantenimiento del piso Im Gapetsch.", "#e7eefb", "🏢"),
                ("Casa de Cosi", "Gestión, mantenimiento y asuntos relacionados con Casa de Cosi.", "#f7dde4", "🏠"),
                ("Vehículos", "Mantenimiento, seguros, revisiones y gestiones de vehículos.", "#fff1c9", "🚗"),
                ("Krankenkassen", "Seguros médicos, facturas, reembolsos y gestiones de Krankenkassen.", "#ddf5e4", "🩺"),
            ]
            for name, description, color, icon in requested_areas:
                existing = conn.execute(
                    "SELECT id FROM areas WHERE name=?", (name,)
                ).fetchone()
                if not existing:
                    conn.execute(
                        """INSERT INTO areas(name,description,color,icon)
                           VALUES(?,?,?,?)""",
                        (name, description, color, icon),
                    )

            conn.execute(
                "INSERT INTO app_meta(key,value) VALUES('household_defaults_v4',?)",
                (iso_now(),),
            )

        # v0.2: Hoy pasa a ser una cola manual. Limpiamos una sola vez
        # las filas que las versiones anteriores añadían automáticamente.
        migrated = conn.execute(
            "SELECT value FROM app_meta WHERE key='manual_today_v1'"
        ).fetchone()
        if not migrated:
            conn.execute("DELETE FROM today_queue WHERE forced=0")
            conn.execute(
                "INSERT INTO app_meta(key,value) VALUES('manual_today_v1',?)",
                (iso_now(),),
            )


def task_row(conn, task_id):
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Tarea no encontrada")
    return row


def person_row(conn, person_id):
    row = conn.execute("SELECT * FROM people WHERE id=?", (person_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Persona no encontrada")
    return row


def last_completion(conn, task_id):
    return conn.execute(
        "SELECT * FROM completions WHERE task_id=? ORDER BY completed_at DESC,id DESC LIMIT 1",
        (task_id,),
    ).fetchone()


def due_date(conn, task):
    if not task["active"]:
        return None

    override = conn.execute(
        """SELECT due_date FROM schedule_overrides
           WHERE task_id=? AND consumed_at IS NULL
           ORDER BY id DESC LIMIT 1""",
        (task["id"],),
    ).fetchone()
    if override:
        return date.fromisoformat(override["due_date"])

    last = last_completion(conn, task["id"])
    last_day = datetime.fromisoformat(last["completed_at"]).astimezone(TZ).date() if last else None
    rtype = task["recurrence_type"]

    if rtype == "none":
        if last:
            return None
        return date.fromisoformat(task["initial_due_date"] or task["created_at"][:10])

    freq = task["frequency_days"]
    if not freq or freq < 1:
        return None

    first = date.fromisoformat(task["initial_due_date"] or today_local().isoformat())
    if rtype == "cycle":
        return last_day + timedelta(days=freq) if last_day else first

    anchor = date.fromisoformat(task["anchor_date"] or first.isoformat())
    if not last_day or last_day < anchor:
        return anchor
    steps = ((last_day - anchor).days // freq) + 1
    return anchor + timedelta(days=steps * freq)


def sync_today(conn):
    # Hoy es deliberadamente manual: no añadimos tareas por fecha.
    # Solo limpiamos referencias a tareas archivadas.
    conn.execute(
        "DELETE FROM today_queue WHERE task_id IN (SELECT id FROM tasks WHERE active=0)"
    )


def queue_snapshot(row):
    return dict(row) if row else None


def restore_queue_row(conn, snapshot):
    if not snapshot:
        return
    conn.execute(
        """INSERT INTO today_queue(task_id,position,forced,added_at)
           VALUES(?,?,?,?)
           ON CONFLICT(task_id) DO UPDATE SET
             position=excluded.position,
             forced=excluded.forced,
             added_at=excluded.added_at""",
        (
            snapshot["task_id"],
            snapshot["position"],
            snapshot["forced"],
            snapshot["added_at"],
        ),
    )


def record_undo(conn, action_type, payload, label):
    cur = conn.execute(
        """INSERT INTO undo_actions(action_type,payload,label,created_at)
           VALUES(?,?,?,?)""",
        (action_type, json.dumps(payload, ensure_ascii=False), label, iso_now()),
    )
    return cur.lastrowid


def latest_undo(conn):
    cutoff = (now_local() - timedelta(hours=24)).isoformat(timespec="seconds")
    row = conn.execute(
        """SELECT id,label,created_at FROM undo_actions
           WHERE undone_at IS NULL AND created_at>=?
           ORDER BY id DESC LIMIT 1""",
        (cutoff,),
    ).fetchone()
    return dict(row) if row else None


def open_completion_undo_map(conn):
    result = {}
    rows = conn.execute(
        """SELECT * FROM undo_actions
           WHERE action_type='complete' AND undone_at IS NULL
           ORDER BY id DESC"""
    ).fetchall()
    for row in rows:
        try:
            payload = json.loads(row["payload"])
            completion_id = int(payload.get("completion_id"))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if completion_id not in result:
            result[completion_id] = {
                "undo_id": row["id"],
                "payload": payload,
            }
    return result


def restore_completion_payload(conn, payload):
    completion_id = int(payload["completion_id"])
    task_id = int(payload["task_id"])
    conn.execute(
        "DELETE FROM completions WHERE id=?",
        (completion_id,),
    )
    conn.execute(
        "UPDATE tasks SET active=? WHERE id=?",
        (payload["previous_active"], task_id),
    )
    if payload.get("active_override_id"):
        conn.execute(
            "UPDATE schedule_overrides SET consumed_at=NULL WHERE id=?",
            (payload["active_override_id"],),
        )
    restore_queue_row(conn, payload.get("queue"))


def shopping_inventory_rows(conn):
    return conn.execute(
        """SELECT * FROM inventory_items
           WHERE active=1 AND (shopping_requested=1 OR stock_status IN ('low','out'))
           ORDER BY category COLLATE NOCASE,name COLLATE NOCASE,id"""
    ).fetchall()


def sync_shopping_task(conn):
    shopping = shopping_inventory_rows(conn)
    raw_id = get_meta(conn, "shopping_task_id")
    task = None
    if raw_id:
        try:
            task = conn.execute(
                "SELECT * FROM tasks WHERE id=?",
                (int(raw_id),),
            ).fetchone()
        except (TypeError, ValueError):
            task = None
            delete_meta(conn, "shopping_task_id")

    if not shopping:
        if task:
            if task["active"]:
                conn.execute("UPDATE tasks SET active=0 WHERE id=?", (task["id"],))
                log_activity(
                    conn,
                    "shopping_task_resolved",
                    'Lista vacía: resuelta "Hacer la compra"',
                    entity_type="task",
                    entity_id=task["id"],
                )
            conn.execute("DELETE FROM today_queue WHERE task_id=?", (task["id"],))
            conn.execute("DELETE FROM task_supplies WHERE task_id=?", (task["id"],))
        return task["id"] if task else None

    names = [row["name"] for row in shopping]
    description = "Falta: " + ", ".join(names[:8])
    if len(names) > 8:
        description += f" y {len(names) - 8} más"
    definition = "La lista de compra vuelve a estar vacía."
    now = iso_now()

    if not task:
        cur = conn.execute(
            """INSERT INTO tasks(
               title,description,category,color,icon,recurrence_type,frequency_days,
               initial_due_date,anchor_date,area_id,owner_person_id,task_type,
               definition_of_done,responsibility_notes,estimated_minutes,active,created_at
               ) VALUES(?,?,?,?,?,'none',NULL,?,?,NULL,NULL,'execution',?,?,NULL,1,?)""",
            (
                "Hacer la compra",
                description,
                "Compra",
                "#dcecff",
                "🛒",
                today_local().isoformat(),
                today_local().isoformat(),
                definition,
                "Tarea automática generada desde Inventario y Comprar.",
                now,
            ),
        )
        task_id = cur.lastrowid
        set_meta(conn, "shopping_task_id", task_id)
        log_activity(
            conn,
            "shopping_task_created",
            f'Creada "Hacer la compra" · {len(shopping)} producto(s)',
            entity_type="task",
            entity_id=task_id,
        )
    else:
        task_id = task["id"]
        was_active = bool(task["active"])
        conn.execute(
            """UPDATE tasks
               SET title='Hacer la compra',description=?,category='Compra',
                   color='#dcecff',icon='🛒',recurrence_type='none',
                   frequency_days=NULL,initial_due_date=?,anchor_date=?,
                   task_type='execution',definition_of_done=?,
                   responsibility_notes=?,estimated_minutes=NULL,active=1
               WHERE id=?""",
            (
                description,
                today_local().isoformat(),
                today_local().isoformat(),
                definition,
                "Tarea automática generada desde Inventario y Comprar.",
                task_id,
            ),
        )
        if not was_active:
            log_activity(
                conn,
                "shopping_task_reactivated",
                f'Reactivada "Hacer la compra" · {len(shopping)} producto(s)',
                entity_type="task",
                entity_id=task_id,
            )

    conn.execute("DELETE FROM task_supplies WHERE task_id=?", (task_id,))
    conn.executemany(
        "INSERT INTO task_supplies(task_id,item_id) VALUES(?,?)",
        [(task_id, row["id"]) for row in shopping],
    )
    return task_id


def task_need(conn, task):
    shopping_task_id = get_meta(conn, "shopping_task_id")
    if task["active"] and shopping_task_id and str(task["id"]) == str(shopping_task_id):
        return {"score": 100, "label": "Pendiente", "suggested": True}
    if not task["active"] or task["recurrence_type"] == "none":
        return None
    if effective_task_pause(conn, task):
        return None

    freq = task["frequency_days"]
    if not freq or freq < 1:
        return None

    due = due_date(conn, task)
    if not due:
        return None

    override = conn.execute(
        """SELECT due_date FROM schedule_overrides
           WHERE task_id=? AND consumed_at IS NULL
           ORDER BY id DESC LIMIT 1""",
        (task["id"],),
    ).fetchone()

    last = last_completion(conn, task["id"])
    last_day = (
        datetime.fromisoformat(last["completed_at"]).astimezone(TZ).date()
        if last
        else None
    )

    if override or task["recurrence_type"] == "fixed" or not last_day:
        cycle_start = due - timedelta(days=freq)
    else:
        cycle_start = last_day

    elapsed = (today_local() - cycle_start).days
    score = round((elapsed / freq) * 100)
    score = max(0, min(100, score))

    if score < 40:
        label = "Puede esperar"
    elif score < 70:
        label = "Pronto"
    elif score < 100:
        label = "Conviene hacer"
    else:
        label = "Pendiente"

    if conn.execute(
        """SELECT 1
           FROM task_supplies s
           JOIN inventory_items i ON i.id=s.item_id
           WHERE s.task_id=? AND i.active=1 AND i.stock_status='out'
           LIMIT 1""",
        (task["id"],),
    ).fetchone():
        label = "Bloqueada por material"

    return {
        "score": score,
        "label": label,
        "suggested": score >= 70,
    }


def log_activity(
    conn,
    kind,
    summary,
    detail="",
    entity_type=None,
    entity_id=None,
):
    conn.execute(
        """INSERT INTO activity_log(
           kind,summary,detail,entity_type,entity_id,created_at
           ) VALUES(?,?,?,?,?,?)""",
        (
            kind,
            summary[:240],
            (detail or "")[:1000],
            entity_type,
            entity_id,
            iso_now(),
        ),
    )


def attachment_json(row):
    d = dict(row)
    d.pop("stored_name", None)
    return d


def attachments_for(conn, entity_type, entity_id):
    return [
        attachment_json(r)
        for r in conn.execute(
            """SELECT * FROM attachments
               WHERE entity_type=? AND entity_id=?
               ORDER BY created_at DESC,id DESC""",
            (entity_type, entity_id),
        ).fetchall()
    ]


def delete_attachment_file(row):
    try:
        path = ATTACHMENTS_DIR / row["stored_name"]
        if path.exists():
            path.unlink()
    except OSError:
        pass


def delete_attachments_for(conn, entity_type, entity_id):
    rows = conn.execute(
        "SELECT * FROM attachments WHERE entity_type=? AND entity_id=?",
        (entity_type, entity_id),
    ).fetchall()
    for row in rows:
        delete_attachment_file(row)
    conn.execute(
        "DELETE FROM attachments WHERE entity_type=? AND entity_id=?",
        (entity_type, entity_id),
    )


def inventory_item_json(conn, item, include_required_by=False):
    d = dict(item)
    d["active"] = bool(d["active"])
    d["shopping_requested"] = bool(d["shopping_requested"])
    d["needs_purchase"] = bool(
        d["shopping_requested"] or d["stock_status"] in {"low", "out"}
    )
    d["available"] = d["stock_status"] != "out"
    d["gastos_linked"] = d.get("gastos_product_id") is not None
    area = None
    if d.get("area_id"):
        row = conn.execute(
            "SELECT id,name,color,icon,active FROM areas WHERE id=?",
            (d["area_id"],),
        ).fetchone()
        if row:
            area = dict(row)
            area["active"] = bool(area["active"])
    d["area"] = area
    if include_required_by:
        shopping_task_id = get_meta(conn, "shopping_task_id")
        d["required_by"] = [
            {"id": r["id"], "title": r["title"], "active": bool(r["active"])}
            for r in conn.execute(
                """SELECT t.id,t.title,t.active
                   FROM task_supplies s
                   JOIN tasks t ON t.id=s.task_id
                   WHERE s.item_id=? AND t.active=1
                     AND (? IS NULL OR t.id<>?)
                   ORDER BY t.title COLLATE NOCASE,t.id""",
                (d["id"], shopping_task_id, shopping_task_id),
            ).fetchall()
        ]
    return d


def task_supplies(conn, task_id):
    return [
        inventory_item_json(conn, r)
        for r in conn.execute(
            """SELECT i.*
               FROM task_supplies s
               JOIN inventory_items i ON i.id=s.item_id
               WHERE s.task_id=? AND i.active=1
               ORDER BY i.category COLLATE NOCASE,i.name COLLATE NOCASE,i.id""",
            (task_id,),
        ).fetchall()
    ]


def validate_supply_ids(conn, supply_ids):
    ids = []
    for raw in supply_ids or []:
        item_id = int(raw)
        if item_id in ids:
            continue
        row = conn.execute(
            "SELECT id FROM inventory_items WHERE id=? AND active=1",
            (item_id,),
        ).fetchone()
        if not row:
            raise HTTPException(400, f"Producto de inventario no válido: {item_id}")
        ids.append(item_id)
    return ids


def set_task_supplies(conn, task_id, supply_ids):
    ids = validate_supply_ids(conn, supply_ids)
    conn.execute("DELETE FROM task_supplies WHERE task_id=?", (task_id,))
    conn.executemany(
        "INSERT INTO task_supplies(task_id,item_id) VALUES(?,?)",
        [(task_id, item_id) for item_id in ids],
    )


def normalize_calendar_url(value):
    url = (value or "").strip()
    if url.startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise HTTPException(400, "El calendario debe usar una URL HTTPS")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise HTTPException(400, "No se puede resolver el servidor del calendario") from exc
    for info in infos:
        address = info[4][0]
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise HTTPException(
                400,
                "Por seguridad, el calendario debe estar alojado en una dirección pública",
            )
    return url


def calendar_subscription_json(conn, row):
    d = dict(row)
    url = d.pop("url", "")
    parsed = urllib.parse.urlparse(url)
    d["url_display"] = parsed.hostname or "calendario externo"
    d["active"] = bool(d["active"])
    area = None
    if d.get("area_id"):
        a = conn.execute(
            "SELECT id,name,color,icon,active FROM areas WHERE id=?",
            (d["area_id"],),
        ).fetchone()
        if a:
            area = dict(a)
            area["active"] = bool(area["active"])
    d["area"] = area
    return d


def ical_datetime(value):
    all_day = isinstance(value, date) and not isinstance(value, datetime)
    if all_day:
        dt = datetime.combine(value, datetime.min.time(), tzinfo=TZ)
    elif isinstance(value, datetime):
        dt = value.replace(tzinfo=TZ) if value.tzinfo is None else value.astimezone(TZ)
    else:
        raise ValueError("Fecha iCal no válida")
    return dt, all_day


def external_event_json(conn, row):
    d = dict(row)
    d["external"] = True
    d["source"] = "ical"
    d["event_at"] = d["start_at"]
    d["all_day"] = bool(d["all_day"])
    d["reminders"] = []
    sub = conn.execute(
        "SELECT * FROM calendar_subscriptions WHERE id=?",
        (d["subscription_id"],),
    ).fetchone()
    d["calendar_name"] = sub["name"] if sub else "Calendario externo"
    area = None
    area_id = sub["area_id"] if sub else None
    if area_id:
        a = conn.execute(
            "SELECT id,name,color,icon,active FROM areas WHERE id=?",
            (area_id,),
        ).fetchone()
        if a:
            area = dict(a)
            area["active"] = bool(area["active"])
    d["area"] = area
    return d


def fetch_calendar_bytes(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Casa-Tareas/1.0 iCal"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            content_type = (response.headers.get("Content-Type") or "").lower()
            data = response.read(5 * 1024 * 1024 + 1)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"No se pudo descargar el calendario: {exc}") from exc
    if len(data) > 5 * 1024 * 1024:
        raise RuntimeError("El calendario supera el límite de 5 MB")
    if not data:
        raise RuntimeError("El calendario está vacío")
    if "text/calendar" not in content_type and b"BEGIN:VCALENDAR" not in data[:4096]:
        raise RuntimeError("La URL no parece devolver un calendario iCal")
    return data


def parse_calendar_occurrences(data):
    try:
        calendar = Calendar.from_ical(data)
    except Exception as exc:
        raise RuntimeError("No se pudo interpretar el calendario iCal") from exc

    start_window = datetime.combine(
        today_local() - timedelta(days=14),
        datetime.min.time(),
        tzinfo=TZ,
    )
    end_window = start_window + timedelta(days=380)
    try:
        components = recurring_ical_events.of(calendar).between(
            start_window,
            end_window,
        )
    except Exception as exc:
        raise RuntimeError("No se pudieron expandir los eventos recurrentes") from exc

    result = []
    for component in components:
        try:
            raw_start = component.decoded("DTSTART")
            start_at, all_day = ical_datetime(raw_start)
        except Exception:
            continue
        raw_end = component.get("DTEND")
        end_at = None
        if raw_end is not None:
            try:
                end_at, _ = ical_datetime(component.decoded("DTEND"))
            except Exception:
                end_at = None
        uid = str(component.get("UID") or f"sin-uid-{start_at.isoformat()}")
        occurrence_key = start_at.isoformat(timespec="minutes")
        result.append(
            {
                "uid": uid[:500],
                "occurrence_key": occurrence_key,
                "title": str(component.get("SUMMARY") or "Evento")[:300],
                "description": str(component.get("DESCRIPTION") or "")[:4000],
                "location": str(component.get("LOCATION") or "")[:500],
                "start_at": start_at.isoformat(timespec="minutes"),
                "end_at": end_at.isoformat(timespec="minutes") if end_at else None,
                "all_day": 1 if all_day else 0,
            }
        )
    result.sort(key=lambda x: (x["start_at"], x["title"].casefold()))
    return result


def sync_calendar_subscription(subscription_id):
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM calendar_subscriptions WHERE id=? AND active=1",
            (subscription_id,),
        ).fetchone()
        if not row:
            return 0
        url = row["url"]

    try:
        url = normalize_calendar_url(url)
        occurrences = parse_calendar_occurrences(fetch_calendar_bytes(url))
    except (HTTPException, RuntimeError) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        with db() as conn:
            conn.execute(
                "UPDATE calendar_subscriptions SET last_error=?,updated_at=? WHERE id=?",
                (str(detail)[:1000], iso_now(), subscription_id),
            )
        raise RuntimeError(str(detail)) from exc

    with db() as conn:
        conn.execute(
            "DELETE FROM calendar_external_events WHERE subscription_id=?",
            (subscription_id,),
        )
        conn.executemany(
            """INSERT INTO calendar_external_events(
               subscription_id,uid,occurrence_key,title,description,location,
               start_at,end_at,all_day,updated_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            [
                (
                    subscription_id,
                    event["uid"],
                    event["occurrence_key"],
                    event["title"],
                    event["description"],
                    event["location"],
                    event["start_at"],
                    event["end_at"],
                    event["all_day"],
                    iso_now(),
                )
                for event in occurrences
            ],
        )
        conn.execute(
            """UPDATE calendar_subscriptions
               SET last_sync_at=?,last_error=NULL,updated_at=? WHERE id=?""",
            (iso_now(), iso_now(), subscription_id),
        )
    return len(occurrences)


def sync_all_calendars():
    with db() as conn:
        ids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM calendar_subscriptions WHERE active=1 ORDER BY id"
            ).fetchall()
        ]
    for subscription_id in ids:
        try:
            sync_calendar_subscription(subscription_id)
        except Exception as exc:
            print(f"iCal sync error for {subscription_id}: {exc}", flush=True)


async def calendar_sync_loop():
    last_sync = 0.0
    while True:
        try:
            now_tick = time.monotonic()
            if last_sync == 0.0 or now_tick - last_sync >= ICAL_SYNC_MINUTES * 60:
                await asyncio.to_thread(sync_all_calendars)
                last_sync = time.monotonic()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"iCal worker error: {exc}", flush=True)
        await asyncio.sleep(30)


def area_json(conn, area):
    d = dict(area)
    d["active"] = bool(d["active"])
    owner = None
    if d.get("owner_person_id"):
        row = conn.execute(
            "SELECT id,name,color,icon,active FROM people WHERE id=?",
            (d["owner_person_id"],),
        ).fetchone()
        owner = dict(row) if row else None
    d["owner"] = owner
    d["task_count"] = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE area_id=? AND active=1",
        (d["id"],),
    ).fetchone()[0]
    d["total_task_count"] = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE area_id=?",
        (d["id"],),
    ).fetchone()[0]
    d["event_count"] = conn.execute(
        "SELECT COUNT(*) FROM events WHERE area_id=? AND active=1",
        (d["id"],),
    ).fetchone()[0]
    d["pause"] = effective_area_pause(conn, area)
    d["paused"] = bool(d["pause"])
    d["attachments"] = attachments_for(conn, "area", d["id"])
    d["attachment_count"] = len(d["attachments"])
    return d


def normalize_event_at(value):
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise HTTPException(400, "Fecha y hora del evento no válidas")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ)
    else:
        parsed = parsed.astimezone(TZ)
    return parsed


def normalize_reminders(values):
    clean = []
    for value in values or []:
        try:
            minutes = int(value)
        except (TypeError, ValueError):
            raise HTTPException(400, "Recordatorio no válido")
        if minutes < 0 or minutes > 525600:
            raise HTTPException(400, "El recordatorio debe estar entre 0 minutos y 1 año")
        if minutes not in clean:
            clean.append(minutes)
    return sorted(clean, reverse=True)


def event_json(conn, event):
    d = dict(event)
    d["active"] = bool(d["active"])
    d["external"] = False
    d["source"] = "local"
    d["all_day"] = False
    try:
        d["reminders"] = normalize_reminders(json.loads(d.pop("reminders_json") or "[]"))
    except (json.JSONDecodeError, TypeError):
        d["reminders"] = []
    area = None
    if d.get("area_id"):
        row = conn.execute("SELECT * FROM areas WHERE id=?", (d["area_id"],)).fetchone()
        if row:
            area = dict(row)
            area["active"] = bool(area["active"])
    d["area"] = area
    return d


def due_event_alerts(conn, events):
    now = now_local()
    cutoff = now - timedelta(hours=24)
    alerts = []
    for event in events:
        if not event["active"]:
            continue
        event_at = normalize_event_at(event["event_at"])
        if event_at < cutoff:
            continue
        for minutes in event.get("reminders", []):
            trigger = event_at - timedelta(minutes=minutes)
            if now < trigger:
                continue
            acknowledged = conn.execute(
                """SELECT 1 FROM event_alert_ack
                   WHERE event_id=? AND reminder_minutes=?""",
                (event["id"], minutes),
            ).fetchone()
            if acknowledged:
                continue
            alerts.append(
                {
                    "event_id": event["id"],
                    "title": event["title"],
                    "event_at": event["event_at"],
                    "area": event.get("area"),
                    "reminder_minutes": minutes,
                    "trigger_at": trigger.isoformat(timespec="minutes"),
                }
            )
    alerts.sort(key=lambda x: (x["event_at"], x["reminder_minutes"]))
    return alerts


def get_meta(conn, key, default=None):
    row = conn.execute("SELECT value FROM app_meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn, key, value):
    conn.execute(
        """INSERT INTO app_meta(key,value) VALUES(?,?)
           ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
        (key, str(value)),
    )


def delete_meta(conn, key):
    conn.execute("DELETE FROM app_meta WHERE key=?", (key,))


def load_runtime_settings(conn):
    global TZ, TELEGRAM_POLL_SECONDS, ICAL_SYNC_MINUTES, MAX_ATTACHMENT_BYTES

    timezone_name = get_meta(conn, "setting_timezone", DEFAULT_TIMEZONE_NAME)
    try:
        TZ = ZoneInfo(timezone_name)
    except Exception:
        timezone_name = DEFAULT_TIMEZONE_NAME
        TZ = ZoneInfo(DEFAULT_TIMEZONE_NAME)
        delete_meta(conn, "setting_timezone")

    try:
        TELEGRAM_POLL_SECONDS = max(
            30,
            min(
                3600,
                int(
                    get_meta(
                        conn,
                        "setting_telegram_poll_seconds",
                        DEFAULT_TELEGRAM_POLL_SECONDS,
                    )
                ),
            ),
        )
    except (TypeError, ValueError):
        TELEGRAM_POLL_SECONDS = DEFAULT_TELEGRAM_POLL_SECONDS
        delete_meta(conn, "setting_telegram_poll_seconds")

    try:
        ICAL_SYNC_MINUTES = max(
            5,
            min(
                1440,
                int(
                    get_meta(
                        conn,
                        "setting_ical_sync_minutes",
                        DEFAULT_ICAL_SYNC_MINUTES,
                    )
                ),
            ),
        )
    except (TypeError, ValueError):
        ICAL_SYNC_MINUTES = DEFAULT_ICAL_SYNC_MINUTES
        delete_meta(conn, "setting_ical_sync_minutes")

    try:
        MAX_ATTACHMENT_BYTES = max(
            1024 * 1024,
            min(
                500 * 1024 * 1024,
                int(
                    get_meta(
                        conn,
                        "setting_max_attachment_bytes",
                        DEFAULT_MAX_ATTACHMENT_BYTES,
                    )
                ),
            ),
        )
    except (TypeError, ValueError):
        MAX_ATTACHMENT_BYTES = DEFAULT_MAX_ATTACHMENT_BYTES
        delete_meta(conn, "setting_max_attachment_bytes")


def runtime_settings_json():
    timezone_name = getattr(TZ, "key", str(TZ))
    return {
        "timezone": timezone_name,
        "telegram_poll_seconds": TELEGRAM_POLL_SECONDS,
        "ical_sync_minutes": ICAL_SYNC_MINUTES,
        "max_attachment_bytes": MAX_ATTACHMENT_BYTES,
        "max_attachment_mb": round(MAX_ATTACHMENT_BYTES / (1024 * 1024)),
    }


def normalize_gastos_comida_url(value):
    url = (value or "").strip().rstrip("/")
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(400, "La URL de Gastos de comida debe empezar por http:// o https://")
    if parsed.username or parsed.password:
        raise HTTPException(400, "La URL de Gastos de comida no debe incluir credenciales")
    if parsed.query or parsed.fragment:
        raise HTTPException(400, "Usa solo la URL base de Gastos de comida, sin parámetros ni fragmentos")
    path = (parsed.path or "").rstrip("/")
    if path:
        raise HTTPException(400, "Usa solo la URL base de Gastos de comida, sin una ruta adicional")
    return url


def gastos_comida_url(conn):
    stored = (get_meta(conn, "gastos_comida_url", "") or "").strip()
    return stored or DEFAULT_GASTOS_COMIDA_URL


def gastos_comida_status(conn):
    url = gastos_comida_url(conn)
    return {
        "configured": bool(url),
        "url": url,
        "source": "application" if (get_meta(conn, "gastos_comida_url", "") or "").strip() else (
            "environment" if DEFAULT_GASTOS_COMIDA_URL else "none"
        ),
        "last_ok_at": get_meta(conn, "gastos_comida_last_ok_at"),
        "last_error": get_meta(conn, "gastos_comida_last_error", ""),
        "sync_last_at": get_meta(conn, "gastos_comida_sync_last_at"),
        "sync_last_error": get_meta(conn, "gastos_comida_sync_last_error", ""),
        "sync_worker_running": bool(
            GASTOS_SYNC_TASK and not GASTOS_SYNC_TASK.done()
        ),
    }


def gastos_comida_api_request(conn, path, method="GET", payload=None):
    base = gastos_comida_url(conn)
    if not base:
        raise RuntimeError("Gastos de comida todavía no está configurado")
    body = None
    headers = {"Accept": "application/json", "User-Agent": "Casa-Tareas/1.3"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        base + path,
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            payload_error = json.loads(exc.read().decode("utf-8"))
            detail = payload_error.get("detail", "") if isinstance(payload_error, dict) else ""
        except (json.JSONDecodeError, UnicodeDecodeError):
            detail = ""
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(f"Gastos de comida devolvió HTTP {exc.code}{suffix}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"No se pudo contactar con Gastos de comida: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Gastos de comida devolvió una respuesta no válida") from exc
    if not isinstance(data, (dict, list)):
        raise RuntimeError("Gastos de comida devolvió un formato inesperado")
    return data


def telegram_bot_token(conn=None):
    environment_token = (TELEGRAM_BOT_TOKEN or "").strip()
    if environment_token:
        return environment_token
    if conn is not None:
        return (get_meta(conn, "telegram_bot_token", "") or "").strip()
    with db() as local_conn:
        return (get_meta(local_conn, "telegram_bot_token", "") or "").strip()


def telegram_token_source(conn):
    if (TELEGRAM_BOT_TOKEN or "").strip():
        return "environment"
    if (get_meta(conn, "telegram_bot_token", "") or "").strip():
        return "application"
    return "none"


def parse_pause_date(value, field_name="Fecha de regreso"):
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        raise HTTPException(400, f"{field_name} no válida")
    return parsed


def validate_pause_payload(return_date, resume_mode):
    target = parse_pause_date(return_date)
    if target <= today_local():
        raise HTTPException(400, "La fecha de regreso debe ser posterior a hoy")
    if resume_mode not in {"continue_cycle", "keep_calendar"}:
        raise HTTPException(400, "Modo de reanudación no válido")
    return target


def get_vacation(conn):
    raw = get_meta(conn, "vacation_state")
    if not raw:
        return {
            "active": False,
            "started_on": None,
            "return_date": None,
            "resume_mode": "continue_cycle",
            "excluded_area_ids": [],
        }
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        delete_meta(conn, "vacation_state")
        return {
            "active": False,
            "started_on": None,
            "return_date": None,
            "resume_mode": "continue_cycle",
            "excluded_area_ids": [],
        }

    try:
        return_date = date.fromisoformat(data["return_date"])
        active = today_local() < return_date
    except (KeyError, TypeError, ValueError):
        active = False
    data["active"] = active
    data.setdefault("excluded_area_ids", [])
    data.setdefault("resume_mode", "continue_cycle")
    return data


def row_pause_active(row):
    until = row["paused_until"] if "paused_until" in row.keys() else None
    if not until:
        return False
    try:
        return today_local() < date.fromisoformat(until)
    except ValueError:
        return False


def effective_task_pause(conn, task):
    if row_pause_active(task):
        return {
            "source": "task",
            "return_date": task["paused_until"],
            "resume_mode": task["pause_resume_mode"] or "continue_cycle",
        }

    area = None
    if task["area_id"]:
        area = conn.execute("SELECT * FROM areas WHERE id=?", (task["area_id"],)).fetchone()
        if area and row_pause_active(area):
            return {
                "source": "area",
                "area_id": area["id"],
                "area_name": area["name"],
                "return_date": area["paused_until"],
                "resume_mode": area["pause_resume_mode"] or "continue_cycle",
            }

    vacation = get_vacation(conn)
    excluded = {int(x) for x in vacation.get("excluded_area_ids", [])}
    if vacation["active"] and task["area_id"] not in excluded:
        return {
            "source": "vacation",
            "return_date": vacation["return_date"],
            "resume_mode": vacation["resume_mode"],
        }
    return None


def effective_area_pause(conn, area):
    if row_pause_active(area):
        return {
            "source": "area",
            "return_date": area["paused_until"],
            "resume_mode": area["pause_resume_mode"] or "continue_cycle",
        }
    vacation = get_vacation(conn)
    excluded = {int(x) for x in vacation.get("excluded_area_ids", [])}
    if vacation["active"] and area["id"] not in excluded:
        return {
            "source": "vacation",
            "return_date": vacation["return_date"],
            "resume_mode": vacation["resume_mode"],
        }
    return None


def pause_for_area_id(conn, area_id):
    if area_id is not None:
        area = conn.execute("SELECT * FROM areas WHERE id=?", (area_id,)).fetchone()
        if area and row_pause_active(area):
            return {
                "source": "area",
                "area_id": area["id"],
                "area_name": area["name"],
                "return_date": area["paused_until"],
                "resume_mode": area["pause_resume_mode"] or "continue_cycle",
            }
    vacation = get_vacation(conn)
    excluded = {int(x) for x in vacation.get("excluded_area_ids", [])}
    if vacation["active"] and area_id not in excluded:
        return {
            "source": "vacation",
            "return_date": vacation["return_date"],
            "resume_mode": vacation["resume_mode"],
        }
    return None


def pause_shift_days(task, started_on, ended_on):
    start = date.fromisoformat(started_on)
    end = date.fromisoformat(ended_on)
    created = date.fromisoformat(task["created_at"][:10])
    effective_start = max(start, created)
    return max(0, (end - effective_start).days)


def shift_task_schedule_after_pause(conn, task, started_on, ended_on):
    if not task["active"]:
        return
    days = pause_shift_days(task, started_on, ended_on)
    if days <= 0:
        return

    current_due = due_date(conn, task)
    active_override = conn.execute(
        """SELECT * FROM schedule_overrides
           WHERE task_id=? AND consumed_at IS NULL
           ORDER BY id DESC LIMIT 1""",
        (task["id"],),
    ).fetchone()

    if task["recurrence_type"] == "fixed":
        updates = []
        params = []
        for field in ("initial_due_date", "anchor_date"):
            value = task[field]
            if value:
                updates.append(f"{field}=?")
                params.append((date.fromisoformat(value) + timedelta(days=days)).isoformat())
        if updates:
            params.append(task["id"])
            conn.execute(
                f"UPDATE tasks SET {','.join(updates)} WHERE id=?",
                tuple(params),
            )
        if active_override and current_due:
            conn.execute(
                "UPDATE schedule_overrides SET due_date=? WHERE id=?",
                ((current_due + timedelta(days=days)).isoformat(), active_override["id"]),
            )
        return

    if current_due:
        shifted = (current_due + timedelta(days=days)).isoformat()
        if active_override:
            conn.execute(
                "UPDATE schedule_overrides SET due_date=? WHERE id=?",
                (shifted, active_override["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO schedule_overrides(task_id,due_date,created_at) VALUES(?,?,?)",
                (task["id"], shifted, iso_now()),
            )


def finish_task_pause(conn, task_id, ended_on=None):
    task = task_row(conn, task_id)
    if not task["paused_until"] or not task["pause_started_on"]:
        return False
    end = ended_on or today_local().isoformat()
    if (task["pause_resume_mode"] or "continue_cycle") == "continue_cycle":
        shift_task_schedule_after_pause(conn, task, task["pause_started_on"], end)
    conn.execute(
        """UPDATE tasks SET pause_started_on=NULL,paused_until=NULL,
           pause_resume_mode=NULL WHERE id=?""",
        (task_id,),
    )
    return True


def finish_area_pause(conn, area_id, ended_on=None):
    area = conn.execute("SELECT * FROM areas WHERE id=?", (area_id,)).fetchone()
    if not area or not area["paused_until"] or not area["pause_started_on"]:
        return False
    end = ended_on or today_local().isoformat()
    if (area["pause_resume_mode"] or "continue_cycle") == "continue_cycle":
        tasks = conn.execute(
            "SELECT * FROM tasks WHERE area_id=? AND active=1",
            (area_id,),
        ).fetchall()
        for task in tasks:
            shift_task_schedule_after_pause(conn, task, area["pause_started_on"], end)
    conn.execute(
        """UPDATE areas SET pause_started_on=NULL,paused_until=NULL,
           pause_resume_mode=NULL WHERE id=?""",
        (area_id,),
    )
    return True


def finish_vacation(conn, ended_on=None):
    vacation = get_vacation(conn)
    raw = get_meta(conn, "vacation_state")
    if not raw:
        return False

    end = ended_on or today_local().isoformat()
    if vacation.get("resume_mode") == "continue_cycle":
        excluded = {int(x) for x in vacation.get("excluded_area_ids", [])}
        tasks = conn.execute("SELECT * FROM tasks WHERE active=1").fetchall()
        for task in tasks:
            if task["area_id"] in excluded:
                continue
            shift_task_schedule_after_pause(
                conn,
                task,
                vacation["started_on"],
                end,
            )
    delete_meta(conn, "vacation_state")
    return True


def sync_pause_states(conn):
    today = today_local()

    expired_tasks = conn.execute(
        """SELECT id,paused_until FROM tasks
           WHERE paused_until IS NOT NULL"""
    ).fetchall()
    for row in expired_tasks:
        try:
            if today >= date.fromisoformat(row["paused_until"]):
                finish_task_pause(conn, row["id"], row["paused_until"])
        except ValueError:
            finish_task_pause(conn, row["id"], today.isoformat())

    expired_areas = conn.execute(
        """SELECT id,paused_until FROM areas
           WHERE paused_until IS NOT NULL"""
    ).fetchall()
    for row in expired_areas:
        try:
            if today >= date.fromisoformat(row["paused_until"]):
                finish_area_pause(conn, row["id"], row["paused_until"])
        except ValueError:
            finish_area_pause(conn, row["id"], today.isoformat())

    vacation = get_vacation(conn)
    if get_meta(conn, "vacation_state") and not vacation["active"]:
        finish_vacation(conn, vacation.get("return_date") or today.isoformat())


def assert_task_not_paused(conn, task):
    pause = effective_task_pause(conn, task)
    if pause:
        raise HTTPException(
            409,
            f'La tarea está pausada hasta {pause["return_date"]}',
        )


def assert_no_pause_overlap_for_task(conn, task):
    if effective_task_pause(conn, task):
        raise HTTPException(409, "La tarea ya está afectada por otra pausa")


def assert_area_can_pause(conn, area):
    if effective_area_pause(conn, area):
        raise HTTPException(409, "El área ya está afectada por otra pausa")
    task_pause = conn.execute(
        """SELECT id FROM tasks
           WHERE area_id=? AND active=1 AND paused_until IS NOT NULL
             AND paused_until>? LIMIT 1""",
        (area["id"], today_local().isoformat()),
    ).fetchone()
    if task_pause:
        raise HTTPException(
            409,
            "Hay tareas del área con una pausa individual activa; reanúdalas primero",
        )


def assert_vacation_can_start(conn, excluded_area_ids):
    vacation = get_vacation(conn)
    if vacation["active"]:
        raise HTTPException(409, "El modo vacaciones ya está activo")

    excluded = {int(x) for x in excluded_area_ids}
    active_area_pauses = conn.execute(
        """SELECT id FROM areas
           WHERE active=1 AND paused_until IS NOT NULL AND paused_until>?""",
        (today_local().isoformat(),),
    ).fetchall()
    for area in active_area_pauses:
        if area["id"] not in excluded:
            raise HTTPException(
                409,
                "Hay áreas con una pausa activa; reanúdalas o exclúyelas de vacaciones",
            )

    active_task_pauses = conn.execute(
        """SELECT area_id FROM tasks
           WHERE active=1 AND paused_until IS NOT NULL AND paused_until>?""",
        (today_local().isoformat(),),
    ).fetchall()
    for task in active_task_pauses:
        if task["area_id"] not in excluded:
            raise HTTPException(
                409,
                "Hay tareas con una pausa individual activa; reanúdalas o excluye su área",
            )


def telegram_status(conn):
    chat_id = get_meta(conn, "telegram_chat_id")
    token = telegram_bot_token(conn)
    source = telegram_token_source(conn)
    return {
        "token_configured": bool(token),
        "token_source": source,
        "token_editable": source != "environment",
        "chat_id": int(chat_id) if chat_id else None,
        "chat_title": get_meta(conn, "telegram_chat_title", ""),
        "bot_username": get_meta(conn, "telegram_bot_username", ""),
        "commands_enabled": bool(chat_id and token),
        "poll_seconds": TELEGRAM_POLL_SECONDS,
        "last_contact_at": get_meta(conn, "telegram_last_contact_at"),
        "worker_running": bool(TELEGRAM_TASK and not TELEGRAM_TASK.done()),
    }


def settings_json(conn):
    telegram = telegram_status(conn)
    calendar_count = conn.execute(
        "SELECT COUNT(*) FROM calendar_subscriptions WHERE active=1"
    ).fetchone()[0]
    attachment_count = conn.execute(
        "SELECT COUNT(*) FROM attachments"
    ).fetchone()[0]
    runtime = runtime_settings_json()
    runtime["language"] = get_meta(conn, "setting_language", "es")
    return {
        "version": "1.5.0",
        "runtime": runtime,
        "telegram": telegram,
        "calendars": {
            "subscription_count": calendar_count,
            "sync_minutes": ICAL_SYNC_MINUTES,
        },
        "attachments": {
            "count": attachment_count,
            "max_bytes": MAX_ATTACHMENT_BYTES,
            "max_mb": round(MAX_ATTACHMENT_BYTES / (1024 * 1024)),
        },
        "integrations": {
            "gastos_comida": gastos_comida_status(conn),
        },
        "data_path": "data/",
    }


def telegram_api_request(method, payload=None, token=None):
    active_token = (token or telegram_bot_token()).strip()
    if not active_token:
        raise RuntimeError("Telegram todavía no está configurado")
    payload = payload or {}
    url = f"https://api.telegram.org/bot{active_token}/{method}"
    body = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST")
    api_wait = int(payload.get("timeout", 0) or 0)
    try:
        with urllib.request.urlopen(request, timeout=max(12, api_wait + 5)) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("description")
        except Exception:
            detail = None
        raise RuntimeError(detail or f"Telegram devolvió HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"No se pudo contactar con Telegram: {exc}") from exc
    if not data.get("ok"):
        raise RuntimeError(data.get("description") or "Telegram rechazó la petición")
    return data.get("result")


def telegram_chat_label(chat):
    return (
        chat.get("title")
        or " ".join(x for x in [chat.get("first_name"), chat.get("last_name")] if x)
        or chat.get("username")
        or str(chat.get("id", "Telegram"))
    )


def telegram_update_chat(update):
    callback = update.get("callback_query")
    if callback and callback.get("message"):
        return callback["message"].get("chat")
    source = (
        update.get("message")
        or update.get("channel_post")
        or update.get("my_chat_member")
    )
    return source.get("chat") if source else None


def remember_telegram_chat(conn, chat):
    if not chat or "id" not in chat:
        return
    conn.execute(
        """INSERT INTO telegram_chats_seen(chat_id,title,chat_type,last_seen_at)
           VALUES(?,?,?,?)
           ON CONFLICT(chat_id) DO UPDATE SET
             title=excluded.title,
             chat_type=excluded.chat_type,
             last_seen_at=excluded.last_seen_at""",
        (
            int(chat["id"]),
            telegram_chat_label(chat),
            chat.get("type", "unknown"),
            iso_now(),
        ),
    )


def telegram_detect_chats():
    with db() as conn:
        rows = conn.execute(
            """SELECT chat_id,title,chat_type
               FROM telegram_chats_seen
               ORDER BY last_seen_at DESC,title COLLATE NOCASE"""
        ).fetchall()
    return [
        {"chat_id": r["chat_id"], "title": r["title"], "type": r["chat_type"]}
        for r in rows
    ]


def telegram_send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": str(chat_id), "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    return telegram_api_request("sendMessage", payload)


def telegram_reminder_label(minutes):
    if minutes == 0:
        return "ahora"
    if minutes < 60:
        return f"{minutes} min antes"
    if minutes % 1440 == 0:
        days = minutes // 1440
        return f"{days} día{'s' if days != 1 else ''} antes"
    if minutes % 60 == 0:
        hours = minutes // 60
        return f"{hours} hora{'s' if hours != 1 else ''} antes"
    return f"{minutes} min antes"


def telegram_event_message(event, reminder_minutes):
    event_at = normalize_event_at(event["event_at"])
    area_name = event.get("area_name")
    lines = ["🔔 Casa Tareas", "", event["title"]]
    if area_name:
        lines.append(f"🏠 {area_name}")
    lines.append(f"📅 {event_at.strftime('%d.%m.%Y · %H:%M')}")
    lines.append(f"⏰ {telegram_reminder_label(reminder_minutes)}")
    description = (event.get("description") or "").strip()
    if description:
        lines.extend(["", description[:1200]])
    return "\n".join(lines)


def process_telegram_reminders():
    if not telegram_bot_token():
        return 0

    with db() as conn:
        chat_id = get_meta(conn, "telegram_chat_id")
        if not chat_id:
            return 0
        now = now_local()
        rows = conn.execute(
            """SELECT e.*, a.name area_name
               FROM events e
               LEFT JOIN areas a ON a.id=e.area_id
               WHERE e.active=1
               ORDER BY e.event_at,e.id"""
        ).fetchall()

        candidates = []
        for row in rows:
            event = dict(row)
            event_at = normalize_event_at(event["event_at"])
            if event_at < now - timedelta(minutes=30):
                continue
            try:
                reminders = normalize_reminders(json.loads(event["reminders_json"] or "[]"))
            except (json.JSONDecodeError, TypeError):
                reminders = []

            due = [
                minutes
                for minutes in reminders
                if event_at - timedelta(minutes=minutes) <= now
            ]
            if not due:
                continue

            most_recent = min(due)
            delivered = conn.execute(
                """SELECT 1 FROM notification_deliveries
                   WHERE event_id=? AND reminder_minutes=? AND channel='telegram'""",
                (event["id"], most_recent),
            ).fetchone()
            if delivered:
                continue

            candidates.append((event, most_recent, due, int(chat_id)))

    sent = 0
    for event, most_recent, due, chat_id in candidates:
        telegram_send_message(
            chat_id,
            telegram_event_message(event, most_recent),
        )
        delivered_at = iso_now()
        with db() as conn:
            for minutes in due:
                conn.execute(
                    """INSERT OR IGNORE INTO notification_deliveries(
                       event_id,reminder_minutes,channel,delivered_at
                       ) VALUES(?,?,'telegram',?)""",
                    (event["id"], minutes, delivered_at),
                )
        sent += 1
    return sent


def telegram_find_task(conn, query):
    query = (query or "").strip()
    if not query:
        return []
    if query.startswith("#") and query[1:].isdigit():
        row = conn.execute(
            "SELECT * FROM tasks WHERE id=? AND active=1",
            (int(query[1:]),),
        ).fetchone()
        return [row] if row else []
    rows = conn.execute(
        "SELECT * FROM tasks WHERE active=1 ORDER BY title COLLATE NOCASE,id"
    ).fetchall()
    exact = [r for r in rows if r["title"].casefold() == query.casefold()]
    if exact:
        return exact
    matches = [r for r in rows if query.casefold() in r["title"].casefold()]
    return matches[:8]


def telegram_find_area(conn, query):
    query = (query or "").strip()
    if not query:
        return None
    rows = conn.execute(
        "SELECT * FROM areas WHERE active=1 ORDER BY name COLLATE NOCASE,id"
    ).fetchall()
    exact = [r for r in rows if r["name"].casefold() == query.casefold()]
    if exact:
        return exact[0]
    matches = [r for r in rows if query.casefold() in r["name"].casefold()]
    return matches[0] if len(matches) == 1 else None


def telegram_task_or_error(conn, query):
    sync_pause_states(conn)
    matches = telegram_find_task(conn, query)
    if not matches:
        raise ValueError(f'No encuentro una tarea activa que coincida con "{query}".')
    if len(matches) > 1:
        choices = "\n".join(f'• #{r["id"]} {r["title"]}' for r in matches)
        raise ValueError(
            "Hay varias tareas que coinciden. Usa el título completo o el #id:\n" + choices
        )
    pause = effective_task_pause(conn, matches[0])
    if pause:
        raise ValueError(f'La tarea está pausada hasta {pause["return_date"]}.')
    return matches[0]


def telegram_area_or_error(conn, query):
    area = telegram_find_area(conn, query)
    if not area:
        names = [
            r["name"]
            for r in conn.execute(
                "SELECT name FROM areas WHERE active=1 ORDER BY name COLLATE NOCASE"
            ).fetchall()
        ]
        raise ValueError(
            f'No encuentro el área "{query}". Áreas: ' + ", ".join(names)
        )
    return area


def telegram_parse_day(value):
    value = (value or "").strip().casefold()
    if value in {"mañana", "manana"}:
        return today_local() + timedelta(days=1)
    if value == "hoy":
        return today_local()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            "Fecha no válida. Usa mañana, hoy o AAAA-MM-DD."
        ) from exc


def telegram_parse_event_at(value):
    value = (value or "").strip()
    folded = value.casefold()
    for prefix, delta in (("mañana", 1), ("manana", 1), ("hoy", 0)):
        if folded.startswith(prefix):
            rest = value[len(prefix):].strip() or "09:00"
            try:
                hour, minute = map(int, rest.split(":", 1))
                return datetime.combine(
                    today_local() + timedelta(days=delta),
                    datetime.min.time().replace(hour=hour, minute=minute),
                    tzinfo=TZ,
                )
            except (ValueError, TypeError):
                raise ValueError("Hora no válida. Ejemplo: mañana 19:00")
    try:
        parsed = datetime.fromisoformat(value.replace(" ", "T", 1))
        return parsed.replace(tzinfo=TZ) if parsed.tzinfo is None else parsed.astimezone(TZ)
    except ValueError:
        pass
    for fmt in ("%d.%m.%Y %H:%M", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=TZ)
        except ValueError:
            continue
    raise ValueError(
        "Fecha/hora no válida. Usa AAAA-MM-DD HH:MM, DD.MM.AAAA HH:MM o mañana 19:00."
    )


def telegram_parse_reminders(value):
    value = (value or "").strip().casefold()
    if not value:
        return [1440]
    result = []
    for raw in value.replace(";", ",").split(","):
        token = raw.strip()
        if not token:
            continue
        if token in {"ahora", "0"}:
            minutes = 0
        elif token.endswith("d") and token[:-1].isdigit():
            minutes = int(token[:-1]) * 1440
        elif token.endswith("h") and token[:-1].isdigit():
            minutes = int(token[:-1]) * 60
        elif token.endswith("m") and token[:-1].isdigit():
            minutes = int(token[:-1])
        else:
            raise ValueError(
                f'Recordatorio "{token}" no válido. Ejemplos: 7d, 1d, 2h, 30m.'
            )
        result.append(minutes)
    return normalize_reminders(result)


def telegram_find_inventory_item(conn, query):
    query = (query or "").strip()
    if not query:
        raise ValueError("Indica un producto del inventario.")
    rows = conn.execute(
        """SELECT * FROM inventory_items
           WHERE active=1 ORDER BY name COLLATE NOCASE,id"""
    ).fetchall()
    exact = [r for r in rows if r["name"].casefold() == query.casefold()]
    if exact:
        return exact[0]
    matches = [r for r in rows if query.casefold() in r["name"].casefold()]
    if not matches:
        raise ValueError(f'No encuentro el producto "{query}".')
    if len(matches) > 1:
        names = ", ".join(r["name"] for r in matches[:8])
        raise ValueError("Hay varios productos que coinciden: " + names)
    return matches[0]


def telegram_help_text():
    return (
        "🏠 Casa Tareas · comandos\n\n"
        "/hoy — tareas y eventos de hoy\n"
        "/agenda — próximos eventos\n"
        "/pendientes [Área] — tareas activas\n"
        "/comprar — lista de compra\n"
        "/comprar Producto — añadir producto a Comprar\n"
        "/stock Producto | hay/poco/falta — actualizar inventario\n"
        "/tarea Título | Área | gestión — crear tarea\n"
        "/hecha Tarea — elegir quién la hizo\n"
        "/mover Tarea | Área — cambiar de área\n"
        "/renombrar Tarea | Nuevo nombre\n"
        "/posponer Tarea | mañana (o AAAA-MM-DD)\n"
        "/evento Título | AAAA-MM-DD HH:MM | Área | 1d,2h\n\n"
        "También puedes escribir /casa seguido de cualquiera de esos comandos, "
        "por ejemplo: /casa hecha Sacar basura.\n"
        "No hay comandos de borrado desde Telegram."
    )


def telegram_store_last_undo(conn, undo_id):
    if undo_id:
        set_meta(conn, "telegram_last_undo_id", undo_id)


def telegram_create_task(conn, args):
    parts = [p.strip() for p in args.split("|")]
    title = parts[0].strip() if parts else ""
    if not title:
        raise ValueError("Uso: /tarea Título | Área | gestión")
    duplicate = conn.execute(
        "SELECT id FROM tasks WHERE active=1 AND title=? COLLATE NOCASE",
        (title,),
    ).fetchone()
    if duplicate:
        raise ValueError(f'Ya existe una tarea activa con ese título (#{duplicate["id"]}).')

    area = telegram_area_or_error(conn, parts[1]) if len(parts) > 1 and parts[1] else None
    task_type = "execution"
    if len(parts) > 2 and parts[2]:
        kind = parts[2].casefold()
        if kind.startswith("gest") or kind in {"mental", "🧠"}:
            task_type = "management"
        elif kind.startswith("ejec") or kind in {"fisica", "física", "🧹"}:
            task_type = "execution"
        else:
            raise ValueError('Tipo no válido. Usa "gestión" o "ejecución".')

    due = today_local().isoformat()
    color = area["color"] if area else "#dcecff"
    icon = "🧠" if task_type == "management" else "🧹"
    cur = conn.execute(
        """INSERT INTO tasks(title,description,category,color,icon,recurrence_type,
           frequency_days,initial_due_date,anchor_date,area_id,owner_person_id,
           task_type,definition_of_done,responsibility_notes,active,created_at)
           VALUES(?,?,?,?,?,'none',NULL,?,?,?,?,?,?,?,1,?)""",
        (
            title,
            "",
            "General",
            color,
            icon,
            due,
            due,
            area["id"] if area else None,
            None,
            task_type,
            "",
            "",
            iso_now(),
        ),
    )
    task_id = cur.lastrowid
    undo_id = record_undo(
        conn,
        "create_task",
        {"task_id": task_id},
        f'Creada "{title}" desde Telegram',
    )
    telegram_store_last_undo(conn, undo_id)
    return task_id, title, area, task_type


def telegram_create_event(conn, args):
    parts = [p.strip() for p in args.split("|")]
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise ValueError(
            "Uso: /evento Título | AAAA-MM-DD HH:MM | Área | 1d,2h"
        )
    title = parts[0]
    event_at = telegram_parse_event_at(parts[1])
    area = telegram_area_or_error(conn, parts[2]) if len(parts) > 2 and parts[2] else None
    reminders = telegram_parse_reminders(parts[3] if len(parts) > 3 else "")
    cur = conn.execute(
        """INSERT INTO events(title,description,area_id,event_at,reminders_json,
           active,created_at,updated_at)
           VALUES(?,?,?,?,?,1,?,?)""",
        (
            title,
            "",
            area["id"] if area else None,
            event_at.isoformat(timespec="minutes"),
            json.dumps(reminders),
            iso_now(),
            iso_now(),
        ),
    )
    event_id = cur.lastrowid
    undo_id = record_undo(
        conn,
        "create_event",
        {"event_id": event_id},
        f'Creado evento "{title}" desde Telegram',
    )
    telegram_store_last_undo(conn, undo_id)
    return event_id, title, event_at, area, reminders


def telegram_handle_command(chat_id, text):
    text = (text or "").strip()
    if not text.startswith("/"):
        return
    first, _, rest = text.partition(" ")
    command = first.split("@", 1)[0].casefold()
    args = rest.strip()

    if command == "/casa":
        if not args:
            telegram_send_message(chat_id, telegram_help_text())
            return
        sub, _, sub_args = args.partition(" ")
        aliases = {
            "añade": "/tarea",
            "anade": "/tarea",
            "nueva": "/tarea",
            "tarea": "/tarea",
            "hecha": "/hecha",
            "realizada": "/hecha",
            "mover": "/mover",
            "renombrar": "/renombrar",
            "posponer": "/posponer",
            "evento": "/evento",
            "hoy": "/hoy",
            "agenda": "/agenda",
            "pendientes": "/pendientes",
            "comprar": "/comprar",
            "stock": "/stock",
            "ayuda": "/ayuda",
        }
        command = aliases.get(sub.casefold(), "/" + sub.casefold())
        args = sub_args.strip()

    if command in {"/start", "/ayuda", "/help"}:
        telegram_send_message(chat_id, telegram_help_text())
        return

    with db() as conn:
        if command == "/hoy":
            sync_pause_states(conn)
            task_rows = conn.execute(
                """SELECT t.* FROM today_queue q
                   JOIN tasks t ON t.id=q.task_id
                   WHERE t.active=1 ORDER BY q.position,q.task_id"""
            ).fetchall()
            task_rows = [
                r for r in task_rows if not effective_task_pause(conn, r)
            ]
            event_rows = conn.execute(
                "SELECT id,title,event_at FROM events WHERE active=1 ORDER BY event_at,id"
            ).fetchall()
            events = [
                r for r in event_rows
                if normalize_event_at(r["event_at"]).date() == today_local()
            ]
            lines = ["📌 Hoy"]
            if task_rows:
                lines.append("\nTareas:")
                lines.extend(f'• #{r["id"]} {r["title"]}' for r in task_rows)
            else:
                lines.append("\nTareas: ninguna en la cola de Hoy.")
            if events:
                lines.append("\nEventos:")
                lines.extend(
                    f'• {normalize_event_at(r["event_at"]).strftime("%H:%M")} · {r["title"]}'
                    for r in events
                )
            else:
                lines.append("\nEventos: ninguno.")
            telegram_send_message(chat_id, "\n".join(lines))
            return

        if command == "/agenda":
            rows = conn.execute(
                "SELECT id,title,event_at,area_id FROM events WHERE active=1 ORDER BY event_at,id"
            ).fetchall()
            upcoming = [
                r for r in rows if normalize_event_at(r["event_at"]) >= now_local()
            ][:10]
            if not upcoming:
                telegram_send_message(chat_id, "📅 No hay eventos próximos.")
                return
            lines = ["📅 Próximos eventos"]
            for r in upcoming:
                area = (
                    conn.execute("SELECT name FROM areas WHERE id=?", (r["area_id"],)).fetchone()
                    if r["area_id"]
                    else None
                )
                suffix = f' · {area["name"]}' if area else ""
                lines.append(
                    f'• {normalize_event_at(r["event_at"]).strftime("%d.%m %H:%M")} · '
                    f'{r["title"]}{suffix}'
                )
            telegram_send_message(chat_id, "\n".join(lines))
            return

        if command == "/pendientes":
            area = telegram_area_or_error(conn, args) if args else None
            sync_pause_states(conn)
            rows = conn.execute(
                "SELECT * FROM tasks WHERE active=1 ORDER BY title COLLATE NOCASE,id"
            ).fetchall()
            rows = [r for r in rows if not effective_task_pause(conn, r)]
            if area:
                rows = [r for r in rows if r["area_id"] == area["id"]]
            if not rows:
                telegram_send_message(
                    chat_id,
                    "✅ No hay tareas activas" + (f" en {area['name']}." if area else "."),
                )
                return
            lines = [
                "📋 Pendientes" + (f" · {area['name']}" if area else "")
            ]
            for r in rows[:25]:
                due = due_date(conn, r)
                suffix = f" · {due.isoformat()}" if due else ""
                lines.append(f'• #{r["id"]} {r["title"]}{suffix}')
            if len(rows) > 25:
                lines.append(f"… y {len(rows)-25} más.")
            telegram_send_message(chat_id, "\n".join(lines))
            return

        if command == "/comprar":
            if args:
                item = telegram_find_inventory_item(conn, args)
                conn.execute(
                    """UPDATE inventory_items
                       SET shopping_requested=1,updated_at=? WHERE id=?""",
                    (iso_now(), item["id"]),
                )
                log_activity(
                    conn,
                    "inventory_stock",
                    f'Añadido a Comprar "{item["name"]}"',
                    entity_type="inventory",
                    entity_id=item["id"],
                )
                telegram_send_message(chat_id, f'🛒 Añadido a Comprar: {item["name"]}')
                return
            rows = conn.execute(
                """SELECT * FROM inventory_items
                   WHERE active=1 AND (
                     shopping_requested=1 OR stock_status IN ('low','out')
                   )
                   ORDER BY stock_status DESC,name COLLATE NOCASE"""
            ).fetchall()
            if not rows:
                telegram_send_message(chat_id, "🛒 La lista de compra está vacía.")
                return
            lines = ["🛒 Comprar"]
            for item in rows:
                state_label = "Falta" if item["stock_status"] == "out" else (
                    "Poco" if item["stock_status"] == "low" else "Añadido"
                )
                qty = f' · {item["purchase_quantity"]}' if item["purchase_quantity"] else ""
                lines.append(f'• {item["name"]}{qty} · {state_label}')
            telegram_send_message(chat_id, "\n".join(lines))
            return

        if command == "/stock":
            parts = [p.strip() for p in args.split("|", 1)]
            if len(parts) != 2 or not all(parts):
                raise ValueError("Uso: /stock Producto | hay/poco/falta")
            item = telegram_find_inventory_item(conn, parts[0])
            aliases = {
                "hay": "ok",
                "ok": "ok",
                "poco": "low",
                "bajo": "low",
                "falta": "out",
                "agotado": "out",
            }
            status = aliases.get(parts[1].casefold())
            if not status:
                raise ValueError("Estado no válido. Usa hay, poco o falta.")
            requested = 0 if status == "ok" else item["shopping_requested"]
            conn.execute(
                """UPDATE inventory_items
                   SET stock_status=?,shopping_requested=?,updated_at=? WHERE id=?""",
                (status, requested, iso_now(), item["id"]),
            )
            labels = {"ok": "Hay", "low": "Poco", "out": "Falta"}
            log_activity(
                conn,
                "inventory_stock",
                f'{item["name"]}: {labels[status]}',
                entity_type="inventory",
                entity_id=item["id"],
            )
            telegram_send_message(
                chat_id,
                f'🧴 {item["name"]}: {labels[status]}',
            )
            return

        if command == "/tarea":
            task_id, title, area, task_type = telegram_create_task(conn, args)
            lines = [f"✅ Tarea creada · #{task_id}", title]
            if area:
                lines.append(f"🏠 {area['name']}")
            lines.append("🧠 Gestión" if task_type == "management" else "🧹 Ejecución")
            telegram_send_message(chat_id, "\n".join(lines))
            return

        if command == "/hecha":
            task = telegram_task_or_error(conn, args)
            people = conn.execute(
                "SELECT id,name,icon FROM people WHERE active=1 ORDER BY name COLLATE NOCASE,id"
            ).fetchall()
            cur = conn.execute(
                """INSERT INTO telegram_pending_actions(
                   action_type,payload,chat_id,created_at
                   ) VALUES('complete',?,?,?)""",
                (
                    json.dumps({"task_id": task["id"]}),
                    chat_id,
                    iso_now(),
                ),
            )
            pending_id = cur.lastrowid
            keyboard = {
                "inline_keyboard": [[
                    {
                        "text": f'{p["icon"]} {p["name"]}',
                        "callback_data": f"done:{pending_id}:{p['id']}",
                    }
                    for p in people
                ]]
            }
            telegram_send_message(
                chat_id,
                f'¿Quién hizo "{task["title"]}"?',
                reply_markup=keyboard,
            )
            return

        if command == "/mover":
            parts = [p.strip() for p in args.split("|", 1)]
            if len(parts) != 2 or not all(parts):
                raise ValueError("Uso: /mover Tarea | Área")
            task = telegram_task_or_error(conn, parts[0])
            destination_text = parts[1].casefold()
            area = None if destination_text in {"sin área", "sin area", "-"} else telegram_area_or_error(conn, parts[1])
            destination_pause = pause_for_area_id(conn, area["id"] if area else None)
            if destination_pause:
                raise ValueError(
                    f'El área de destino está pausada hasta {destination_pause["return_date"]}.'
                )
            previous_area_id = task["area_id"]
            new_area_id = area["id"] if area else None
            if previous_area_id == new_area_id:
                telegram_send_message(chat_id, "ℹ️ La tarea ya está en esa área.")
                return
            conn.execute(
                "UPDATE tasks SET area_id=? WHERE id=?",
                (new_area_id, task["id"]),
            )
            undo_id = record_undo(
                conn,
                "move_task_area",
                {"task_id": task["id"], "previous_area_id": previous_area_id},
                f'Movida de área "{task["title"]}"',
            )
            telegram_store_last_undo(conn, undo_id)
            telegram_send_message(
                chat_id,
                f'✅ "{task["title"]}" → {area["name"] if area else "Sin área"}',
            )
            return

        if command == "/renombrar":
            parts = [p.strip() for p in args.split("|", 1)]
            if len(parts) != 2 or not all(parts):
                raise ValueError("Uso: /renombrar Tarea | Nuevo nombre")
            task = telegram_task_or_error(conn, parts[0])
            new_title = parts[1][:120].strip()
            old_title = task["title"]
            if new_title.casefold() == old_title.casefold():
                telegram_send_message(chat_id, "ℹ️ El título no cambia.")
                return
            conn.execute(
                "UPDATE tasks SET title=? WHERE id=?",
                (new_title, task["id"]),
            )
            undo_id = record_undo(
                conn,
                "rename_task",
                {"task_id": task["id"], "previous_title": old_title},
                f'Renombrada "{old_title}" a "{new_title}"',
            )
            telegram_store_last_undo(conn, undo_id)
            telegram_send_message(chat_id, f'✅ Tarea renombrada: "{new_title}"')
            return

        if command == "/posponer":
            parts = [p.strip() for p in args.split("|", 1)]
            if len(parts) != 2 or not all(parts):
                raise ValueError("Uso: /posponer Tarea | mañana")
            task = telegram_task_or_error(conn, parts[0])
            new_day = telegram_parse_day(parts[1])
            result = postpone_task_action(conn, task["id"], new_day.isoformat())
            telegram_store_last_undo(conn, result["undo_id"])
            telegram_send_message(
                chat_id,
                f'✅ "{task["title"]}" pospuesta a {new_day.isoformat()}',
            )
            return

        if command == "/evento":
            event_id, title, event_at, area, reminders = telegram_create_event(conn, args)
            lines = [
                f"✅ Evento creado · #{event_id}",
                title,
                f"📅 {event_at.strftime('%d.%m.%Y · %H:%M')}",
            ]
            if area:
                lines.append(f"🏠 {area['name']}")
            if reminders:
                lines.append(
                    "🔔 " + ", ".join(telegram_reminder_label(m) for m in reminders)
                )
            telegram_send_message(chat_id, "\n".join(lines))
            return

        if command == "/deshacer":
            undo_id = get_meta(conn, "telegram_last_undo_id")
            if not undo_id:
                telegram_send_message(chat_id, "ℹ️ No hay una acción reciente de Telegram que deshacer.")
                return
            # Se ejecuta fuera de esta transacción para reutilizar el mismo mecanismo
            # de deshacer que utiliza la interfaz web.
        else:
            telegram_send_message(chat_id, telegram_help_text())
            return

    if command == "/deshacer":
        try:
            result = undo(int(undo_id))
        except HTTPException as exc:
            raise ValueError(str(exc.detail))
        with db() as conn:
            delete_meta(conn, "telegram_last_undo_id")
        telegram_send_message(chat_id, "↶ " + result.get("undone", "Cambio deshecho"))


def telegram_handle_callback(chat_id, callback):
    data = callback.get("data", "")
    if not data.startswith("done:"):
        telegram_api_request(
            "answerCallbackQuery",
            {"callback_query_id": callback["id"], "text": "Acción no reconocida"},
        )
        return
    try:
        _, pending_raw, person_raw = data.split(":", 2)
        pending_id = int(pending_raw)
        person_id = int(person_raw)
    except (ValueError, TypeError):
        raise ValueError("Confirmación no válida.")

    with db() as conn:
        pending = conn.execute(
            """SELECT * FROM telegram_pending_actions
               WHERE id=? AND used_at IS NULL""",
            (pending_id,),
        ).fetchone()
        if not pending or pending["chat_id"] != chat_id:
            telegram_api_request(
                "answerCallbackQuery",
                {"callback_query_id": callback["id"], "text": "Esta confirmación ya no está disponible"},
            )
            return
        created_at = datetime.fromisoformat(pending["created_at"])
        if now_local() - created_at > timedelta(minutes=30):
            conn.execute(
                "UPDATE telegram_pending_actions SET used_at=? WHERE id=?",
                (iso_now(), pending_id),
            )
            telegram_api_request(
                "answerCallbackQuery",
                {"callback_query_id": callback["id"], "text": "La confirmación ha caducado"},
            )
            return

        payload = json.loads(pending["payload"])
        result = complete_task_action(conn, int(payload["task_id"]), person_id)
        conn.execute(
            "UPDATE telegram_pending_actions SET used_at=? WHERE id=?",
            (iso_now(), pending_id),
        )
        telegram_store_last_undo(conn, result["undo_id"])

    telegram_api_request(
        "answerCallbackQuery",
        {"callback_query_id": callback["id"], "text": "Tarea registrada"},
    )
    message = callback.get("message") or {}
    if message.get("message_id"):
        telegram_api_request(
            "editMessageReplyMarkup",
            {
                "chat_id": str(chat_id),
                "message_id": str(message["message_id"]),
                "reply_markup": json.dumps({"inline_keyboard": []}),
            },
        )
    telegram_send_message(
        chat_id,
        f'✅ "{result["task_title"]}" completada por {result["person_name"]}.',
    )


def process_telegram_update(update):
    chat = telegram_update_chat(update)
    if chat:
        with db() as conn:
            remember_telegram_chat(conn, chat)
            configured = get_meta(conn, "telegram_chat_id")
        if not configured or int(configured) != int(chat["id"]):
            return

    if update.get("callback_query"):
        callback = update["callback_query"]
        message = callback.get("message") or {}
        callback_chat = message.get("chat") or {}
        if not callback_chat:
            return
        telegram_handle_callback(int(callback_chat["id"]), callback)
        return

    message = update.get("message") or update.get("channel_post")
    if not message or not message.get("text") or not chat:
        return
    text = message["text"].strip()
    if text.startswith("/"):
        telegram_handle_command(int(chat["id"]), text)


def process_telegram_updates(timeout=20):
    if not telegram_bot_token():
        return 0
    with db() as conn:
        offset = int(get_meta(conn, "telegram_update_offset", "0") or 0)

    updates = telegram_api_request(
        "getUpdates",
        {
            "offset": offset,
            "limit": 100,
            "timeout": max(0, int(timeout)),
            "allowed_updates": json.dumps(
                ["message", "channel_post", "callback_query", "my_chat_member"]
            ),
        },
    ) or []
    with db() as conn:
        set_meta(conn, "telegram_last_contact_at", iso_now())

    processed = 0
    for update in updates:
        update_id = int(update.get("update_id", offset))
        chat = telegram_update_chat(update)
        try:
            process_telegram_update(update)
        except ValueError as exc:
            if chat:
                with db() as conn:
                    configured = get_meta(conn, "telegram_chat_id")
                if configured and int(configured) == int(chat["id"]):
                    telegram_send_message(int(chat["id"]), "⚠️ " + str(exc))
        except Exception as exc:
            print(f"Telegram command error: {exc}", flush=True)
            if chat:
                try:
                    with db() as conn:
                        configured = get_meta(conn, "telegram_chat_id")
                    if configured and int(configured) == int(chat["id"]):
                        telegram_send_message(
                            int(chat["id"]),
                            "⚠️ No pude procesar ese comando. Revisa /ayuda o prueba de nuevo.",
                        )
                except Exception:
                    pass
        finally:
            with db() as conn:
                set_meta(conn, "telegram_update_offset", update_id + 1)
        processed += 1
    return processed


def telegram_command_definitions():
    return [
        {"command": "hoy", "description": "Tareas y eventos de hoy"},
        {"command": "agenda", "description": "Próximos eventos"},
        {"command": "pendientes", "description": "Tareas activas"},
        {"command": "comprar", "description": "Ver o añadir a la lista de compra"},
        {"command": "stock", "description": "Actualizar existencias"},
        {"command": "tarea", "description": "Crear una tarea"},
        {"command": "hecha", "description": "Marcar una tarea como hecha"},
        {"command": "mover", "description": "Mover una tarea de área"},
        {"command": "renombrar", "description": "Renombrar una tarea"},
        {"command": "posponer", "description": "Posponer una tarea"},
        {"command": "evento", "description": "Crear un evento"},
        {"command": "deshacer", "description": "Deshacer el último cambio del bot"},
        {"command": "ayuda", "description": "Ver ejemplos de comandos"},
    ]


def clear_telegram_runtime_state(conn, clear_seen=True):
    for key in (
        "telegram_update_offset",
        "telegram_chat_id",
        "telegram_chat_title",
        "telegram_bot_id",
        "telegram_bot_username",
        "telegram_last_contact_at",
        "telegram_last_undo_id",
    ):
        delete_meta(conn, key)
    if clear_seen:
        conn.execute("DELETE FROM telegram_chats_seen")
    conn.execute("DELETE FROM telegram_pending_actions")


def apply_telegram_identity(conn, info):
    bot_id = str(info.get("id"))
    username = info.get("username", "")
    previous = get_meta(conn, "telegram_bot_id")
    if previous and previous != bot_id:
        clear_telegram_runtime_state(conn, clear_seen=True)
    set_meta(conn, "telegram_bot_id", bot_id)
    set_meta(conn, "telegram_bot_username", username)
    set_meta(conn, "telegram_last_contact_at", iso_now())


def ensure_telegram_bot_identity(token=None):
    info = telegram_api_request("getMe", token=token)
    telegram_api_request(
        "setMyCommands",
        {"commands": json.dumps(telegram_command_definitions(), ensure_ascii=False)},
        token=token,
    )
    with db() as conn:
        apply_telegram_identity(conn, info)
    return info


async def telegram_reminder_loop():
    identity_ready = False
    active_token = None
    last_reminder_check = 0.0
    while True:
        try:
            token = await asyncio.to_thread(telegram_bot_token)
            if not token:
                active_token = None
                identity_ready = False
                await asyncio.sleep(2)
                continue
            if token != active_token:
                active_token = token
                identity_ready = False
            if not identity_ready:
                await asyncio.to_thread(ensure_telegram_bot_identity, token)
                identity_ready = True

            def sync_pauses_once():
                with db() as conn:
                    sync_pause_states(conn)

            await asyncio.to_thread(sync_pauses_once)
            await asyncio.to_thread(process_telegram_updates, 20)
            now_tick = time.monotonic()
            if now_tick - last_reminder_check >= TELEGRAM_POLL_SECONDS:
                await asyncio.to_thread(process_telegram_reminders)
                last_reminder_check = now_tick
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"Telegram worker error: {exc}", flush=True)
            await asyncio.sleep(5)


async def restart_telegram_worker():
    global TELEGRAM_TASK
    if TELEGRAM_TASK:
        await stop_telegram_worker()
    if telegram_bot_token():
        TELEGRAM_TASK = asyncio.create_task(telegram_reminder_loop())


async def stop_telegram_worker():
    global TELEGRAM_TASK
    if TELEGRAM_TASK:
        TELEGRAM_TASK.cancel()
        try:
            await TELEGRAM_TASK
        except asyncio.CancelledError:
            pass
        TELEGRAM_TASK = None


def task_json(conn, task):
    d = dict(task)
    d["active"] = bool(d["active"])
    due = due_date(conn, task)
    d["next_due"] = due.isoformat() if due else None
    d["pause"] = effective_task_pause(conn, task)
    d["paused"] = bool(d["pause"])
    need = task_need(conn, task)
    d["need_score"] = need["score"] if need else None
    d["need_label"] = need["label"] if need else None
    d["is_suggested"] = bool(need and need["suggested"])
    shopping_task_id = get_meta(conn, "shopping_task_id")
    d["is_shopping_task"] = bool(
        shopping_task_id and str(d["id"]) == str(shopping_task_id)
    )

    area = None
    if d.get("area_id"):
        row = conn.execute("SELECT * FROM areas WHERE id=?", (d["area_id"],)).fetchone()
        if row:
            area = dict(row)
            area["active"] = bool(area["active"])
    d["area"] = area

    owner_id = d.get("owner_person_id")
    source = "task" if owner_id else None
    if not owner_id and area and area["active"]:
        owner_id = area.get("owner_person_id")
        source = "area" if owner_id else None

    owner = None
    if owner_id:
        row = conn.execute(
            "SELECT id,name,color,icon,active FROM people WHERE id=?",
            (owner_id,),
        ).fetchone()
        if row and row["active"]:
            owner = dict(row)
    d["effective_owner"] = owner
    d["responsibility_source"] = source
    d["attachments"] = attachments_for(conn, "task", d["id"])
    d["attachment_count"] = len(d["attachments"])
    d["supplies"] = task_supplies(conn, d["id"])
    d["missing_supplies"] = [
        item for item in d["supplies"] if item["stock_status"] == "out"
    ]
    d["shopping_supplies"] = [
        item for item in d["supplies"] if item["needs_purchase"]
    ]
    d["blocked_by_supplies"] = bool(d["missing_supplies"])
    d["blocking_supplies"] = [
        {"id": item["id"], "name": item["name"]}
        for item in d["missing_supplies"]
    ]

    last = last_completion(conn, task["id"])
    if last:
        p = conn.execute(
            "SELECT id,name,color,icon,active FROM people WHERE id=?",
            (last["person_id"],),
        ).fetchone()
        d["last_completion"] = {"completed_at": last["completed_at"], "person": dict(p)}
    else:
        d["last_completion"] = None
    return d


def validate_task_responsibility(conn, area_id, owner_person_id):
    if area_id is not None:
        area = conn.execute(
            "SELECT id FROM areas WHERE id=? AND active=1", (area_id,)
        ).fetchone()
        if not area:
            raise HTTPException(400, "Área no válida o archivada")
    if owner_person_id is not None:
        owner = conn.execute(
            "SELECT id FROM people WHERE id=? AND active=1", (owner_person_id,)
        ).fetchone()
        if not owner:
            raise HTTPException(400, "Responsable no válido o inactivo")


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = ""
    category: str = "General"
    color: str = "#dcecff"
    icon: str = "🧹"
    recurrence_type: str = "none"
    frequency_days: int | None = Field(default=None, ge=1, le=3650)
    initial_due_date: str | None = None
    anchor_date: str | None = None
    area_id: int | None = None
    owner_person_id: int | None = None
    task_type: str = "execution"
    definition_of_done: str = ""
    responsibility_notes: str = ""
    estimated_minutes: int | None = Field(default=None, ge=1, le=1440)
    supply_ids: list[int] = Field(default_factory=list)


class AreaIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = ""
    color: str = "#e7eefb"
    icon: str = "🏠"
    owner_person_id: int | None = None


class AreaMoveIn(BaseModel):
    area_id: int | None = None


class EventIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = ""
    area_id: int | None = None
    event_at: str
    reminders: list[int] = Field(default_factory=lambda: [1440])


class TelegramChatIn(BaseModel):
    chat_id: int
    title: str = Field(default="", max_length=200)


class TelegramTokenIn(BaseModel):
    token: str = Field(min_length=20, max_length=250)


class RuntimeSettingsIn(BaseModel):
    timezone: str = Field(min_length=1, max_length=100)
    language: str = Field(default="es", pattern="^(es|en|de)$")
    telegram_poll_seconds: int = Field(ge=30, le=3600)
    ical_sync_minutes: int = Field(ge=5, le=1440)
    max_attachment_mb: int = Field(ge=1, le=500)


class GastosIntegrationIn(BaseModel):
    url: str = Field(default="", max_length=500)


class InventoryItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(default="General", max_length=80)
    area_id: int | None = None
    unit: str = Field(default="", max_length=50)
    purchase_quantity: str = Field(default="", max_length=80)
    stock_status: str = "ok"
    shopping_requested: bool = False
    notes: str = Field(default="", max_length=1000)
    gastos_product_id: int | None = Field(default=None, ge=1)


class InventoryStockIn(BaseModel):
    stock_status: str
    shopping_requested: bool | None = None


class ResetIn(BaseModel):
    confirmation: str = ""


class CalendarSubscriptionIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=8, max_length=2000)
    area_id: int | None = None


class PauseIn(BaseModel):
    return_date: str
    resume_mode: str = "continue_cycle"


class VacationIn(PauseIn):
    excluded_area_ids: list[int] = Field(default_factory=list)


class CompleteIn(BaseModel):
    person_id: int


class PostponeIn(BaseModel):
    due_date: str


class ReorderIn(BaseModel):
    task_ids: list[int]


class PersonIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    color: str = "#f7c8b6"
    icon: str = "👤"
    gastos_user_name: str | None = Field(default=None, max_length=120)


@app.on_event("startup")
async def startup():
    global TELEGRAM_TASK, CALENDAR_TASK, GASTOS_SYNC_TASK
    init_db()
    with db() as conn:
        load_runtime_settings(conn)
        sync_pause_states(conn)
        token_configured = bool(telegram_bot_token(conn))
    if token_configured:
        TELEGRAM_TASK = asyncio.create_task(telegram_reminder_loop())
    CALENDAR_TASK = asyncio.create_task(calendar_sync_loop())
    GASTOS_SYNC_TASK = asyncio.create_task(gastos_purchase_sync_loop())


@app.on_event("shutdown")
async def shutdown():
    global TELEGRAM_TASK, CALENDAR_TASK, GASTOS_SYNC_TASK
    if TELEGRAM_TASK:
        TELEGRAM_TASK.cancel()
        try:
            await TELEGRAM_TASK
        except asyncio.CancelledError:
            pass
        TELEGRAM_TASK = None
    if CALENDAR_TASK:
        CALENDAR_TASK.cancel()
        try:
            await CALENDAR_TASK
        except asyncio.CancelledError:
            pass
        CALENDAR_TASK = None
    if GASTOS_SYNC_TASK:
        GASTOS_SYNC_TASK.cancel()
        try:
            await GASTOS_SYNC_TASK
        except asyncio.CancelledError:
            pass
        GASTOS_SYNC_TASK = None


@app.get("/")
def root():
    return FileResponse(BASE_DIR / "static" / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/api/health")
def health():
    return {"ok": True, "version": "1.5.0"}


@app.get("/api/state")
def state():
    with db() as conn:
        sync_pause_states(conn)
        sync_shopping_task(conn)
        sync_today(conn)
        people_all = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM people ORDER BY active DESC,name COLLATE NOCASE,id"
            ).fetchall()
        ]
        people = [p for p in people_all if p["active"]]
        areas_all = [
            area_json(conn, r)
            for r in conn.execute(
                "SELECT * FROM areas ORDER BY active DESC,name COLLATE NOCASE,id"
            ).fetchall()
        ]
        areas = [a for a in areas_all if a["active"]]
        tasks = [
            task_json(conn, r)
            for r in conn.execute(
                "SELECT * FROM tasks ORDER BY active DESC,category,title"
            ).fetchall()
        ]
        inventory_all = [
            inventory_item_json(conn, r, include_required_by=True)
            for r in conn.execute(
                """SELECT * FROM inventory_items
                   ORDER BY active DESC,category COLLATE NOCASE,name COLLATE NOCASE,id"""
            ).fetchall()
        ]
        inventory = [item for item in inventory_all if item["active"]]
        shopping_list = [
            item for item in inventory if item["needs_purchase"]
        ]
        events = [
            event_json(conn, r)
            for r in conn.execute(
                "SELECT * FROM events WHERE active=1 ORDER BY event_at,id"
            ).fetchall()
        ]
        external_events = [
            external_event_json(conn, r)
            for r in conn.execute(
                """SELECT * FROM calendar_external_events
                   WHERE start_at>=?
                   ORDER BY start_at,id""",
                (
                    datetime.combine(
                        today_local() - timedelta(days=14),
                        datetime.min.time(),
                        tzinfo=TZ,
                    ).isoformat(timespec="minutes"),
                ),
            ).fetchall()
        ]
        agenda_events = events + external_events
        agenda_events.sort(key=lambda e: (e["event_at"], e["title"].casefold()))
        event_today = []
        event_upcoming = []
        today = today_local()
        for event in agenda_events:
            event_day = normalize_event_at(event["event_at"]).date()
            if event_day == today:
                event_today.append(event)
            elif event_day > today:
                event_upcoming.append(event)
        alerts_due = due_event_alerts(conn, events)
        today_ids = [
            r["task_id"]
            for r in conn.execute(
                "SELECT * FROM today_queue ORDER BY position,task_id"
            ).fetchall()
        ]
        by_id = {t["id"]: t for t in tasks}
        today = [
            by_id[i]
            for i in today_ids
            if i in by_id and by_id[i]["active"] and not by_id[i]["paused"]
        ]
        today_set = set(today_ids)
        suggested = sorted(
            [
                t
                for t in tasks
                if t["active"]
                and not t["paused"]
                and t["is_suggested"]
                and t["id"] not in today_set
            ],
            key=lambda t: (
                -(t["need_score"] or 0),
                t["next_due"] or "9999-12-31",
                t["estimated_minutes"] if t["estimated_minutes"] is not None else 99999,
                t["title"].lower(),
            ),
        )
        upcoming = sorted(
            [
                t
                for t in tasks
                if t["active"] and not t["paused"] and t["next_due"] and t["id"] not in today_set
            ],
            key=lambda t: (t["next_due"], t["title"].lower()),
        )
        history_rows = conn.execute(
            """SELECT c.id,c.completed_at,t.id task_id,t.title,t.icon,
                      p.id person_id,p.name,p.color,p.icon person_icon
               FROM completions c
               JOIN tasks t ON t.id=c.task_id
               JOIN people p ON p.id=c.person_id
               ORDER BY c.completed_at DESC,c.id DESC LIMIT 200"""
        ).fetchall()
        completion_undos = open_completion_undo_map(conn)
        latest_seen_tasks = set()
        history = []
        for row in history_rows:
            item = dict(row)
            undo_info = completion_undos.get(item["id"])
            is_latest_for_task = item["task_id"] not in latest_seen_tasks
            latest_seen_tasks.add(item["task_id"])
            item["can_undo_to_today"] = bool(
                is_latest_for_task
                and undo_info
                and undo_info["payload"].get("queue")
            )
            history.append(item)
        cutoff = (now_local() - timedelta(days=30)).isoformat()
        stats = [
            dict(r)
            for r in conn.execute(
                """SELECT p.id,p.name,p.color,p.icon,p.active,COUNT(c.id) count
                   FROM people p
                   LEFT JOIN completions c
                     ON c.person_id=p.id AND c.completed_at>=?
                   GROUP BY p.id
                   HAVING p.active=1 OR COUNT(c.id)>0
                   ORDER BY p.active DESC,p.name COLLATE NOCASE""",
                (cutoff,),
            ).fetchall()
        ]
        calendar_subscriptions = [
            calendar_subscription_json(conn, r)
            for r in conn.execute(
                """SELECT * FROM calendar_subscriptions
                   ORDER BY active DESC,name COLLATE NOCASE,id"""
            ).fetchall()
        ]
        activity = [
            dict(r)
            for r in conn.execute(
                """SELECT * FROM activity_log
                   ORDER BY created_at DESC,id DESC LIMIT 100"""
            ).fetchall()
        ]
        return {
            "people": people,
            "people_all": people_all,
            "areas": areas,
            "areas_all": areas_all,
            "today": today,
            "suggested": suggested,
            "upcoming": upcoming,
            "tasks": tasks,
            "inventory": inventory,
            "inventory_all": inventory_all,
            "shopping_list": shopping_list,
            "events": events,
            "external_events": external_events,
            "agenda_events": agenda_events,
            "calendar_subscriptions": calendar_subscriptions,
            "event_today": event_today,
            "event_upcoming": event_upcoming,
            "alerts_due": alerts_due,
            "vacation": get_vacation(conn),
            "telegram": telegram_status(conn),
            "settings": settings_json(conn),
            "history": history,
            "stats": stats,
            "activity": activity,
            "last_undo": latest_undo(conn),
        }


@app.get("/api/settings")
def get_settings():
    with db() as conn:
        return settings_json(conn)


@app.put("/api/settings/runtime")
def update_runtime_settings(payload: RuntimeSettingsIn):
    global TZ, TELEGRAM_POLL_SECONDS, ICAL_SYNC_MINUTES, MAX_ATTACHMENT_BYTES

    timezone_name = payload.timezone.strip()
    try:
        ZoneInfo(timezone_name)
    except Exception:
        raise HTTPException(400, "Zona horaria no válida")

    with db() as conn:
        set_meta(conn, "setting_timezone", timezone_name)
        set_meta(conn, "setting_language", payload.language)
        set_meta(
            conn,
            "setting_telegram_poll_seconds",
            payload.telegram_poll_seconds,
        )
        set_meta(conn, "setting_ical_sync_minutes", payload.ical_sync_minutes)
        set_meta(
            conn,
            "setting_max_attachment_bytes",
            payload.max_attachment_mb * 1024 * 1024,
        )
        load_runtime_settings(conn)
        log_activity(
            conn,
            "settings_updated",
            "Actualizada la configuración de Casa Tareas",
            entity_type="settings",
        )
        return settings_json(conn)


@app.put("/api/settings/gastos-comida")
def save_gastos_comida_settings(payload: GastosIntegrationIn):
    url = normalize_gastos_comida_url(payload.url)
    with db() as conn:
        if url:
            set_meta(conn, "gastos_comida_url", url)
        else:
            delete_meta(conn, "gastos_comida_url")
        delete_meta(conn, "gastos_comida_last_ok_at")
        delete_meta(conn, "gastos_comida_last_error")
        delete_meta(conn, "gastos_comida_sync_cursor_at")
        delete_meta(conn, "gastos_comida_sync_cursor_id")
        delete_meta(conn, "gastos_comida_sync_last_at")
        delete_meta(conn, "gastos_comida_sync_last_error")
        log_activity(
            conn,
            "integration_updated",
            "Actualizada la integración con Gastos de comida",
            entity_type="settings",
        )
        return {
            "ok": True,
            "integration": gastos_comida_status(conn),
        }


@app.post("/api/integrations/gastos-comida/sync")
def sync_gastos_comida_now():
    result = sync_gastos_purchase_changes()
    if not result.get("ok"):
        raise HTTPException(502, result.get("error") or "No se pudo sincronizar Gastos")
    return result


@app.post("/api/integrations/gastos-comida/test")
def test_gastos_comida_connection():
    with db() as conn:
        try:
            result = gastos_comida_api_request(conn, "/api/v1/health")
            if result.get("ok") is not True or result.get("service") != "gastos-comida":
                raise RuntimeError("La URL responde, pero no parece ser el servicio Gastos de comida")
            set_meta(conn, "gastos_comida_last_ok_at", iso_now())
            delete_meta(conn, "gastos_comida_last_error")
            return {
                "ok": True,
                "health": {
                    "api_version": result.get("api_version"),
                    "products": int(result.get("products", 0) or 0),
                    "tickets": int(result.get("tickets", 0) or 0),
                    "items": int(result.get("items", 0) or 0),
                },
                "integration": gastos_comida_status(conn),
            }
        except RuntimeError as exc:
            set_meta(conn, "gastos_comida_last_error", str(exc))
            raise HTTPException(502, str(exc))



def reconcile_gastos_ticket_with_inventory(conn, ticket):
    if not isinstance(ticket, dict):
        return []
    ticket_id = ticket.get("id")
    purchased_at = ticket.get("date") or ticket.get("purchase_date") or today_local().isoformat()
    product_ids = {
        int(item["product_id"])
        for item in ticket.get("items", [])
        if isinstance(item, dict) and item.get("product_id") is not None
    }
    if not product_ids:
        return []
    placeholders = ",".join("?" for _ in product_ids)
    rows = conn.execute(
        f"""SELECT * FROM inventory_items
            WHERE active=1 AND gastos_product_id IN ({placeholders})""",
        tuple(sorted(product_ids)),
    ).fetchall()
    updated = []
    for item in rows:
        already_reconciled = (
            item["stock_status"] == "ok"
            and not bool(item["shopping_requested"])
            and str(item["last_purchase_ticket_id"] or "") == str(ticket_id or "")
            and str(item["last_purchased_at"] or "") == str(purchased_at or "")
        )
        if already_reconciled:
            continue
        conn.execute(
            """UPDATE inventory_items
               SET stock_status='ok',shopping_requested=0,last_purchased_at=?,
                   last_purchase_ticket_id=?,updated_at=?
               WHERE id=?""",
            (purchased_at, ticket_id, iso_now(), item["id"]),
        )
        updated.append({"id": item["id"], "name": item["name"]})
        log_activity(
            conn,
            "inventory_purchased",
            f'Repuesto desde Gastos: "{item["name"]}"',
            detail=f'Ticket #{ticket_id}' if ticket_id else "",
            entity_type="inventory",
            entity_id=item["id"],
        )
    return updated


def sync_gastos_purchase_changes():
    with db() as conn:
        if not gastos_comida_url(conn):
            return {"ok": True, "configured": False, "reconciled": []}
        cursor_at = get_meta(conn, "gastos_comida_sync_cursor_at")
        try:
            cursor_id = int(get_meta(conn, "gastos_comida_sync_cursor_id", "0") or 0)
        except (TypeError, ValueError):
            cursor_id = 0

    try:
        if not cursor_at:
            with db() as conn:
                result = gastos_comida_api_request(
                    conn, "/api/v1/purchases/changes?latest=1"
                )
                cursor = result.get("cursor") or {}
                if cursor.get("updated_at"):
                    set_meta(
                        conn,
                        "gastos_comida_sync_cursor_at",
                        cursor["updated_at"],
                    )
                set_meta(
                    conn,
                    "gastos_comida_sync_cursor_id",
                    int(cursor.get("ticket_id") or 0),
                )
                set_meta(conn, "gastos_comida_sync_last_at", iso_now())
                delete_meta(conn, "gastos_comida_sync_last_error")
                set_meta(conn, "gastos_comida_last_ok_at", iso_now())
                delete_meta(conn, "gastos_comida_last_error")
            return {
                "ok": True,
                "configured": True,
                "bootstrapped": True,
                "reconciled": [],
            }

        reconciled = []
        pages = 0
        while pages < 10:
            pages += 1
            query = urllib.parse.urlencode(
                {
                    "after": cursor_at,
                    "after_id": cursor_id,
                    "limit": 100,
                }
            )
            with db() as conn:
                result = gastos_comida_api_request(
                    conn, "/api/v1/purchases/changes?" + query
                )
                for ticket in result.get("items") or []:
                    reconciled.extend(
                        reconcile_gastos_ticket_with_inventory(conn, ticket)
                    )

                cursor = result.get("cursor") or {}
                next_at = cursor.get("updated_at") or cursor_at
                next_id = int(cursor.get("ticket_id") or cursor_id)
                cursor_at = next_at
                cursor_id = next_id
                if cursor_at:
                    set_meta(conn, "gastos_comida_sync_cursor_at", cursor_at)
                set_meta(conn, "gastos_comida_sync_cursor_id", cursor_id)
                set_meta(conn, "gastos_comida_sync_last_at", iso_now())
                delete_meta(conn, "gastos_comida_sync_last_error")
                set_meta(conn, "gastos_comida_last_ok_at", iso_now())
                delete_meta(conn, "gastos_comida_last_error")
                sync_shopping_task(conn)

            if not result.get("has_more") or not result.get("items"):
                break

        return {
            "ok": True,
            "configured": True,
            "bootstrapped": False,
            "reconciled": reconciled,
            "cursor": {
                "updated_at": cursor_at,
                "ticket_id": cursor_id,
            },
        }
    except RuntimeError as exc:
        with db() as conn:
            set_meta(conn, "gastos_comida_sync_last_error", str(exc))
        return {
            "ok": False,
            "configured": True,
            "error": str(exc),
            "reconciled": [],
        }


async def gastos_purchase_sync_loop():
    while True:
        try:
            await asyncio.to_thread(sync_gastos_purchase_changes)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"Gastos sync worker error: {exc}", flush=True)
        await asyncio.sleep(GASTOS_SYNC_SECONDS)


def gastos_proxy_call(path, method="GET", payload=None):
    with db() as conn:
        try:
            result = gastos_comida_api_request(conn, path, method=method, payload=payload)
            set_meta(conn, "gastos_comida_last_ok_at", iso_now())
            delete_meta(conn, "gastos_comida_last_error")
            return result
        except RuntimeError as exc:
            set_meta(conn, "gastos_comida_last_error", str(exc))
            raise HTTPException(502, str(exc))


COUNT_PURCHASE_UNITS = {
    "", "u", "ud", "uds", "unidad", "unidades", "pieza", "piezas",
    "botella", "botellas", "paquete", "paquetes", "pack", "packs",
    "caja", "cajas", "lata", "latas", "bolsa", "bolsas",
}
MEASURE_PURCHASE_UNITS = {
    "kg", "g", "gr", "gramo", "gramos", "l", "litro", "litros",
    "ml", "mililitro", "mililitros",
}


def parse_purchase_quantity(value):
    raw = (value or "").strip()
    if not raw:
        return {
            "raw": raw,
            "value": None,
            "unit": None,
            "status": "missing",
            "estimate_eligible": False,
        }

    match = re.match(r"^([0-9]+(?:[.,][0-9]+)?)\s*([^0-9]*)$", raw, re.IGNORECASE)
    if not match:
        return {
            "raw": raw,
            "value": None,
            "unit": None,
            "status": "unrecognized",
            "estimate_eligible": False,
        }

    amount = float(match.group(1).replace(",", "."))
    unit = match.group(2).strip().casefold().rstrip(".")
    if amount <= 0:
        return {
            "raw": raw,
            "value": None,
            "unit": unit or None,
            "status": "unrecognized",
            "estimate_eligible": False,
        }

    if unit in COUNT_PURCHASE_UNITS:
        status = "count"
        eligible = True
    elif unit in MEASURE_PURCHASE_UNITS:
        status = "measurement_unverified"
        eligible = False
    else:
        status = "unit_unrecognized"
        eligible = False

    return {
        "raw": raw,
        "value": amount,
        "unit": unit or None,
        "status": status,
        "estimate_eligible": eligible,
    }


@app.get("/api/gastos/shopping-plan")
def gastos_shopping_plan():
    with db() as conn:
        shopping = [
            inventory_item_json(conn, row, include_required_by=True)
            for row in shopping_inventory_rows(conn)
        ]

    items = []
    groups = {}
    for item in shopping:
        plan_item = {
            "id": item["id"],
            "name": item["name"],
            "purchase_quantity": item.get("purchase_quantity", ""),
            "category": item.get("category", "General"),
            "gastos_product_id": item.get("gastos_product_id"),
            "recommended_supermarket": None,
            "habitual_supermarket": None,
            "average_unit_price": None,
            "recommended_unit_price": None,
            "habitual_unit_price": None,
            "estimated_saving_unit": None,
            "estimated_saving_percent": None,
            "recommendation_confidence": None,
            "recommendation_reason": None,
            "purchase_quantity_parsed": parse_purchase_quantity(
                item.get("purchase_quantity", "")
            ),
            "estimated_line_total": None,
            "estimated_baseline_total": None,
            "estimated_saving_total": None,
            "last_purchase": None,
            "pricing_available": False,
        }
        product_id = item.get("gastos_product_id")
        if product_id:
            try:
                stats = gastos_proxy_call(f"/api/v1/products/{int(product_id)}/stats")
                recommended = stats.get("recommended_supermarket")
                habitual = stats.get("habitual_supermarket")
                plan_item["recommended_supermarket"] = recommended
                plan_item["habitual_supermarket"] = habitual
                plan_item["average_unit_price"] = stats.get("average_unit_price")
                recommendation_meta = stats.get("recommendation") or {}
                plan_item["recommendation_confidence"] = recommendation_meta.get("confidence")
                plan_item["recommendation_reason"] = recommendation_meta.get("reason")
                plan_item["last_purchase"] = stats.get("last_purchase")
                plan_item["pricing_available"] = bool(
                    recommended or stats.get("last_purchase")
                )

                recommended_price = (
                    (recommended.get("recommendation_unit_price") if recommended.get("recommendation_unit_price") is not None else recommended.get("average_unit_price"))
                    if isinstance(recommended, dict)
                    else None
                )
                habitual_price = (
                    (habitual.get("recommendation_unit_price") if habitual.get("recommendation_unit_price") is not None else habitual.get("average_unit_price"))
                    if isinstance(habitual, dict)
                    else None
                )
                plan_item["recommended_unit_price"] = recommended_price
                plan_item["habitual_unit_price"] = habitual_price
                if (
                    recommended_price is not None
                    and habitual_price is not None
                    and float(habitual_price) > 0
                ):
                    saving = max(
                        0.0,
                        float(habitual_price) - float(recommended_price),
                    )
                    plan_item["estimated_saving_unit"] = round(saving, 2)
                    plan_item["estimated_saving_percent"] = round(
                        (saving / float(habitual_price)) * 100,
                        1,
                    )

                parsed_quantity = plan_item["purchase_quantity_parsed"]
                if (
                    parsed_quantity.get("estimate_eligible")
                    and parsed_quantity.get("value") is not None
                    and recommended_price is not None
                ):
                    multiplier = float(parsed_quantity["value"])
                    plan_item["estimated_line_total"] = round(
                        float(recommended_price) * multiplier, 2
                    )
                    if habitual_price is not None:
                        plan_item["estimated_baseline_total"] = round(
                            float(habitual_price) * multiplier, 2
                        )
                        plan_item["estimated_saving_total"] = round(
                            max(
                                0.0,
                                float(habitual_price) - float(recommended_price),
                            )
                            * multiplier,
                            2,
                        )
            except HTTPException:
                pass

        supermarket = (
            (plan_item["recommended_supermarket"] or {}).get("supermarket")
            or "Sin recomendación"
        )
        groups.setdefault(supermarket, []).append(plan_item)
        items.append(plan_item)

    ordered_groups = []
    total_saving = 0.0
    total_savings_count = 0
    for supermarket in sorted(
        groups,
        key=lambda value: (value == "Sin recomendación", value.casefold()),
    ):
        group_items = groups[supermarket]
        estimated_total = 0.0
        baseline_total = 0.0
        group_saving = 0.0
        priced_count = 0
        comparable_count = 0
        savings_count = 0
        basket_total = 0.0
        basket_baseline_total = 0.0
        basket_saving_total = 0.0
        basket_priced_count = 0
        for item in group_items:
            price = item.get("recommended_unit_price")
            if price is not None:
                estimated_total += float(price)
                priced_count += 1

            habitual_price = item.get("habitual_unit_price")
            saving = item.get("estimated_saving_unit")
            if habitual_price is not None and saving is not None:
                baseline_total += float(habitual_price)
                comparable_count += 1
                group_saving += float(saving)
                if float(saving) > 0:
                    savings_count += 1

            line_total = item.get("estimated_line_total")
            if line_total is not None:
                basket_total += float(line_total)
                basket_priced_count += 1
            line_baseline = item.get("estimated_baseline_total")
            if line_baseline is not None:
                basket_baseline_total += float(line_baseline)
            line_saving = item.get("estimated_saving_total")
            if line_saving is not None:
                basket_saving_total += float(line_saving)

        total_saving += group_saving
        total_savings_count += savings_count
        ordered_groups.append(
            {
                "supermarket": supermarket,
                "items": group_items,
                "count": len(group_items),
                "estimated_unit_total": round(estimated_total, 2),
                "estimated_baseline_unit_total": round(baseline_total, 2),
                "estimated_saving_unit_total": round(group_saving, 2),
                "priced_count": priced_count,
                "comparable_count": comparable_count,
                "savings_count": savings_count,
                "estimated_basket_total": round(basket_total, 2),
                "estimated_basket_baseline_total": round(basket_baseline_total, 2),
                "estimated_basket_saving": round(basket_saving_total, 2),
                "basket_priced_count": basket_priced_count,
                "basket_complete": basket_priced_count == len(group_items),
            }
        )

    basket_total = sum(
        float(item["estimated_line_total"])
        for item in items
        if item.get("estimated_line_total") is not None
    )
    basket_baseline_total = sum(
        float(item["estimated_baseline_total"])
        for item in items
        if item.get("estimated_baseline_total") is not None
    )
    basket_saving_total = sum(
        float(item["estimated_saving_total"])
        for item in items
        if item.get("estimated_saving_total") is not None
    )
    basket_priced_count = sum(
        1 for item in items if item.get("estimated_line_total") is not None
    )

    return {
        "items": items,
        "groups": ordered_groups,
        "count": len(items),
        "linked_count": sum(
            1 for item in items if item.get("gastos_product_id") is not None
        ),
        "recommended_count": sum(
            1 for item in items if item.get("recommended_supermarket")
        ),
        "estimated_saving_unit_total": round(total_saving, 2),
        "savings_count": total_savings_count,
        "estimated_basket_total": round(basket_total, 2),
        "estimated_basket_baseline_total": round(basket_baseline_total, 2),
        "estimated_basket_saving": round(basket_saving_total, 2),
        "basket_priced_count": basket_priced_count,
        "basket_complete": basket_priced_count == len(items),
        "basket_unpriced_count": len(items) - basket_priced_count,
    }


@app.get("/api/gastos/home-summary")
def gastos_home_summary():
    today = today_local()
    current_start = today.replace(day=1)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end.replace(day=1)

    current_query = urllib.parse.urlencode(
        {"from": current_start.isoformat(), "to": today.isoformat()}
    )
    previous_query = urllib.parse.urlencode(
        {"from": previous_start.isoformat(), "to": previous_end.isoformat()}
    )
    current = gastos_proxy_call("/api/v1/spending/summary?" + current_query)
    previous = gastos_proxy_call("/api/v1/spending/summary?" + previous_query)
    current_total = float(current.get("total") or 0.0)
    previous_total = float(previous.get("total") or 0.0)
    change_percent = None
    if previous_total:
        change_percent = round(
            ((current_total - previous_total) / previous_total) * 100,
            1,
        )
    return {
        "current_month": current,
        "previous_month": previous,
        "change_percent": change_percent,
    }


@app.get("/api/gastos/dashboard")
def gastos_dashboard(
    article: str = "",
    user: str = "",
    supermarket: str = "",
    start_date: str = "",
    end_date: str = "",
    chart_year: int | None = None,
):
    params = {}
    if article:
        params["article"] = article
    if user:
        params["user"] = user
    if supermarket:
        params["supermarket"] = supermarket
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    if chart_year is not None:
        params["chart_year"] = str(chart_year)
    query = urllib.parse.urlencode(params)
    return gastos_proxy_call("/api/v1/dashboard" + (f"?{query}" if query else ""))


@app.get("/api/gastos/tickets")
def gastos_tickets(limit: int = 200):
    limit = max(1, min(1000, limit))
    return gastos_proxy_call(f"/api/v1/tickets?limit={limit}")


@app.get("/api/gastos/tickets/{ticket_id}")
def gastos_ticket(ticket_id: int):
    return gastos_proxy_call(f"/api/v1/tickets/{ticket_id}")


@app.post("/api/gastos/tickets")
def gastos_create_ticket(payload: dict):
    result = gastos_proxy_call("/api/v1/tickets", method="POST", payload=payload)
    with db() as conn:
        result["inventory_restocked"] = reconcile_gastos_ticket_with_inventory(
            conn, result.get("ticket")
        )
    return result


@app.put("/api/gastos/tickets/{ticket_id}")
def gastos_update_ticket(ticket_id: int, payload: dict):
    return gastos_proxy_call(f"/api/v1/tickets/{ticket_id}", method="PUT", payload=payload)


@app.delete("/api/gastos/tickets/{ticket_id}")
def gastos_delete_ticket(ticket_id: int):
    return gastos_proxy_call(f"/api/v1/tickets/{ticket_id}", method="DELETE")


@app.get("/api/gastos/products")
def gastos_products(q: str = "", limit: int = 100):
    params = {"limit": max(1, min(500, limit))}
    if q:
        params["q"] = q
    return gastos_proxy_call("/api/v1/products?" + urllib.parse.urlencode(params))


@app.get("/api/gastos/products/{product_id}")
def gastos_product(product_id: int):
    return gastos_proxy_call(f"/api/v1/products/{product_id}")


@app.get("/api/gastos/products/{product_id}/stats")
def gastos_product_stats(product_id: int):
    return gastos_proxy_call(f"/api/v1/products/{product_id}/stats")


@app.get("/api/gastos/lookups")
def gastos_lookups():
    return gastos_proxy_call("/api/v1/lookups")


@app.get("/api/gastos/users")
def gastos_users():
    lookups = gastos_proxy_call("/api/v1/lookups")
    users = list(lookups.get("users") or [])
    with db() as conn:
        linked_rows = conn.execute(
            """SELECT id,name,color,icon,active,gastos_user_name
               FROM people
               WHERE gastos_user_name IS NOT NULL AND gastos_user_name <> ''
               ORDER BY active DESC,name COLLATE NOCASE,id"""
        ).fetchall()
    by_user = {
        row["gastos_user_name"]: {
            "id": row["id"],
            "name": row["name"],
            "color": row["color"],
            "icon": row["icon"],
            "active": bool(row["active"]),
        }
        for row in linked_rows
    }
    return {
        "users": [
            {"name": user_name, "person": by_user.get(user_name)}
            for user_name in users
        ],
        "linked_count": sum(1 for user_name in users if user_name in by_user),
    }


@app.get("/api/gastos/integration-health")
def gastos_integration_health():
    products_payload = gastos_proxy_call("/api/v1/products?limit=500")
    lookups = gastos_proxy_call("/api/v1/lookups")
    products = list(products_payload.get("items") or [])
    users = list(lookups.get("users") or [])

    product_by_id = {
        int(product["id"]): product
        for product in products
        if product.get("id") is not None
    }
    products_by_name: dict[str, list[dict]] = {}
    for product in products:
        key = str(product.get("name") or "").strip().casefold()
        if key:
            products_by_name.setdefault(key, []).append(product)

    users_by_name: dict[str, list[str]] = {}
    for user_name in users:
        key = str(user_name or "").strip().casefold()
        if key:
            users_by_name.setdefault(key, []).append(user_name)

    with db() as conn:
        inventory_rows = conn.execute(
            """SELECT id,name,gastos_product_id
               FROM inventory_items
               WHERE active=1
               ORDER BY name COLLATE NOCASE,id"""
        ).fetchall()
        people_rows = conn.execute(
            """SELECT id,name,color,icon,gastos_user_name
               FROM people
               WHERE active=1
               ORDER BY name COLLATE NOCASE,id"""
        ).fetchall()

    product_suggestions = []
    stale_product_links = []
    linked_inventory = 0
    for row in inventory_rows:
        linked_id = row["gastos_product_id"]
        if linked_id is not None:
            linked_inventory += 1
            if int(linked_id) not in product_by_id:
                stale_product_links.append(
                    {
                        "inventory_id": row["id"],
                        "inventory_name": row["name"],
                        "gastos_product_id": linked_id,
                    }
                )
            continue
        matches = products_by_name.get(str(row["name"] or "").strip().casefold(), [])
        if len(matches) == 1:
            product_suggestions.append(
                {
                    "inventory_id": row["id"],
                    "inventory_name": row["name"],
                    "product_id": matches[0]["id"],
                    "product_name": matches[0].get("name") or row["name"],
                }
            )

    user_suggestions = []
    stale_user_links = []
    linked_people = 0
    known_users = set(users)
    for row in people_rows:
        linked_user = (row["gastos_user_name"] or "").strip()
        if linked_user:
            linked_people += 1
            if linked_user not in known_users:
                stale_user_links.append(
                    {
                        "person_id": row["id"],
                        "person_name": row["name"],
                        "gastos_user_name": linked_user,
                    }
                )
            continue
        matches = users_by_name.get(str(row["name"] or "").strip().casefold(), [])
        if len(matches) == 1:
            user_suggestions.append(
                {
                    "person_id": row["id"],
                    "person_name": row["name"],
                    "gastos_user_name": matches[0],
                }
            )

    linked_gastos_users = {
        (row["gastos_user_name"] or "").strip()
        for row in people_rows
        if (row["gastos_user_name"] or "").strip()
    }

    return {
        "inventory": {
            "total": len(inventory_rows),
            "linked": linked_inventory,
            "unlinked": len(inventory_rows) - linked_inventory,
            "exact_match_suggestions": product_suggestions,
            "stale_links": stale_product_links,
        },
        "products": {
            "total": len(products),
        },
        "people": {
            "total": len(people_rows),
            "linked": linked_people,
            "unlinked": len(people_rows) - linked_people,
            "exact_match_suggestions": user_suggestions,
            "stale_links": stale_user_links,
        },
        "users": {
            "total": len(users),
            "linked": sum(1 for user_name in users if user_name in linked_gastos_users),
            "unlinked": sum(1 for user_name in users if user_name not in linked_gastos_users),
        },
        "status": "attention"
        if stale_product_links or stale_user_links
        else ("suggestions" if product_suggestions or user_suggestions else "ok"),
    }


@app.delete("/api/gastos/lookups/{category}")
def gastos_delete_lookup(category: str, value: str):
    query = urllib.parse.urlencode({"value": value})
    return gastos_proxy_call(f"/api/v1/lookups/{urllib.parse.quote(category)}?{query}", method="DELETE")


@app.put("/api/settings/telegram-token")
async def save_telegram_token(payload: TelegramTokenIn):
    if (TELEGRAM_BOT_TOKEN or "").strip():
        raise HTTPException(
            409,
            "El token está gestionado por TELEGRAM_BOT_TOKEN en el entorno. "
            "Elimínalo de .env y recrea el contenedor una vez si quieres gestionarlo desde la web.",
        )

    token = payload.token.strip()
    if any(ch.isspace() for ch in token):
        raise HTTPException(400, "El token de Telegram no puede contener espacios")

    try:
        info = await asyncio.to_thread(
            telegram_api_request,
            "getMe",
            None,
            token,
        )
        await asyncio.to_thread(
            telegram_api_request,
            "setMyCommands",
            {"commands": json.dumps(telegram_command_definitions(), ensure_ascii=False)},
            token,
        )
    except RuntimeError as exc:
        raise HTTPException(400, f"Telegram no aceptó el token: {exc}")

    await stop_telegram_worker()
    with db() as conn:
        set_meta(conn, "telegram_bot_token", token)
        apply_telegram_identity(conn, info)
        username = info.get("username", "")
        log_activity(
            conn,
            "telegram_configured",
            f'Telegram configurado{f" para @{username}" if username else ""}',
            entity_type="settings",
        )
    await restart_telegram_worker()

    with db() as conn:
        return {
            "ok": True,
            "telegram": telegram_status(conn),
        }


@app.delete("/api/settings/telegram-token")
async def delete_telegram_token():
    if (TELEGRAM_BOT_TOKEN or "").strip():
        raise HTTPException(
            409,
            "El token está gestionado por TELEGRAM_BOT_TOKEN en el entorno y no puede borrarse desde la web.",
        )

    await stop_telegram_worker()
    with db() as conn:
        had_token = bool(get_meta(conn, "telegram_bot_token", ""))
        delete_meta(conn, "telegram_bot_token")
        clear_telegram_runtime_state(conn, clear_seen=True)
        if had_token:
            log_activity(
                conn,
                "telegram_disconnected",
                "Eliminada la configuración del bot de Telegram",
                entity_type="settings",
            )
        return {
            "ok": True,
            "already_empty": not had_token,
            "telegram": telegram_status(conn),
        }


@app.get("/api/telegram/status")
def get_telegram_status():
    with db() as conn:
        return telegram_status(conn)


@app.post("/api/telegram/chats")
def detect_telegram_chats():
    if not telegram_bot_token():
        raise HTTPException(400, "Configura primero el bot en Configuración → Telegram")
    try:
        return {"chats": telegram_detect_chats()}
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))


@app.put("/api/telegram/chat")
def configure_telegram_chat(payload: TelegramChatIn):
    if not telegram_bot_token():
        raise HTTPException(400, "Configura primero el bot en Configuración → Telegram")
    try:
        chat = telegram_api_request("getChat", {"chat_id": str(payload.chat_id)})
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))

    title = (
        chat.get("title")
        or " ".join(x for x in [chat.get("first_name"), chat.get("last_name")] if x)
        or chat.get("username")
        or payload.title
        or str(payload.chat_id)
    )
    with db() as conn:
        set_meta(conn, "telegram_chat_id", payload.chat_id)
        set_meta(conn, "telegram_chat_title", title)
        set_meta(conn, "telegram_last_contact_at", iso_now())
    return {"ok": True, "chat_id": payload.chat_id, "chat_title": title}


@app.delete("/api/telegram/chat")
def disconnect_telegram_chat():
    with db() as conn:
        delete_meta(conn, "telegram_chat_id")
        delete_meta(conn, "telegram_chat_title")
    return {"ok": True}


@app.post("/api/telegram/test")
def test_telegram():
    if not telegram_bot_token():
        raise HTTPException(400, "Configura primero el bot en Configuración → Telegram")
    with db() as conn:
        chat_id = get_meta(conn, "telegram_chat_id")
        title = get_meta(conn, "telegram_chat_title", "")
    if not chat_id:
        raise HTTPException(400, "Selecciona primero un chat de Telegram")
    try:
        telegram_api_request(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": "✅ Casa Tareas está conectado con Telegram.\n\nAdemás de recibir recordatorios, puedes escribir /ayuda para ver los comandos disponibles.",
            },
        )
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))
    with db() as conn:
        set_meta(conn, "telegram_last_contact_at", iso_now())
    return {"ok": True, "chat_title": title}


def validate_calendar_area(conn, area_id):
    if area_id is None:
        return
    area = conn.execute(
        "SELECT id FROM areas WHERE id=? AND active=1",
        (area_id,),
    ).fetchone()
    if not area:
        raise HTTPException(400, "Área no válida o archivada")


@app.post("/api/calendars")
def create_calendar_subscription(payload: CalendarSubscriptionIn):
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "El nombre del calendario no puede estar vacío")
    url = normalize_calendar_url(payload.url)
    with db() as conn:
        validate_calendar_area(conn, payload.area_id)
        cur = conn.execute(
            """INSERT INTO calendar_subscriptions(
               name,url,area_id,active,created_at,updated_at
               ) VALUES(?,?,?,1,?,?)""",
            (name, url, payload.area_id, iso_now(), iso_now()),
        )
        subscription_id = cur.lastrowid
        log_activity(
            conn,
            "calendar_added",
            f'Añadido el calendario externo "{name}"',
            entity_type="calendar",
            entity_id=subscription_id,
        )
    try:
        count = sync_calendar_subscription(subscription_id)
        return {"id": subscription_id, "synced": True, "event_count": count}
    except RuntimeError as exc:
        return {
            "id": subscription_id,
            "synced": False,
            "error": str(exc),
            "event_count": 0,
        }


@app.put("/api/calendars/{subscription_id}")
def update_calendar_subscription(
    subscription_id: int,
    payload: CalendarSubscriptionIn,
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "El nombre del calendario no puede estar vacío")
    url = normalize_calendar_url(payload.url)
    with db() as conn:
        existing = conn.execute(
            "SELECT * FROM calendar_subscriptions WHERE id=?",
            (subscription_id,),
        ).fetchone()
        if not existing:
            raise HTTPException(404, "Calendario externo no encontrado")
        validate_calendar_area(conn, payload.area_id)
        conn.execute(
            """UPDATE calendar_subscriptions
               SET name=?,url=?,area_id=?,active=1,updated_at=?
               WHERE id=?""",
            (name, url, payload.area_id, iso_now(), subscription_id),
        )
        log_activity(
            conn,
            "calendar_updated",
            f'Actualizado el calendario externo "{name}"',
            entity_type="calendar",
            entity_id=subscription_id,
        )
    try:
        count = sync_calendar_subscription(subscription_id)
        return {"ok": True, "synced": True, "event_count": count}
    except RuntimeError as exc:
        return {"ok": True, "synced": False, "error": str(exc)}


@app.post("/api/calendars/sync")
def sync_calendars_now():
    sync_all_calendars()
    return {"ok": True}


@app.post("/api/calendars/{subscription_id}/sync")
def sync_one_calendar(subscription_id: int):
    try:
        count = sync_calendar_subscription(subscription_id)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))
    return {"ok": True, "event_count": count}


@app.delete("/api/calendars/{subscription_id}")
def delete_calendar_subscription(subscription_id: int):
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM calendar_subscriptions WHERE id=?",
            (subscription_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Calendario externo no encontrado")
        conn.execute(
            "DELETE FROM calendar_subscriptions WHERE id=?",
            (subscription_id,),
        )
        log_activity(
            conn,
            "calendar_deleted",
            f'Eliminado el calendario externo "{row["name"]}"',
            entity_type="calendar",
            entity_id=subscription_id,
        )
    return {"ok": True}


@app.post("/api/events")
def create_event(payload: EventIn):
    event_at = normalize_event_at(payload.event_at)
    reminders = normalize_reminders(payload.reminders)
    with db() as conn:
        if payload.area_id is not None:
            area = conn.execute(
                "SELECT id FROM areas WHERE id=? AND active=1",
                (payload.area_id,),
            ).fetchone()
            if not area:
                raise HTTPException(400, "Área no válida o archivada")
        cur = conn.execute(
            """INSERT INTO events(title,description,area_id,event_at,reminders_json,
               active,created_at,updated_at)
               VALUES(?,?,?,?,?,1,?,?)""",
            (
                payload.title.strip(),
                payload.description.strip(),
                payload.area_id,
                event_at.isoformat(timespec="minutes"),
                json.dumps(reminders),
                iso_now(),
                iso_now(),
            ),
        )
        event_id = cur.lastrowid
        log_activity(
            conn,
            "event_created",
            f'Creado el evento "{payload.title.strip()}"',
            entity_type="event",
            entity_id=event_id,
        )
        return {"id": event_id}


@app.put("/api/events/{event_id}")
def update_event(event_id: int, payload: EventIn):
    event_at = normalize_event_at(payload.event_at)
    reminders = normalize_reminders(payload.reminders)
    with db() as conn:
        event = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        if not event:
            raise HTTPException(404, "Evento no encontrado")
        if payload.area_id is not None:
            area = conn.execute(
                "SELECT id FROM areas WHERE id=? AND active=1",
                (payload.area_id,),
            ).fetchone()
            if not area:
                raise HTTPException(400, "Área no válida o archivada")
        conn.execute(
            """UPDATE events SET title=?,description=?,area_id=?,event_at=?,
               reminders_json=?,active=1,updated_at=? WHERE id=?""",
            (
                payload.title.strip(),
                payload.description.strip(),
                payload.area_id,
                event_at.isoformat(timespec="minutes"),
                json.dumps(reminders),
                iso_now(),
                event_id,
            ),
        )
        conn.execute("DELETE FROM event_alert_ack WHERE event_id=?", (event_id,))
        conn.execute("DELETE FROM notification_deliveries WHERE event_id=?", (event_id,))
        log_activity(
            conn,
            "event_updated",
            f'Actualizado el evento "{payload.title.strip()}"',
            entity_type="event",
            entity_id=event_id,
        )
        return {"ok": True}


@app.delete("/api/events/{event_id}")
def delete_event(event_id: int):
    with db() as conn:
        event = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        if not event:
            raise HTTPException(404, "Evento no encontrado")
        conn.execute("DELETE FROM events WHERE id=?", (event_id,))
        log_activity(
            conn,
            "event_deleted",
            f'Eliminado el evento "{event["title"]}"',
            entity_type="event",
            entity_id=event_id,
        )
        return {"ok": True}


@app.post("/api/events/{event_id}/reminders/{minutes}/ack")
def acknowledge_event_reminder(event_id: int, minutes: int):
    if minutes < 0 or minutes > 525600:
        raise HTTPException(400, "Recordatorio no válido")
    with db() as conn:
        event = conn.execute("SELECT id FROM events WHERE id=?", (event_id,)).fetchone()
        if not event:
            raise HTTPException(404, "Evento no encontrado")
        conn.execute(
            """INSERT INTO event_alert_ack(event_id,reminder_minutes,acknowledged_at)
               VALUES(?,?,?)
               ON CONFLICT(event_id,reminder_minutes)
               DO UPDATE SET acknowledged_at=excluded.acknowledged_at""",
            (event_id, minutes, iso_now()),
        )
        return {"ok": True}


def validate_attachment_entity(conn, entity_type, entity_id):
    if entity_type == "task":
        row = conn.execute("SELECT id,title FROM tasks WHERE id=?", (entity_id,)).fetchone()
        label = row["title"] if row else None
    elif entity_type == "area":
        row = conn.execute("SELECT id,name FROM areas WHERE id=?", (entity_id,)).fetchone()
        label = row["name"] if row else None
    else:
        raise HTTPException(400, "Tipo de adjunto no válido")
    if not row:
        raise HTTPException(404, "El elemento al que quieres adjuntar el archivo no existe")
    return label


@app.post("/api/attachments")
async def upload_attachment(
    entity_type: str = Form(...),
    entity_id: int = Form(...),
    file: UploadFile = File(...),
):
    with db() as conn:
        label = validate_attachment_entity(conn, entity_type, entity_id)

    original_name = Path(file.filename or "archivo").name.strip() or "archivo"
    suffix = Path(original_name).suffix.lower()
    if len(suffix) > 12 or any(ch not in ".abcdefghijklmnopqrstuvwxyz0123456789" for ch in suffix):
        suffix = ""
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    path = ATTACHMENTS_DIR / stored_name
    total = 0
    try:
        with path.open("wb") as handle:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_ATTACHMENT_BYTES:
                    raise HTTPException(
                        413,
                        f"El archivo supera el límite de {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB",
                    )
                handle.write(chunk)
    except Exception:
        if path.exists():
            path.unlink()
        raise
    finally:
        await file.close()

    if total == 0:
        if path.exists():
            path.unlink()
        raise HTTPException(400, "El archivo está vacío")

    try:
        with db() as conn:
            validate_attachment_entity(conn, entity_type, entity_id)
            cur = conn.execute(
                """INSERT INTO attachments(
                   entity_type,entity_id,original_name,stored_name,content_type,
                   size_bytes,created_at
                   ) VALUES(?,?,?,?,?,?,?)""",
                (
                    entity_type,
                    entity_id,
                    original_name[:255],
                    stored_name,
                    (file.content_type or "application/octet-stream")[:200],
                    total,
                    iso_now(),
                ),
            )
            attachment_id = cur.lastrowid
            log_activity(
                conn,
                "attachment_added",
                f'Adjuntado "{original_name}" a {label}',
                entity_type=entity_type,
                entity_id=entity_id,
            )
    except Exception:
        if path.exists():
            path.unlink()
        raise
    return {"id": attachment_id}


@app.get("/api/attachments/{attachment_id}/download")
def download_attachment(attachment_id: int):
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM attachments WHERE id=?",
            (attachment_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Adjunto no encontrado")
        data = dict(row)
    path = ATTACHMENTS_DIR / data["stored_name"]
    if not path.exists():
        raise HTTPException(404, "El archivo ya no está disponible en disco")
    return FileResponse(
        path,
        media_type=data["content_type"],
        filename=data["original_name"],
        headers={"Cache-Control": "no-store"},
    )


@app.delete("/api/attachments/{attachment_id}")
def delete_attachment(attachment_id: int):
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM attachments WHERE id=?",
            (attachment_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Adjunto no encontrado")
        data = dict(row)
        conn.execute("DELETE FROM attachments WHERE id=?", (attachment_id,))
        log_activity(
            conn,
            "attachment_deleted",
            f'Eliminado el adjunto "{data["original_name"]}"',
            entity_type=data["entity_type"],
            entity_id=data["entity_id"],
        )
    delete_attachment_file(data)
    return {"ok": True}


def validate_inventory_payload(conn, payload: InventoryItemIn, item_id=None):
    if payload.stock_status not in {"ok", "low", "out"}:
        raise HTTPException(400, "Estado de stock no válido")
    if payload.area_id is not None:
        area = conn.execute(
            "SELECT id FROM areas WHERE id=? AND active=1",
            (payload.area_id,),
        ).fetchone()
        if not area:
            raise HTTPException(400, "Área no válida o archivada")
    if payload.gastos_product_id is not None:
        linked = conn.execute(
            """SELECT id,name FROM inventory_items
               WHERE gastos_product_id=? AND active=1 AND (? IS NULL OR id<>?)""",
            (payload.gastos_product_id, item_id, item_id),
        ).fetchone()
        if linked:
            raise HTTPException(
                409,
                f'El producto de Gastos ya está vinculado a "{linked["name"]}"',
            )


@app.post("/api/inventory")
def create_inventory_item(payload: InventoryItemIn):
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "El nombre del producto no puede estar vacío")
    with db() as conn:
        validate_inventory_payload(conn, payload)
        existing = conn.execute(
            "SELECT * FROM inventory_items WHERE name=? COLLATE NOCASE",
            (name,),
        ).fetchone()
        if existing:
            if existing["active"]:
                raise HTTPException(409, "Ya existe un producto con ese nombre")
            conn.execute(
                """UPDATE inventory_items SET active=1,category=?,area_id=?,unit=?,
                   purchase_quantity=?,stock_status=?,shopping_requested=?,notes=?,
                   gastos_product_id=?,updated_at=? WHERE id=?""",
                (
                    payload.category.strip() or "General",
                    payload.area_id,
                    payload.unit.strip(),
                    payload.purchase_quantity.strip(),
                    payload.stock_status,
                    1 if payload.shopping_requested else 0,
                    payload.notes.strip(),
                    payload.gastos_product_id,
                    iso_now(),
                    existing["id"],
                ),
            )
            item_id = existing["id"]
        else:
            cur = conn.execute(
                """INSERT INTO inventory_items(
                   name,category,area_id,unit,purchase_quantity,stock_status,
                   shopping_requested,notes,gastos_product_id,active,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,1,?,?)""",
                (
                    name,
                    payload.category.strip() or "General",
                    payload.area_id,
                    payload.unit.strip(),
                    payload.purchase_quantity.strip(),
                    payload.stock_status,
                    1 if payload.shopping_requested else 0,
                    payload.notes.strip(),
                    payload.gastos_product_id,
                    iso_now(),
                    iso_now(),
                ),
            )
            item_id = cur.lastrowid
        log_activity(
            conn,
            "inventory_created",
            f'Añadido al inventario "{name}"',
            entity_type="inventory",
            entity_id=item_id,
        )
        return {"id": item_id}


@app.put("/api/inventory/{item_id}")
def update_inventory_item(item_id: int, payload: InventoryItemIn):
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "El nombre del producto no puede estar vacío")
    with db() as conn:
        validate_inventory_payload(conn, payload, item_id=item_id)
        item = conn.execute(
            "SELECT * FROM inventory_items WHERE id=?",
            (item_id,),
        ).fetchone()
        if not item:
            raise HTTPException(404, "Producto no encontrado")
        try:
            conn.execute(
                """UPDATE inventory_items SET name=?,category=?,area_id=?,unit=?,
                   purchase_quantity=?,stock_status=?,shopping_requested=?,notes=?,
                   gastos_product_id=?,updated_at=? WHERE id=?""",
                (
                    name,
                    payload.category.strip() or "General",
                    payload.area_id,
                    payload.unit.strip(),
                    payload.purchase_quantity.strip(),
                    payload.stock_status,
                    1 if payload.shopping_requested else 0,
                    payload.notes.strip(),
                    payload.gastos_product_id,
                    iso_now(),
                    item_id,
                ),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Ya existe un producto con ese nombre")
        log_activity(
            conn,
            "inventory_updated",
            f'Actualizado el producto "{name}"',
            entity_type="inventory",
            entity_id=item_id,
        )
        return {"ok": True}


@app.post("/api/inventory/{item_id}/stock")
def update_inventory_stock(item_id: int, payload: InventoryStockIn):
    if payload.stock_status not in {"ok", "low", "out"}:
        raise HTTPException(400, "Estado de stock no válido")
    with db() as conn:
        item = conn.execute(
            "SELECT * FROM inventory_items WHERE id=? AND active=1",
            (item_id,),
        ).fetchone()
        if not item:
            raise HTTPException(404, "Producto no encontrado")
        requested = (
            int(payload.shopping_requested)
            if payload.shopping_requested is not None
            else item["shopping_requested"]
        )
        if payload.stock_status == "ok" and payload.shopping_requested is None:
            requested = 0
        conn.execute(
            """UPDATE inventory_items SET stock_status=?,shopping_requested=?,
               updated_at=? WHERE id=?""",
            (payload.stock_status, requested, iso_now(), item_id),
        )
        labels = {"ok": "Hay", "low": "Poco", "out": "Falta"}
        log_activity(
            conn,
            "inventory_stock",
            f'{item["name"]}: {labels[payload.stock_status]}',
            entity_type="inventory",
            entity_id=item_id,
        )
        return {"ok": True}


@app.delete("/api/inventory/{item_id}")
def archive_inventory_item(item_id: int):
    with db() as conn:
        item = conn.execute(
            "SELECT * FROM inventory_items WHERE id=?",
            (item_id,),
        ).fetchone()
        if not item:
            raise HTTPException(404, "Producto no encontrado")
        linked = conn.execute(
            """SELECT COUNT(*) FROM task_supplies s
               JOIN tasks t ON t.id=s.task_id
               WHERE s.item_id=? AND t.active=1""",
            (item_id,),
        ).fetchone()[0]
        if linked:
            raise HTTPException(
                409,
                f"El producto está asociado a {linked} tarea(s) activa(s). Quítalo de esas tareas antes de archivarlo.",
            )
        conn.execute(
            "UPDATE inventory_items SET active=0,updated_at=? WHERE id=?",
            (iso_now(), item_id),
        )
        log_activity(
            conn,
            "inventory_archived",
            f'Archivado el producto "{item["name"]}"',
            entity_type="inventory",
            entity_id=item_id,
        )
        return {"ok": True}


@app.post("/api/inventory/{item_id}/restore")
def restore_inventory_item(item_id: int):
    with db() as conn:
        item = conn.execute(
            "SELECT * FROM inventory_items WHERE id=?",
            (item_id,),
        ).fetchone()
        if not item:
            raise HTTPException(404, "Producto no encontrado")
        conn.execute(
            "UPDATE inventory_items SET active=1,updated_at=? WHERE id=?",
            (iso_now(), item_id),
        )
        return {"ok": True}


@app.put("/api/inventory/{item_id}/gastos-product/{product_id}")
def link_inventory_to_gastos_product(item_id: int, product_id: int):
    product = gastos_proxy_call(f"/api/v1/products/{product_id}")
    with db() as conn:
        item = conn.execute(
            "SELECT * FROM inventory_items WHERE id=? AND active=1",
            (item_id,),
        ).fetchone()
        if not item:
            raise HTTPException(404, "Producto de inventario no encontrado")
        other = conn.execute(
            """SELECT id,name FROM inventory_items
               WHERE gastos_product_id=? AND id<>? AND active=1""",
            (product_id, item_id),
        ).fetchone()
        if other:
            raise HTTPException(
                409,
                f'Este producto de Gastos ya está vinculado a "{other["name"]}"',
            )
        conn.execute(
            "UPDATE inventory_items SET gastos_product_id=?,updated_at=? WHERE id=?",
            (product_id, iso_now(), item_id),
        )
        log_activity(
            conn,
            "inventory_gastos_linked",
            f'Vinculado "{item["name"]}" con Gastos: {product.get("name", product_id)}',
            entity_type="inventory",
            entity_id=item_id,
        )
    return {"ok": True, "product": product}


@app.delete("/api/inventory/{item_id}/gastos-product")
def unlink_inventory_from_gastos_product(item_id: int):
    with db() as conn:
        item = conn.execute(
            "SELECT * FROM inventory_items WHERE id=? AND active=1",
            (item_id,),
        ).fetchone()
        if not item:
            raise HTTPException(404, "Producto de inventario no encontrado")
        conn.execute(
            "UPDATE inventory_items SET gastos_product_id=NULL,updated_at=? WHERE id=?",
            (iso_now(), item_id),
        )
        log_activity(
            conn,
            "inventory_gastos_unlinked",
            f'Desvinculado "{item["name"]}" de Gastos',
            entity_type="inventory",
            entity_id=item_id,
        )
    return {"ok": True}


@app.post("/api/admin/reset-casa")
def reset_casa_database(payload: ResetIn):
    if payload.confirmation != "BORRAR TAREAS":
        raise HTTPException(400, "Confirmación incorrecta")
    with db() as conn:
        attachment_rows = conn.execute("SELECT * FROM attachments").fetchall()
        for row in attachment_rows:
            delete_attachment_file(row)

        for table in (
            "task_supplies",
            "today_queue",
            "schedule_overrides",
            "completions",
            "event_alert_ack",
            "notification_deliveries",
            "calendar_external_events",
            "calendar_subscriptions",
            "attachments",
            "events",
            "inventory_items",
            "tasks",
            "areas",
            "people",
            "undo_actions",
            "activity_log",
            "telegram_pending_actions",
        ):
            conn.execute(f"DELETE FROM {table}")

        conn.execute(
            """DELETE FROM sqlite_sequence WHERE name IN (
               'people','areas','tasks','events','telegram_pending_actions',
               'completions','schedule_overrides','undo_actions','activity_log',
               'attachments','calendar_subscriptions','calendar_external_events',
               'inventory_items'
            )"""
        )
        set_meta(conn, "sample_data_disabled", "1")
        delete_meta(conn, "shopping_task_id")
        delete_meta(conn, "vacation_state")
    return {"ok": True}


@app.post("/api/gastos/admin/reset")
def reset_gastos_database(payload: ResetIn):
    if payload.confirmation != "BORRAR GASTOS":
        raise HTTPException(400, "Confirmación incorrecta")
    result = gastos_proxy_call(
        "/api/v1/admin/reset",
        method="POST",
        payload={"confirmation": "BORRAR GASTOS"},
    )
    with db() as conn:
        conn.execute(
            """UPDATE inventory_items
               SET gastos_product_id=NULL,last_purchased_at=NULL,
                   last_purchase_ticket_id=NULL,updated_at=?""",
            (iso_now(),),
        )
        delete_meta(conn, "gastos_comida_sync_cursor_at")
        delete_meta(conn, "gastos_comida_sync_cursor_id")
        delete_meta(conn, "gastos_comida_sync_last_at")
        delete_meta(conn, "gastos_comida_sync_last_error")
        log_activity(
            conn,
            "gastos_reset",
            "Base de Gastos vaciada; vínculos de inventario eliminados",
            entity_type="settings",
        )
    return result


@app.post("/api/vacation/start")
def start_vacation(payload: VacationIn):
    target = validate_pause_payload(payload.return_date, payload.resume_mode)
    with db() as conn:
        sync_pause_states(conn)
        excluded = sorted({int(x) for x in payload.excluded_area_ids})
        if excluded:
            rows = conn.execute(
                "SELECT id FROM areas WHERE active=1"
            ).fetchall()
            valid = {r["id"] for r in rows}
            if any(area_id not in valid for area_id in excluded):
                raise HTTPException(400, "Hay un área excluida que no existe o está archivada")

        assert_vacation_can_start(conn, excluded)
        value = {
            "started_on": today_local().isoformat(),
            "return_date": target.isoformat(),
            "resume_mode": payload.resume_mode,
            "excluded_area_ids": excluded,
        }
        set_meta(conn, "vacation_state", json.dumps(value))
        log_activity(
            conn,
            "vacation_started",
            f'Modo vacaciones hasta {target.isoformat()}',
            detail="La Agenda continúa activa.",
            entity_type="vacation",
        )
        return {"ok": True, "vacation": get_vacation(conn)}


@app.post("/api/vacation/end")
def end_vacation():
    with db() as conn:
        sync_pause_states(conn)
        if not get_meta(conn, "vacation_state"):
            return {"ok": True, "already_inactive": True}
        finish_vacation(conn, today_local().isoformat())
        log_activity(
            conn,
            "vacation_ended",
            "Terminado el modo vacaciones",
            entity_type="vacation",
        )
        return {"ok": True, "already_inactive": False}


@app.post("/api/tasks/{task_id}/pause")
def pause_task(task_id: int, payload: PauseIn):
    target = validate_pause_payload(payload.return_date, payload.resume_mode)
    with db() as conn:
        sync_pause_states(conn)
        task = task_row(conn, task_id)
        if not task["active"]:
            raise HTTPException(400, "La tarea está archivada")
        assert_no_pause_overlap_for_task(conn, task)
        conn.execute(
            """UPDATE tasks SET pause_started_on=?,paused_until=?,
               pause_resume_mode=? WHERE id=?""",
            (
                today_local().isoformat(),
                target.isoformat(),
                payload.resume_mode,
                task_id,
            ),
        )
        return {"ok": True}


@app.post("/api/tasks/{task_id}/resume")
def resume_task(task_id: int):
    with db() as conn:
        sync_pause_states(conn)
        task = task_row(conn, task_id)
        if task["paused_until"]:
            finish_task_pause(conn, task_id, today_local().isoformat())
            return {"ok": True}
        pause = effective_task_pause(conn, task)
        if pause:
            raise HTTPException(
                409,
                "Esta tarea está pausada por su área o por el modo vacaciones; reanuda ese ámbito",
            )
        return {"ok": True, "already_active": True}


@app.post("/api/areas/{area_id}/pause")
def pause_area(area_id: int, payload: PauseIn):
    target = validate_pause_payload(payload.return_date, payload.resume_mode)
    with db() as conn:
        sync_pause_states(conn)
        area = conn.execute(
            "SELECT * FROM areas WHERE id=? AND active=1",
            (area_id,),
        ).fetchone()
        if not area:
            raise HTTPException(404, "Área no encontrada o archivada")
        assert_area_can_pause(conn, area)
        conn.execute(
            """UPDATE areas SET pause_started_on=?,paused_until=?,
               pause_resume_mode=? WHERE id=?""",
            (
                today_local().isoformat(),
                target.isoformat(),
                payload.resume_mode,
                area_id,
            ),
        )
        return {"ok": True}


@app.post("/api/areas/{area_id}/resume")
def resume_area(area_id: int):
    with db() as conn:
        sync_pause_states(conn)
        area = conn.execute("SELECT * FROM areas WHERE id=?", (area_id,)).fetchone()
        if not area:
            raise HTTPException(404, "Área no encontrada")
        if area["paused_until"]:
            finish_area_pause(conn, area_id, today_local().isoformat())
            return {"ok": True}
        pause = effective_area_pause(conn, area)
        if pause:
            raise HTTPException(
                409,
                "Esta área está pausada por el modo vacaciones; termínalo desde el Tablero",
            )
        return {"ok": True, "already_active": True}


@app.post("/api/tasks")
def create_task(payload: TaskIn):
    if payload.recurrence_type not in {"none", "cycle", "fixed"}:
        raise HTTPException(400, "Recurrencia no válida")
    if payload.task_type not in {"execution", "management"}:
        raise HTTPException(400, "Tipo de tarea no válido")
    due = payload.initial_due_date or today_local().isoformat()
    anchor = payload.anchor_date or due
    with db() as conn:
        validate_task_responsibility(conn, payload.area_id, payload.owner_person_id)
        supply_ids = validate_supply_ids(conn, payload.supply_ids)
        cur = conn.execute(
            """INSERT INTO tasks(title,description,category,color,icon,recurrence_type,
               frequency_days,initial_due_date,anchor_date,area_id,owner_person_id,
               task_type,definition_of_done,responsibility_notes,estimated_minutes,
               active,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)""",
            (
                payload.title.strip(),
                payload.description.strip(),
                payload.category.strip() or "General",
                payload.color,
                payload.icon,
                payload.recurrence_type,
                payload.frequency_days,
                due,
                anchor,
                payload.area_id,
                payload.owner_person_id,
                payload.task_type,
                payload.definition_of_done.strip(),
                payload.responsibility_notes.strip(),
                payload.estimated_minutes,
                iso_now(),
            ),
        )
        task_id = cur.lastrowid
        set_task_supplies(conn, task_id, supply_ids)
        log_activity(
            conn,
            "task_created",
            f'Creada la tarea "{payload.title.strip()}"',
            entity_type="task",
            entity_id=task_id,
        )
        return {"id": task_id}


@app.put("/api/tasks/{task_id}")
def update_task(task_id: int, payload: TaskIn):
    if payload.recurrence_type not in {"none", "cycle", "fixed"}:
        raise HTTPException(400, "Recurrencia no válida")
    if payload.task_type not in {"execution", "management"}:
        raise HTTPException(400, "Tipo de tarea no válido")
    with db() as conn:
        sync_pause_states(conn)
        task = task_row(conn, task_id)
        validate_task_responsibility(conn, payload.area_id, payload.owner_person_id)
        supply_ids = validate_supply_ids(conn, payload.supply_ids)
        if payload.area_id != task["area_id"]:
            if effective_task_pause(conn, task):
                raise HTTPException(
                    409,
                    "No se puede mover de área una tarea mientras está pausada",
                )
            destination_pause = pause_for_area_id(conn, payload.area_id)
            if destination_pause:
                raise HTTPException(
                    409,
                    f'El área de destino está pausada hasta {destination_pause["return_date"]}',
                )
        due = payload.initial_due_date or today_local().isoformat()
        anchor = payload.anchor_date or due
        conn.execute(
            """UPDATE tasks SET title=?,description=?,category=?,color=?,icon=?,
               recurrence_type=?,frequency_days=?,initial_due_date=?,anchor_date=?,
               area_id=?,owner_person_id=?,task_type=?,definition_of_done=?,
               responsibility_notes=?,estimated_minutes=? WHERE id=?""",
            (
                payload.title.strip(),
                payload.description.strip(),
                payload.category.strip() or "General",
                payload.color,
                payload.icon,
                payload.recurrence_type,
                payload.frequency_days,
                due,
                anchor,
                payload.area_id,
                payload.owner_person_id,
                payload.task_type,
                payload.definition_of_done.strip(),
                payload.responsibility_notes.strip(),
                payload.estimated_minutes,
                task_id,
            ),
        )
        set_task_supplies(conn, task_id, supply_ids)
        log_activity(
            conn,
            "task_updated",
            f'Actualizada la tarea "{payload.title.strip()}"',
            entity_type="task",
            entity_id=task_id,
        )
        return {"ok": True}


@app.put("/api/tasks/{task_id}/area")
def move_task_area(task_id: int, payload: AreaMoveIn):
    with db() as conn:
        sync_pause_states(conn)
        task = task_row(conn, task_id)
        if effective_task_pause(conn, task):
            raise HTTPException(409, "No se puede mover de área una tarea mientras está pausada")
        if payload.area_id is not None:
            area = conn.execute(
                "SELECT id FROM areas WHERE id=? AND active=1",
                (payload.area_id,),
            ).fetchone()
            if not area:
                raise HTTPException(400, "El área de destino no existe o está archivada")

        previous_area_id = task["area_id"]
        if previous_area_id == payload.area_id:
            return {"ok": True, "undo_id": None}

        destination_pause = pause_for_area_id(conn, payload.area_id)
        if destination_pause:
            raise HTTPException(
                409,
                f'El área de destino está pausada hasta {destination_pause["return_date"]}',
            )

        conn.execute(
            "UPDATE tasks SET area_id=? WHERE id=?",
            (payload.area_id, task_id),
        )
        undo_id = record_undo(
            conn,
            "move_task_area",
            {"task_id": task_id, "previous_area_id": previous_area_id},
            f'Movida de área "{task["title"]}"',
        )
        destination = (
            conn.execute("SELECT name FROM areas WHERE id=?", (payload.area_id,)).fetchone()
            if payload.area_id
            else None
        )
        log_activity(
            conn,
            "task_moved",
            f'Movida "{task["title"]}" a {destination["name"] if destination else "Sin área"}',
            entity_type="task",
            entity_id=task_id,
        )
        return {"ok": True, "undo_id": undo_id}


@app.delete("/api/tasks/{task_id}")
def archive_task(task_id: int):
    with db() as conn:
        task = task_row(conn, task_id)
        queue = conn.execute(
            "SELECT * FROM today_queue WHERE task_id=?", (task_id,)
        ).fetchone()
        conn.execute("UPDATE tasks SET active=0 WHERE id=?", (task_id,))
        conn.execute("DELETE FROM today_queue WHERE task_id=?", (task_id,))
        undo_id = record_undo(
            conn,
            "archive_task",
            {
                "task_id": task_id,
                "previous_active": task["active"],
                "queue": queue_snapshot(queue),
            },
            f'Archivada "{task["title"]}"',
        )
        return {"ok": True, "undo_id": undo_id}


@app.delete("/api/tasks/{task_id}/hard")
def delete_task_permanently(task_id: int):
    with db() as conn:
        task = task_row(conn, task_id)
        delete_attachments_for(conn, "task", task_id)
        conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        log_activity(
            conn,
            "task_deleted",
            f'Eliminada definitivamente la tarea "{task["title"]}"',
            entity_type="task",
            entity_id=task_id,
        )
        return {"ok": True}


@app.post("/api/today/reorder")
def reorder_today(payload: ReorderIn):
    with db() as conn:
        sync_pause_states(conn)
        queue_rows = conn.execute(
            """SELECT q.*,t.*
               FROM today_queue q
               JOIN tasks t ON t.id=q.task_id
               WHERE t.active=1
               ORDER BY q.position,q.task_id"""
        ).fetchall()
        visible_rows = [
            row for row in queue_rows if not effective_task_pause(conn, row)
        ]
        old_order = [row["task_id"] for row in visible_rows]
        old_positions = [
            {"task_id": row["task_id"], "position": row["position"]}
            for row in visible_rows
        ]
        if (
            len(payload.task_ids) != len(old_order)
            or len(set(payload.task_ids)) != len(payload.task_ids)
            or set(payload.task_ids) != set(old_order)
        ):
            raise HTTPException(400, "La lista de Hoy cambió; recarga e inténtalo de nuevo")
        if payload.task_ids == old_order:
            return {"ok": True, "undo_id": None}

        available_positions = sorted(row["position"] for row in visible_rows)
        for position, task_id in zip(available_positions, payload.task_ids):
            conn.execute(
                "UPDATE today_queue SET position=? WHERE task_id=?",
                (position, task_id),
            )
        undo_id = record_undo(
            conn,
            "reorder_today",
            {"old_order": old_order, "old_positions": old_positions},
            "Reordenada la cola de Hoy",
        )
        return {"ok": True, "undo_id": undo_id}


@app.post("/api/today/{task_id}")
def add_today(task_id: int):
    with db() as conn:
        sync_pause_states(conn)
        task = task_row(conn, task_id)
        if not task["active"]:
            raise HTTPException(400, "La tarea está archivada")
        assert_task_not_paused(conn, task)
        existing = conn.execute(
            "SELECT * FROM today_queue WHERE task_id=?", (task_id,)
        ).fetchone()
        if existing:
            # Idempotente: dos eventos drop nunca añaden dos tareas.
            return {"ok": True, "undo_id": None, "already_today": True}

        pos = conn.execute(
            "SELECT COALESCE(MAX(position),0)+1 FROM today_queue"
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO today_queue(task_id,position,forced,added_at) VALUES(?,?,1,?)",
            (task_id, pos, iso_now()),
        )
        undo_id = record_undo(
            conn,
            "add_today",
            {"task_id": task_id},
            f'Añadida a Hoy: "{task["title"]}"',
        )
        return {"ok": True, "undo_id": undo_id, "already_today": False}


@app.delete("/api/today/{task_id}")
def remove_today(task_id: int):
    with db() as conn:
        sync_pause_states(conn)
        task = task_row(conn, task_id)
        queue = conn.execute(
            "SELECT * FROM today_queue WHERE task_id=?",
            (task_id,),
        ).fetchone()
        if not queue:
            return {"ok": True, "undo_id": None, "already_removed": True}

        snapshot = queue_snapshot(queue)
        conn.execute("DELETE FROM today_queue WHERE task_id=?", (task_id,))
        undo_id = record_undo(
            conn,
            "remove_today",
            {"task_id": task_id, "queue": snapshot},
            f'Quitada de Hoy: "{task["title"]}"',
        )
        return {"ok": True, "undo_id": undo_id, "already_removed": False}


def postpone_task_action(conn, task_id, due_date_value):
    sync_pause_states(conn)
    try:
        date.fromisoformat(due_date_value)
    except ValueError:
        raise HTTPException(400, "Fecha no válida")

    task = task_row(conn, task_id)
    if not task["active"]:
        raise HTTPException(400, "La tarea está archivada")
    assert_task_not_paused(conn, task)
    queue = conn.execute(
        "SELECT * FROM today_queue WHERE task_id=?", (task_id,)
    ).fetchone()
    previous_override = conn.execute(
        """SELECT * FROM schedule_overrides
           WHERE task_id=? AND consumed_at IS NULL
           ORDER BY id DESC LIMIT 1""",
        (task_id,),
    ).fetchone()

    if previous_override:
        conn.execute(
            "UPDATE schedule_overrides SET consumed_at=? WHERE id=?",
            (iso_now(), previous_override["id"]),
        )
    cur = conn.execute(
        "INSERT INTO schedule_overrides(task_id,due_date,created_at) VALUES(?,?,?)",
        (task_id, due_date_value, iso_now()),
    )
    conn.execute("DELETE FROM today_queue WHERE task_id=?", (task_id,))
    undo_id = record_undo(
        conn,
        "postpone",
        {
            "task_id": task_id,
            "new_override_id": cur.lastrowid,
            "previous_override_id": previous_override["id"]
            if previous_override
            else None,
            "queue": queue_snapshot(queue),
        },
        f'Pospuesta "{task["title"]}"',
    )
    log_activity(
        conn,
        "task_postponed",
        f'Pospuesta "{task["title"]}" al {due_date_value}',
        entity_type="task",
        entity_id=task_id,
    )
    return {"ok": True, "undo_id": undo_id, "task_title": task["title"]}


def complete_task_action(conn, task_id, person_id):
    sync_pause_states(conn)
    task = task_row(conn, task_id)
    if not task["active"]:
        raise HTTPException(400, "La tarea está archivada")
    assert_task_not_paused(conn, task)
    person = conn.execute(
        "SELECT * FROM people WHERE id=? AND active=1", (person_id,)
    ).fetchone()
    if not person:
        raise HTTPException(400, "Persona no válida")

    queue = conn.execute(
        "SELECT * FROM today_queue WHERE task_id=?", (task_id,)
    ).fetchone()
    active_override = conn.execute(
        """SELECT * FROM schedule_overrides
           WHERE task_id=? AND consumed_at IS NULL
           ORDER BY id DESC LIMIT 1""",
        (task_id,),
    ).fetchone()

    cur = conn.execute(
        "INSERT INTO completions(task_id,person_id,completed_at) VALUES(?,?,?)",
        (task_id, person_id, iso_now()),
    )
    if active_override:
        conn.execute(
            "UPDATE schedule_overrides SET consumed_at=? WHERE id=?",
            (iso_now(), active_override["id"]),
        )
    conn.execute("DELETE FROM today_queue WHERE task_id=?", (task_id,))
    if task["recurrence_type"] == "none":
        conn.execute("UPDATE tasks SET active=0 WHERE id=?", (task_id,))

    undo_id = record_undo(
        conn,
        "complete",
        {
            "task_id": task_id,
            "completion_id": cur.lastrowid,
            "previous_active": task["active"],
            "active_override_id": active_override["id"]
            if active_override
            else None,
            "queue": queue_snapshot(queue),
        },
        f'Completada "{task["title"]}" por {person["name"]}',
    )
    log_activity(
        conn,
        "task_completed",
        f'{person["name"]} completó "{task["title"]}"',
        entity_type="task",
        entity_id=task_id,
    )
    return {
        "ok": True,
        "undo_id": undo_id,
        "task_title": task["title"],
        "person_name": person["name"],
    }


@app.post("/api/tasks/{task_id}/postpone")
def postpone(task_id: int, payload: PostponeIn):
    with db() as conn:
        return postpone_task_action(conn, task_id, payload.due_date)


@app.post("/api/tasks/{task_id}/complete")
def complete(task_id: int, payload: CompleteIn):
    with db() as conn:
        return complete_task_action(conn, task_id, payload.person_id)


@app.post("/api/areas")
def create_area(payload: AreaIn):
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "El nombre del área no puede estar vacío")
    with db() as conn:
        if payload.owner_person_id is not None:
            validate_task_responsibility(conn, None, payload.owner_person_id)
        existing = conn.execute("SELECT * FROM areas WHERE name=?", (name,)).fetchone()
        if existing:
            if existing["active"]:
                raise HTTPException(409, "Ya existe un área con ese nombre")
            conn.execute(
                """UPDATE areas SET active=1,description=?,color=?,icon=?,
                   owner_person_id=? WHERE id=?""",
                (
                    payload.description.strip(),
                    payload.color,
                    payload.icon,
                    payload.owner_person_id,
                    existing["id"],
                ),
            )
            log_activity(
                conn,
                "area_restored",
                f'Reactivada el área "{name}"',
                entity_type="area",
                entity_id=existing["id"],
            )
            return {"id": existing["id"], "reactivated": True}

        cur = conn.execute(
            """INSERT INTO areas(name,description,color,icon,owner_person_id)
               VALUES(?,?,?,?,?)""",
            (
                name,
                payload.description.strip(),
                payload.color,
                payload.icon,
                payload.owner_person_id,
            ),
        )
        area_id = cur.lastrowid
        log_activity(
            conn,
            "area_created",
            f'Creada el área "{name}"',
            entity_type="area",
            entity_id=area_id,
        )
        return {"id": area_id, "reactivated": False}


@app.put("/api/areas/{area_id}")
def update_area(area_id: int, payload: AreaIn):
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "El nombre del área no puede estar vacío")
    with db() as conn:
        area = conn.execute("SELECT * FROM areas WHERE id=?", (area_id,)).fetchone()
        if not area:
            raise HTTPException(404, "Área no encontrada")
        if payload.owner_person_id is not None:
            validate_task_responsibility(conn, None, payload.owner_person_id)
        try:
            conn.execute(
                """UPDATE areas SET name=?,description=?,color=?,icon=?,
                   owner_person_id=? WHERE id=?""",
                (
                    name,
                    payload.description.strip(),
                    payload.color,
                    payload.icon,
                    payload.owner_person_id,
                    area_id,
                ),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Ya existe un área con ese nombre")
        log_activity(
            conn,
            "area_updated",
            f'Actualizada el área "{name}"',
            entity_type="area",
            entity_id=area_id,
        )
        return {"ok": True}


@app.delete("/api/areas/{area_id}")
def archive_area(area_id: int):
    with db() as conn:
        area = conn.execute("SELECT * FROM areas WHERE id=?", (area_id,)).fetchone()
        if not area:
            raise HTTPException(404, "Área no encontrada")
        if not area["active"]:
            return {"ok": True, "undo_id": None}
        conn.execute("UPDATE areas SET active=0 WHERE id=?", (area_id,))
        undo_id = record_undo(
            conn,
            "area_active",
            {"area_id": area_id, "previous_active": 1},
            f'Archivada el área "{area["name"]}"',
        )
        log_activity(
            conn,
            "area_archived",
            f'Archivada el área "{area["name"]}"',
            entity_type="area",
            entity_id=area_id,
        )
        return {"ok": True, "undo_id": undo_id}


@app.delete("/api/areas/{area_id}/hard")
def delete_area_permanently(area_id: int):
    with db() as conn:
        area = conn.execute("SELECT * FROM areas WHERE id=?", (area_id,)).fetchone()
        if not area:
            raise HTTPException(404, "Área no encontrada")

        task_count = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE area_id=?",
            (area_id,),
        ).fetchone()[0]
        event_count = conn.execute(
            "SELECT COUNT(*) FROM events WHERE area_id=? AND active=1",
            (area_id,),
        ).fetchone()[0]
        attachment_count = conn.execute(
            "SELECT COUNT(*) FROM attachments WHERE entity_type='area' AND entity_id=?",
            (area_id,),
        ).fetchone()[0]
        if task_count or event_count or attachment_count:
            raise HTTPException(
                409,
                f"El área todavía tiene {task_count} tarea(s), {event_count} evento(s) y {attachment_count} documento(s). Muévelos o elimínalos antes de eliminarla.",
            )

        conn.execute("DELETE FROM areas WHERE id=?", (area_id,))
        log_activity(
            conn,
            "area_deleted",
            f'Eliminada definitivamente el área "{area["name"]}"',
            entity_type="area",
            entity_id=area_id,
        )
        return {"ok": True}


@app.post("/api/areas/{area_id}/restore")
def restore_area(area_id: int):
    with db() as conn:
        area = conn.execute("SELECT * FROM areas WHERE id=?", (area_id,)).fetchone()
        if not area:
            raise HTTPException(404, "Área no encontrada")
        if area["active"]:
            return {"ok": True, "undo_id": None}
        conn.execute("UPDATE areas SET active=1 WHERE id=?", (area_id,))
        undo_id = record_undo(
            conn,
            "area_active",
            {"area_id": area_id, "previous_active": 0},
            f'Reactivada el área "{area["name"]}"',
        )
        log_activity(
            conn,
            "area_restored",
            f'Reactivada el área "{area["name"]}"',
            entity_type="area",
            entity_id=area_id,
        )
        return {"ok": True, "undo_id": undo_id}


@app.post("/api/people")
def create_person(payload: PersonIn):
    name = payload.name.strip()
    gastos_user_name = (payload.gastos_user_name or "").strip() or None
    if not name:
        raise HTTPException(400, "El nombre no puede estar vacío")
    with db() as conn:
        if gastos_user_name:
            linked = conn.execute(
                "SELECT id,name FROM people WHERE gastos_user_name=?", (gastos_user_name,)
            ).fetchone()
            if linked:
                raise HTTPException(
                    409,
                    f'El usuario de Gastos "{gastos_user_name}" ya está vinculado con {linked["name"]}',
                )
        existing = conn.execute(
            "SELECT * FROM people WHERE name=?", (name,)
        ).fetchone()
        if existing:
            if existing["active"]:
                raise HTTPException(409, "Ya existe una persona con ese nombre")
            conn.execute(
                "UPDATE people SET active=1,color=?,icon=?,gastos_user_name=? WHERE id=?",
                (payload.color, payload.icon, gastos_user_name, existing["id"]),
            )
            return {"id": existing["id"], "reactivated": True}

        cur = conn.execute(
            "INSERT INTO people(name,color,icon,gastos_user_name) VALUES(?,?,?,?)",
            (name, payload.color, payload.icon, gastos_user_name),
        )
        return {"id": cur.lastrowid, "reactivated": False}


@app.put("/api/people/{person_id}")
def update_person(person_id: int, payload: PersonIn):
    name = payload.name.strip()
    gastos_user_name = (payload.gastos_user_name or "").strip() or None
    if not name:
        raise HTTPException(400, "El nombre no puede estar vacío")
    with db() as conn:
        person_row(conn, person_id)
        if gastos_user_name:
            linked = conn.execute(
                "SELECT id,name FROM people WHERE gastos_user_name=? AND id<>?",
                (gastos_user_name, person_id),
            ).fetchone()
            if linked:
                raise HTTPException(
                    409,
                    f'El usuario de Gastos "{gastos_user_name}" ya está vinculado con {linked["name"]}',
                )
        try:
            conn.execute(
                "UPDATE people SET name=?,color=?,icon=?,gastos_user_name=? WHERE id=?",
                (name, payload.color, payload.icon, gastos_user_name, person_id),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Ya existe una persona con ese nombre")
        return {"ok": True}


@app.delete("/api/people/{person_id}")
def delete_person(person_id: int):
    with db() as conn:
        person = person_row(conn, person_id)
        if not person["active"]:
            return {"ok": True, "undo_id": None}

        active_count = conn.execute(
            "SELECT COUNT(*) FROM people WHERE active=1"
        ).fetchone()[0]
        if active_count <= 1:
            raise HTTPException(400, "Debe quedar al menos una persona activa")

        conn.execute("UPDATE people SET active=0 WHERE id=?", (person_id,))
        undo_id = record_undo(
            conn,
            "person_active",
            {"person_id": person_id, "previous_active": 1},
            f'Eliminada la persona "{person["name"]}"',
        )
        return {"ok": True, "undo_id": undo_id}


@app.post("/api/people/{person_id}/restore")
def restore_person(person_id: int):
    with db() as conn:
        person = person_row(conn, person_id)
        if person["active"]:
            return {"ok": True, "undo_id": None}
        conn.execute("UPDATE people SET active=1 WHERE id=?", (person_id,))
        undo_id = record_undo(
            conn,
            "person_active",
            {"person_id": person_id, "previous_active": 0},
            f'Reactivada la persona "{person["name"]}"',
        )
        return {"ok": True, "undo_id": undo_id}


@app.post("/api/completions/{completion_id}/undo-to-today")
def undo_completion_to_today(completion_id: int):
    with db() as conn:
        completion = conn.execute(
            """SELECT c.*,t.title
               FROM completions c
               JOIN tasks t ON t.id=c.task_id
               WHERE c.id=?""",
            (completion_id,),
        ).fetchone()
        if not completion:
            raise HTTPException(404, "La realización ya no existe")

        later = conn.execute(
            """SELECT id FROM completions
               WHERE task_id=? AND id>? ORDER BY id DESC LIMIT 1""",
            (completion["task_id"], completion_id),
        ).fetchone()
        if later:
            raise HTTPException(
                409,
                "Hay una realización posterior de esta tarea. Deshaz primero la más reciente.",
            )

        undo_info = open_completion_undo_map(conn).get(completion_id)
        if not undo_info:
            raise HTTPException(
                409,
                "Esta realización ya no tiene información suficiente para deshacerse.",
            )
        payload = undo_info["payload"]
        if not payload.get("queue"):
            raise HTTPException(
                409,
                "Esta realización no procedía de la cola de Hoy.",
            )

        restore_completion_payload(conn, payload)
        conn.execute(
            "UPDATE undo_actions SET undone_at=? WHERE id=?",
            (iso_now(), undo_info["undo_id"]),
        )
        log_activity(
            conn,
            "completion_undone",
            f'Deshecha la realización de "{completion["title"]}"',
            detail="La tarea ha vuelto a Hoy.",
            entity_type="task",
            entity_id=completion["task_id"],
        )
        return {
            "ok": True,
            "task_id": completion["task_id"],
            "task_title": completion["title"],
        }


@app.post("/api/undo/{undo_id}")
def undo(undo_id: int):
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM undo_actions WHERE id=? AND undone_at IS NULL",
            (undo_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Esta acción ya no se puede deshacer")

        payload = json.loads(row["payload"])
        action = row["action_type"]

        if action == "add_today":
            conn.execute(
                "DELETE FROM today_queue WHERE task_id=?",
                (payload["task_id"],),
            )

        elif action == "remove_today":
            restore_queue_row(conn, payload.get("queue"))

        elif action == "reorder_today":
            if payload.get("old_positions"):
                for item in payload["old_positions"]:
                    conn.execute(
                        "UPDATE today_queue SET position=? WHERE task_id=?",
                        (item["position"], item["task_id"]),
                    )
            else:
                for pos, task_id in enumerate(payload["old_order"], start=1):
                    conn.execute(
                        "UPDATE today_queue SET position=? WHERE task_id=?",
                        (pos, task_id),
                    )

        elif action == "postpone":
            conn.execute(
                "DELETE FROM schedule_overrides WHERE id=?",
                (payload["new_override_id"],),
            )
            if payload.get("previous_override_id"):
                conn.execute(
                    "UPDATE schedule_overrides SET consumed_at=NULL WHERE id=?",
                    (payload["previous_override_id"],),
                )
            restore_queue_row(conn, payload.get("queue"))

        elif action == "complete":
            restore_completion_payload(conn, payload)

        elif action == "archive_task":
            conn.execute(
                "UPDATE tasks SET active=? WHERE id=?",
                (payload["previous_active"], payload["task_id"]),
            )
            restore_queue_row(conn, payload.get("queue"))

        elif action == "person_active":
            conn.execute(
                "UPDATE people SET active=? WHERE id=?",
                (payload["previous_active"], payload["person_id"]),
            )

        elif action == "area_active":
            conn.execute(
                "UPDATE areas SET active=? WHERE id=?",
                (payload["previous_active"], payload["area_id"]),
            )

        elif action == "move_task_area":
            conn.execute(
                "UPDATE tasks SET area_id=? WHERE id=?",
                (payload.get("previous_area_id"), payload["task_id"]),
            )

        elif action == "rename_task":
            conn.execute(
                "UPDATE tasks SET title=? WHERE id=?",
                (payload["previous_title"], payload["task_id"]),
            )

        elif action == "create_task":
            completion_count = conn.execute(
                "SELECT COUNT(*) FROM completions WHERE task_id=?",
                (payload["task_id"],),
            ).fetchone()[0]
            if completion_count:
                raise HTTPException(
                    409,
                    "No se puede deshacer la creación porque la tarea ya tiene historial",
                )
            conn.execute("DELETE FROM tasks WHERE id=?", (payload["task_id"],))

        elif action == "create_event":
            conn.execute("DELETE FROM events WHERE id=?", (payload["event_id"],))

        else:
            raise HTTPException(400, "Tipo de deshacer no soportado")

        conn.execute(
            "UPDATE undo_actions SET undone_at=? WHERE id=?",
            (iso_now(), undo_id),
        )
        return {"ok": True, "undone": row["label"]}

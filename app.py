from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("APP_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "chores.db"
TZ = ZoneInfo(os.getenv("APP_TIMEZONE", "Europe/Zurich"))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_POLL_SECONDS = max(30, int(os.getenv("TELEGRAM_POLL_SECONDS", "60") or "60"))
TELEGRAM_TASK = None

app = FastAPI(title="Casa Tareas", version="0.7.0")
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
          active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS areas(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL UNIQUE,
          description TEXT NOT NULL DEFAULT '',
          color TEXT NOT NULL DEFAULT '#e7eefb',
          icon TEXT NOT NULL DEFAULT '🏠',
          owner_person_id INTEGER,
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
        """)

        # Migraciones aditivas para bases creadas por versiones anteriores.
        ensure_column(conn, "tasks", "area_id", "INTEGER REFERENCES areas(id) ON DELETE SET NULL")
        ensure_column(conn, "tasks", "owner_person_id", "INTEGER REFERENCES people(id) ON DELETE SET NULL")
        ensure_column(conn, "tasks", "task_type", "TEXT NOT NULL DEFAULT 'execution'")
        ensure_column(conn, "tasks", "definition_of_done", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "tasks", "responsibility_notes", "TEXT NOT NULL DEFAULT ''")

        if conn.execute("SELECT COUNT(*) FROM people").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO people(name,color,icon) VALUES(?,?,?)",
                [
                    ("Cosi", "#f7c8b6", "👩"),
                    ("Jose", "#b8d8ff", "👨"),
                    ("Li", "#d8c6ff", "👩‍🦰"),
                ],
            )

        if conn.execute("SELECT COUNT(*) FROM areas").fetchone()[0] == 0:
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

        if conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0:
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
        if not household_v4:
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


def telegram_status(conn):
    chat_id = get_meta(conn, "telegram_chat_id")
    return {
        "token_configured": bool(TELEGRAM_BOT_TOKEN),
        "chat_id": int(chat_id) if chat_id else None,
        "chat_title": get_meta(conn, "telegram_chat_title", ""),
        "bot_username": get_meta(conn, "telegram_bot_username", ""),
        "commands_enabled": bool(chat_id and TELEGRAM_BOT_TOKEN),
        "poll_seconds": TELEGRAM_POLL_SECONDS,
    }


def telegram_api_request(method, payload=None):
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Falta TELEGRAM_BOT_TOKEN en la configuración del contenedor")
    payload = payload or {}
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
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
    if not TELEGRAM_BOT_TOKEN:
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
    matches = telegram_find_task(conn, query)
    if not matches:
        raise ValueError(f'No encuentro una tarea activa que coincida con "{query}".')
    if len(matches) > 1:
        choices = "\n".join(f'• #{r["id"]} {r["title"]}' for r in matches)
        raise ValueError(
            "Hay varias tareas que coinciden. Usa el título completo o el #id:\n" + choices
        )
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


def telegram_help_text():
    return (
        "🏠 Casa Tareas · comandos\n\n"
        "/hoy — tareas y eventos de hoy\n"
        "/agenda — próximos eventos\n"
        "/pendientes [Área] — tareas activas\n"
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
            "ayuda": "/ayuda",
        }
        command = aliases.get(sub.casefold(), "/" + sub.casefold())
        args = sub_args.strip()

    if command in {"/start", "/ayuda", "/help"}:
        telegram_send_message(chat_id, telegram_help_text())
        return

    with db() as conn:
        if command == "/hoy":
            task_rows = conn.execute(
                """SELECT t.id,t.title FROM today_queue q
                   JOIN tasks t ON t.id=q.task_id
                   WHERE t.active=1 ORDER BY q.position,q.task_id"""
            ).fetchall()
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
            rows = conn.execute(
                "SELECT * FROM tasks WHERE active=1 ORDER BY title COLLATE NOCASE,id"
            ).fetchall()
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
    if not TELEGRAM_BOT_TOKEN:
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


def ensure_telegram_bot_identity():
    info = telegram_api_request("getMe")
    bot_id = str(info.get("id"))
    username = info.get("username", "")
    with db() as conn:
        previous = get_meta(conn, "telegram_bot_id")
        if previous and previous != bot_id:
            delete_meta(conn, "telegram_update_offset")
            conn.execute("DELETE FROM telegram_chats_seen")
            delete_meta(conn, "telegram_chat_id")
            delete_meta(conn, "telegram_chat_title")
        set_meta(conn, "telegram_bot_id", bot_id)
        set_meta(conn, "telegram_bot_username", username)

    commands = [
        {"command": "hoy", "description": "Tareas y eventos de hoy"},
        {"command": "agenda", "description": "Próximos eventos"},
        {"command": "pendientes", "description": "Tareas activas"},
        {"command": "tarea", "description": "Crear una tarea"},
        {"command": "hecha", "description": "Marcar una tarea como hecha"},
        {"command": "mover", "description": "Mover una tarea de área"},
        {"command": "posponer", "description": "Posponer una tarea"},
        {"command": "evento", "description": "Crear un evento"},
        {"command": "deshacer", "description": "Deshacer el último cambio del bot"},
        {"command": "ayuda", "description": "Ver ejemplos de comandos"},
    ]
    telegram_api_request(
        "setMyCommands",
        {"commands": json.dumps(commands, ensure_ascii=False)},
    )
    return info


async def telegram_reminder_loop():
    identity_ready = False
    last_reminder_check = 0.0
    while True:
        try:
            if not identity_ready:
                await asyncio.to_thread(ensure_telegram_bot_identity)
                identity_ready = True

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


def task_json(conn, task):
    d = dict(task)
    d["active"] = bool(d["active"])
    due = due_date(conn, task)
    d["next_due"] = due.isoformat() if due else None

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


@app.on_event("startup")
async def startup():
    global TELEGRAM_TASK
    init_db()
    if TELEGRAM_BOT_TOKEN:
        TELEGRAM_TASK = asyncio.create_task(telegram_reminder_loop())


@app.on_event("shutdown")
async def shutdown():
    global TELEGRAM_TASK
    if TELEGRAM_TASK:
        TELEGRAM_TASK.cancel()
        try:
            await TELEGRAM_TASK
        except asyncio.CancelledError:
            pass
        TELEGRAM_TASK = None


@app.get("/")
def root():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "version": "0.7.0"}


@app.get("/api/state")
def state():
    with db() as conn:
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
        events = [
            event_json(conn, r)
            for r in conn.execute(
                "SELECT * FROM events WHERE active=1 ORDER BY event_at,id"
            ).fetchall()
        ]
        event_today = []
        event_upcoming = []
        today = today_local()
        for event in events:
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
        today = [by_id[i] for i in today_ids if i in by_id and by_id[i]["active"]]
        today_set = set(today_ids)
        upcoming = sorted(
            [
                t
                for t in tasks
                if t["active"] and t["next_due"] and t["id"] not in today_set
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
        history = [dict(r) for r in history_rows]
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
        return {
            "people": people,
            "people_all": people_all,
            "areas": areas,
            "areas_all": areas_all,
            "today": today,
            "upcoming": upcoming,
            "tasks": tasks,
            "events": events,
            "event_today": event_today,
            "event_upcoming": event_upcoming,
            "alerts_due": alerts_due,
            "telegram": telegram_status(conn),
            "history": history,
            "stats": stats,
            "last_undo": latest_undo(conn),
        }


@app.get("/api/telegram/status")
def get_telegram_status():
    with db() as conn:
        return telegram_status(conn)


@app.post("/api/telegram/chats")
def detect_telegram_chats():
    if not TELEGRAM_BOT_TOKEN:
        raise HTTPException(400, "Configura TELEGRAM_BOT_TOKEN y reinicia el contenedor")
    try:
        return {"chats": telegram_detect_chats()}
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))


@app.put("/api/telegram/chat")
def configure_telegram_chat(payload: TelegramChatIn):
    if not TELEGRAM_BOT_TOKEN:
        raise HTTPException(400, "Configura TELEGRAM_BOT_TOKEN y reinicia el contenedor")
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
    return {"ok": True, "chat_id": payload.chat_id, "chat_title": title}


@app.delete("/api/telegram/chat")
def disconnect_telegram_chat():
    with db() as conn:
        delete_meta(conn, "telegram_chat_id")
        delete_meta(conn, "telegram_chat_title")
    return {"ok": True}


@app.post("/api/telegram/test")
def test_telegram():
    if not TELEGRAM_BOT_TOKEN:
        raise HTTPException(400, "Configura TELEGRAM_BOT_TOKEN y reinicia el contenedor")
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
    return {"ok": True, "chat_title": title}


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
        return {"id": cur.lastrowid}


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
        return {"ok": True}


@app.delete("/api/events/{event_id}")
def delete_event(event_id: int):
    with db() as conn:
        event = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        if not event:
            raise HTTPException(404, "Evento no encontrado")
        conn.execute("DELETE FROM events WHERE id=?", (event_id,))
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
        cur = conn.execute(
            """INSERT INTO tasks(title,description,category,color,icon,recurrence_type,
               frequency_days,initial_due_date,anchor_date,area_id,owner_person_id,
               task_type,definition_of_done,responsibility_notes,active,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)""",
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
                iso_now(),
            ),
        )
        return {"id": cur.lastrowid}


@app.put("/api/tasks/{task_id}")
def update_task(task_id: int, payload: TaskIn):
    if payload.recurrence_type not in {"none", "cycle", "fixed"}:
        raise HTTPException(400, "Recurrencia no válida")
    if payload.task_type not in {"execution", "management"}:
        raise HTTPException(400, "Tipo de tarea no válido")
    with db() as conn:
        task_row(conn, task_id)
        validate_task_responsibility(conn, payload.area_id, payload.owner_person_id)
        due = payload.initial_due_date or today_local().isoformat()
        anchor = payload.anchor_date or due
        conn.execute(
            """UPDATE tasks SET title=?,description=?,category=?,color=?,icon=?,
               recurrence_type=?,frequency_days=?,initial_due_date=?,anchor_date=?,
               area_id=?,owner_person_id=?,task_type=?,definition_of_done=?,
               responsibility_notes=? WHERE id=?""",
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
                task_id,
            ),
        )
        return {"ok": True}


@app.put("/api/tasks/{task_id}/area")
def move_task_area(task_id: int, payload: AreaMoveIn):
    with db() as conn:
        task = task_row(conn, task_id)
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
        task_row(conn, task_id)
        conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        return {"ok": True}


@app.post("/api/today/reorder")
def reorder_today(payload: ReorderIn):
    with db() as conn:
        old_order = [
            r["task_id"]
            for r in conn.execute(
                "SELECT task_id FROM today_queue ORDER BY position,task_id"
            ).fetchall()
        ]
        if (
            len(payload.task_ids) != len(old_order)
            or len(set(payload.task_ids)) != len(payload.task_ids)
            or set(payload.task_ids) != set(old_order)
        ):
            raise HTTPException(400, "La lista de Hoy cambió; recarga e inténtalo de nuevo")
        if payload.task_ids == old_order:
            return {"ok": True, "undo_id": None}

        for pos, task_id in enumerate(payload.task_ids, start=1):
            conn.execute(
                "UPDATE today_queue SET position=? WHERE task_id=?",
                (pos, task_id),
            )
        undo_id = record_undo(
            conn,
            "reorder_today",
            {"old_order": old_order},
            "Reordenada la cola de Hoy",
        )
        return {"ok": True, "undo_id": undo_id}


@app.post("/api/today/{task_id}")
def add_today(task_id: int):
    with db() as conn:
        task = task_row(conn, task_id)
        if not task["active"]:
            raise HTTPException(400, "La tarea está archivada")
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




def postpone_task_action(conn, task_id, due_date_value):
    try:
        date.fromisoformat(due_date_value)
    except ValueError:
        raise HTTPException(400, "Fecha no válida")

    task = task_row(conn, task_id)
    if not task["active"]:
        raise HTTPException(400, "La tarea está archivada")
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
    return {"ok": True, "undo_id": undo_id, "task_title": task["title"]}


def complete_task_action(conn, task_id, person_id):
    task = task_row(conn, task_id)
    if not task["active"]:
        raise HTTPException(400, "La tarea está archivada")
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
        return {"id": cur.lastrowid, "reactivated": False}


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
        if task_count or event_count:
            raise HTTPException(
                409,
                f"El área todavía tiene {task_count} tarea(s) y {event_count} evento(s) asociado(s). Muévelos antes de eliminarla.",
            )

        conn.execute("DELETE FROM areas WHERE id=?", (area_id,))
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
        return {"ok": True, "undo_id": undo_id}


@app.post("/api/people")
def create_person(payload: PersonIn):
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "El nombre no puede estar vacío")
    with db() as conn:
        existing = conn.execute(
            "SELECT * FROM people WHERE name=?", (name,)
        ).fetchone()
        if existing:
            if existing["active"]:
                raise HTTPException(409, "Ya existe una persona con ese nombre")
            conn.execute(
                "UPDATE people SET active=1,color=?,icon=? WHERE id=?",
                (payload.color, payload.icon, existing["id"]),
            )
            return {"id": existing["id"], "reactivated": True}

        cur = conn.execute(
            "INSERT INTO people(name,color,icon) VALUES(?,?,?)",
            (name, payload.color, payload.icon),
        )
        return {"id": cur.lastrowid, "reactivated": False}


@app.put("/api/people/{person_id}")
def update_person(person_id: int, payload: PersonIn):
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "El nombre no puede estar vacío")
    with db() as conn:
        person_row(conn, person_id)
        try:
            conn.execute(
                "UPDATE people SET name=?,color=?,icon=? WHERE id=?",
                (name, payload.color, payload.icon, person_id),
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

        elif action == "reorder_today":
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
            conn.execute(
                "DELETE FROM completions WHERE id=?",
                (payload["completion_id"],),
            )
            conn.execute(
                "UPDATE tasks SET active=? WHERE id=?",
                (payload["previous_active"], payload["task_id"]),
            )
            if payload.get("active_override_id"):
                conn.execute(
                    "UPDATE schedule_overrides SET consumed_at=NULL WHERE id=?",
                    (payload["active_override_id"],),
                )
            restore_queue_row(conn, payload.get("queue"))

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

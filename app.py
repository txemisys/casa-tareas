from __future__ import annotations

import json
import os
import sqlite3
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

app = FastAPI(title="Casa Tareas", version="0.2.0")
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
                    ("Ana", "#f7c8b6", "👩"),
                    ("Juan", "#b8d8ff", "👨"),
                    ("Lucía", "#d8c6ff", "👩‍🦰"),
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
    return d


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
def startup():
    init_db()


@app.get("/")
def root():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "version": "0.3.0"}


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
            "history": history,
            "stats": stats,
            "last_undo": latest_undo(conn),
        }


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




@app.post("/api/tasks/{task_id}/postpone")
def postpone(task_id: int, payload: PostponeIn):
    try:
        date.fromisoformat(payload.due_date)
    except ValueError:
        raise HTTPException(400, "Fecha no válida")

    with db() as conn:
        task = task_row(conn, task_id)
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
            (task_id, payload.due_date, iso_now()),
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
        return {"ok": True, "undo_id": undo_id}


@app.post("/api/tasks/{task_id}/complete")
def complete(task_id: int, payload: CompleteIn):
    with db() as conn:
        task = task_row(conn, task_id)
        person = conn.execute(
            "SELECT * FROM people WHERE id=? AND active=1", (payload.person_id,)
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
            (task_id, payload.person_id, iso_now()),
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
        return {"ok": True, "undo_id": undo_id}


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
        if task_count:
            raise HTTPException(
                409,
                f"El área todavía tiene {task_count} tarea(s) asociada(s). Muévelas a otra área antes de eliminarla.",
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

        else:
            raise HTTPException(400, "Tipo de deshacer no soportado")

        conn.execute(
            "UPDATE undo_actions SET undone_at=? WHERE id=?",
            (iso_now(), undo_id),
        )
        return {"ok": True, "undone": row["label"]}

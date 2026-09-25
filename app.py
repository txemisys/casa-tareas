from __future__ import annotations

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

app = FastAPI(title="Casa Tareas", version="0.1.0")
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
          active INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL
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
          forced INTEGER NOT NULL DEFAULT 0,
          added_at TEXT NOT NULL,
          FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_completions_task ON completions(task_id, completed_at DESC);
        """)

        if conn.execute("SELECT COUNT(*) FROM people").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO people(name,color,icon) VALUES(?,?,?)",
                [
                    ("Ana", "#f7c8b6", "👩"),
                    ("Juan", "#b8d8ff", "👨"),
                    ("Lucía", "#d8c6ff", "👩‍🦰"),
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


def task_row(conn, task_id):
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Tarea no encontrada")
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
    current = {r["task_id"]: r for r in conn.execute("SELECT * FROM today_queue").fetchall()}
    max_pos = conn.execute("SELECT COALESCE(MAX(position),0) FROM today_queue").fetchone()[0]
    for task in conn.execute("SELECT * FROM tasks WHERE active=1 ORDER BY id").fetchall():
        due = due_date(conn, task)
        q = current.get(task["id"])
        should_be_here = due is not None and due <= today_local()
        if should_be_here and not q:
            max_pos += 1
            conn.execute(
                "INSERT INTO today_queue(task_id,position,forced,added_at) VALUES(?,?,0,?)",
                (task["id"], max_pos, iso_now()),
            )
        elif not should_be_here and q and not q["forced"]:
            conn.execute("DELETE FROM today_queue WHERE task_id=?", (task["id"],))


def task_json(conn, task):
    d = dict(task)
    d["active"] = bool(d["active"])
    due = due_date(conn, task)
    d["next_due"] = due.isoformat() if due else None
    last = last_completion(conn, task["id"])
    if last:
        p = conn.execute("SELECT id,name,color,icon FROM people WHERE id=?", (last["person_id"],)).fetchone()
        d["last_completion"] = {"completed_at": last["completed_at"], "person": dict(p)}
    else:
        d["last_completion"] = None
    return d


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


@app.get("/api/state")
def state():
    with db() as conn:
        sync_today(conn)
        people = [dict(r) for r in conn.execute("SELECT * FROM people WHERE active=1 ORDER BY id").fetchall()]
        tasks = [task_json(conn, r) for r in conn.execute("SELECT * FROM tasks ORDER BY active DESC,category,title").fetchall()]
        today_ids = [r["task_id"] for r in conn.execute("SELECT * FROM today_queue ORDER BY position,task_id").fetchall()]
        by_id = {t["id"]: t for t in tasks}
        today = [by_id[i] for i in today_ids if i in by_id and by_id[i]["active"]]
        today_set = set(today_ids)
        upcoming = sorted(
            [t for t in tasks if t["active"] and t["next_due"] and t["id"] not in today_set],
            key=lambda t: t["next_due"],
        )
        history_rows = conn.execute(
            """SELECT c.id,c.completed_at,t.id task_id,t.title,t.icon,p.id person_id,p.name,p.color,p.icon person_icon
               FROM completions c JOIN tasks t ON t.id=c.task_id JOIN people p ON p.id=c.person_id
               ORDER BY c.completed_at DESC,c.id DESC LIMIT 200"""
        ).fetchall()
        history = [dict(r) for r in history_rows]
        cutoff = (now_local() - timedelta(days=30)).isoformat()
        stats = [dict(r) for r in conn.execute(
            """SELECT p.id,p.name,p.color,p.icon,COUNT(c.id) count
               FROM people p LEFT JOIN completions c ON c.person_id=p.id AND c.completed_at>=?
               WHERE p.active=1 GROUP BY p.id ORDER BY p.id""",
            (cutoff,),
        ).fetchall()]
        return {"people":people,"today":today,"upcoming":upcoming,"tasks":tasks,"history":history,"stats":stats}


@app.post("/api/tasks")
def create_task(payload: TaskIn):
    if payload.recurrence_type not in {"none","cycle","fixed"}:
        raise HTTPException(400, "Recurrencia no válida")
    due = payload.initial_due_date or today_local().isoformat()
    anchor = payload.anchor_date or due
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO tasks(title,description,category,color,icon,recurrence_type,
               frequency_days,initial_due_date,anchor_date,active,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,1,?)""",
            (payload.title.strip(),payload.description.strip(),payload.category.strip() or "General",
             payload.color,payload.icon,payload.recurrence_type,payload.frequency_days,due,anchor,iso_now()),
        )
        return {"id":cur.lastrowid}


@app.put("/api/tasks/{task_id}")
def update_task(task_id: int, payload: TaskIn):
    with db() as conn:
        task_row(conn, task_id)
        due = payload.initial_due_date or today_local().isoformat()
        anchor = payload.anchor_date or due
        conn.execute(
            """UPDATE tasks SET title=?,description=?,category=?,color=?,icon=?,recurrence_type=?,
               frequency_days=?,initial_due_date=?,anchor_date=? WHERE id=?""",
            (payload.title.strip(),payload.description.strip(),payload.category.strip() or "General",
             payload.color,payload.icon,payload.recurrence_type,payload.frequency_days,due,anchor,task_id),
        )
        sync_today(conn)
        return {"ok":True}


@app.delete("/api/tasks/{task_id}")
def archive_task(task_id: int):
    with db() as conn:
        task_row(conn, task_id)
        conn.execute("UPDATE tasks SET active=0 WHERE id=?", (task_id,))
        conn.execute("DELETE FROM today_queue WHERE task_id=?", (task_id,))
        return {"ok":True}


@app.post("/api/today/{task_id}")
def add_today(task_id: int):
    with db() as conn:
        task = task_row(conn, task_id)
        if not task["active"]:
            raise HTTPException(400, "La tarea está archivada")
        pos = conn.execute("SELECT COALESCE(MAX(position),0)+1 FROM today_queue").fetchone()[0]
        conn.execute(
            """INSERT INTO today_queue(task_id,position,forced,added_at) VALUES(?,?,1,?)
               ON CONFLICT(task_id) DO UPDATE SET forced=1""",
            (task_id,pos,iso_now()),
        )
        return {"ok":True}


@app.post("/api/today/reorder")
def reorder_today(payload: ReorderIn):
    with db() as conn:
        for pos, task_id in enumerate(payload.task_ids, start=1):
            conn.execute("UPDATE today_queue SET position=? WHERE task_id=?", (pos,task_id))
        return {"ok":True}


@app.post("/api/tasks/{task_id}/postpone")
def postpone(task_id: int, payload: PostponeIn):
    try:
        date.fromisoformat(payload.due_date)
    except ValueError:
        raise HTTPException(400, "Fecha no válida")
    with db() as conn:
        task_row(conn, task_id)
        conn.execute("UPDATE schedule_overrides SET consumed_at=? WHERE task_id=? AND consumed_at IS NULL", (iso_now(),task_id))
        conn.execute(
            "INSERT INTO schedule_overrides(task_id,due_date,created_at) VALUES(?,?,?)",
            (task_id,payload.due_date,iso_now()),
        )
        conn.execute("DELETE FROM today_queue WHERE task_id=?", (task_id,))
        return {"ok":True}


@app.post("/api/tasks/{task_id}/complete")
def complete(task_id: int, payload: CompleteIn):
    with db() as conn:
        task = task_row(conn, task_id)
        person = conn.execute("SELECT * FROM people WHERE id=? AND active=1", (payload.person_id,)).fetchone()
        if not person:
            raise HTTPException(400, "Persona no válida")
        conn.execute(
            "INSERT INTO completions(task_id,person_id,completed_at) VALUES(?,?,?)",
            (task_id,payload.person_id,iso_now()),
        )
        conn.execute("UPDATE schedule_overrides SET consumed_at=? WHERE task_id=? AND consumed_at IS NULL", (iso_now(),task_id))
        conn.execute("DELETE FROM today_queue WHERE task_id=?", (task_id,))
        if task["recurrence_type"] == "none":
            conn.execute("UPDATE tasks SET active=0 WHERE id=?", (task_id,))
        sync_today(conn)
        return {"ok":True}


@app.post("/api/people")
def create_person(payload: PersonIn):
    with db() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO people(name,color,icon) VALUES(?,?,?)",
                (payload.name.strip(),payload.color,payload.icon),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Ya existe una persona con ese nombre")
        return {"id":cur.lastrowid}

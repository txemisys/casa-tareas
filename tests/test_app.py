import json
from datetime import date, datetime, timedelta


def get_state(client):
    response = client.get("/api/state")
    assert response.status_code == 200
    return response.json()


def task_payload(**overrides):
    data = {
        "title": "Tarea de prueba",
        "description": "Descripción",
        "category": "Pruebas",
        "color": "#dcecff",
        "icon": "🧪",
        "recurrence_type": "cycle",
        "frequency_days": 7,
        "initial_due_date": date.today().isoformat(),
        "anchor_date": date.today().isoformat(),
    }
    data.update(overrides)
    return data


def task_from_state(state, task_id):
    return next(task for task in state["tasks"] if task["id"] == task_id)


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_add_one_task_to_today_is_idempotent_and_undoable(client):
    initial = get_state(client)
    assert initial["today"] == []

    task_id = initial["upcoming"][0]["id"]

    first = client.post(f"/api/today/{task_id}")
    assert first.status_code == 200
    first_data = first.json()
    assert first_data["already_today"] is False
    assert first_data["undo_id"] is not None

    after_first = get_state(client)
    assert [task["id"] for task in after_first["today"]] == [task_id]

    second = client.post(f"/api/today/{task_id}")
    assert second.status_code == 200
    assert second.json()["already_today"] is True
    assert second.json()["undo_id"] is None

    after_second = get_state(client)
    assert [task["id"] for task in after_second["today"]] == [task_id]

    undo = client.post(f"/api/undo/{first_data['undo_id']}")
    assert undo.status_code == 200
    assert get_state(client)["today"] == []


def test_reorder_today_and_undo(client):
    initial = get_state(client)
    first_id = initial["upcoming"][0]["id"]
    second_id = initial["upcoming"][1]["id"]

    assert client.post(f"/api/today/{first_id}").status_code == 200
    assert client.post(f"/api/today/{second_id}").status_code == 200
    assert [t["id"] for t in get_state(client)["today"]] == [first_id, second_id]

    reordered = client.post(
        "/api/today/reorder",
        json={"task_ids": [second_id, first_id]},
    )
    assert reordered.status_code == 200
    undo_id = reordered.json()["undo_id"]
    assert undo_id is not None
    assert [t["id"] for t in get_state(client)["today"]] == [second_id, first_id]

    undo = client.post(f"/api/undo/{undo_id}")
    assert undo.status_code == 200
    assert [t["id"] for t in get_state(client)["today"]] == [first_id, second_id]


def test_reorder_rejects_incomplete_or_duplicate_queue(client):
    initial = get_state(client)
    ids = [initial["upcoming"][0]["id"], initial["upcoming"][1]["id"]]
    for task_id in ids:
        assert client.post(f"/api/today/{task_id}").status_code == 200

    missing = client.post("/api/today/reorder", json={"task_ids": [ids[0]]})
    assert missing.status_code == 400

    duplicate = client.post(
        "/api/today/reorder",
        json={"task_ids": [ids[0], ids[0]]},
    )
    assert duplicate.status_code == 400

    assert [t["id"] for t in get_state(client)["today"]] == ids


def test_cycle_completion_moves_next_due_and_undo_restores(client):
    state = get_state(client)
    task = next(t for t in state["tasks"] if t["active"] and t["recurrence_type"] == "cycle")
    person = state["people"][0]

    assert client.post(f"/api/today/{task['id']}").status_code == 200
    completed = client.post(
        f"/api/tasks/{task['id']}/complete",
        json={"person_id": person["id"]},
    )
    assert completed.status_code == 200
    undo_id = completed.json()["undo_id"]

    after = get_state(client)
    assert all(t["id"] != task["id"] for t in after["today"])
    assert after["history"][0]["task_id"] == task["id"]
    assert after["history"][0]["person_id"] == person["id"]

    completed_day = datetime.fromisoformat(after["history"][0]["completed_at"]).date()
    expected_due = completed_day + timedelta(days=task["frequency_days"])
    updated = task_from_state(after, task["id"])
    assert updated["next_due"] == expected_due.isoformat()

    undo = client.post(f"/api/undo/{undo_id}")
    assert undo.status_code == 200

    restored = get_state(client)
    assert restored["history"] == []
    assert [t["id"] for t in restored["today"]] == [task["id"]]


def test_fixed_schedule_is_not_shifted_by_early_completion(client):
    anchor = date.today() + timedelta(days=10)
    created = client.post(
        "/api/tasks",
        json=task_payload(
            title="Calendario fijo",
            recurrence_type="fixed",
            frequency_days=7,
            initial_due_date=anchor.isoformat(),
            anchor_date=anchor.isoformat(),
        ),
    )
    assert created.status_code == 200
    task_id = created.json()["id"]

    state = get_state(client)
    person_id = state["people"][0]["id"]

    assert client.post(f"/api/today/{task_id}").status_code == 200
    completed = client.post(
        f"/api/tasks/{task_id}/complete",
        json={"person_id": person_id},
    )
    assert completed.status_code == 200

    after = get_state(client)
    task = task_from_state(after, task_id)
    assert task["next_due"] == anchor.isoformat()


def test_one_off_task_archives_on_completion_and_undo_reactivates(client):
    created = client.post(
        "/api/tasks",
        json=task_payload(
            title="Puntual",
            recurrence_type="none",
            frequency_days=None,
        ),
    )
    assert created.status_code == 200
    task_id = created.json()["id"]

    state = get_state(client)
    person_id = state["people"][0]["id"]
    assert client.post(f"/api/today/{task_id}").status_code == 200

    completed = client.post(
        f"/api/tasks/{task_id}/complete",
        json={"person_id": person_id},
    )
    assert completed.status_code == 200

    after = get_state(client)
    assert task_from_state(after, task_id)["active"] is False

    undo = client.post(f"/api/undo/{completed.json()['undo_id']}")
    assert undo.status_code == 200
    restored = get_state(client)
    assert task_from_state(restored, task_id)["active"] is True
    assert [t["id"] for t in restored["today"]] == [task_id]


def test_people_create_edit_delete_restore_and_keep_history(client):
    created = client.post(
        "/api/people",
        json={"name": "Alex", "color": "#abcdef", "icon": "🙂"},
    )
    assert created.status_code == 200
    person_id = created.json()["id"]

    updated = client.put(
        f"/api/people/{person_id}",
        json={"name": "Alexandra", "color": "#fedcba", "icon": "🧑"},
    )
    assert updated.status_code == 200

    state = get_state(client)
    person = next(p for p in state["people"] if p["id"] == person_id)
    assert person["name"] == "Alexandra"
    assert person["color"] == "#fedcba"

    task_id = state["upcoming"][0]["id"]
    assert client.post(f"/api/today/{task_id}").status_code == 200
    completed = client.post(
        f"/api/tasks/{task_id}/complete",
        json={"person_id": person_id},
    )
    assert completed.status_code == 200

    deleted = client.delete(f"/api/people/{person_id}")
    assert deleted.status_code == 200
    delete_undo_id = deleted.json()["undo_id"]

    after_delete = get_state(client)
    assert all(p["id"] != person_id for p in after_delete["people"])
    stored = next(p for p in after_delete["people_all"] if p["id"] == person_id)
    assert stored["active"] == 0
    assert any(
        h["person_id"] == person_id and h["name"] == "Alexandra"
        for h in after_delete["history"]
    )

    restore = client.post(f"/api/people/{person_id}/restore")
    assert restore.status_code == 200
    assert any(p["id"] == person_id for p in get_state(client)["people"])

    # El deshacer de la eliminación también es seguro si la persona ya está activa.
    # Primero deshacemos la restauración y luego la eliminación.
    restore_undo_id = restore.json()["undo_id"]
    assert client.post(f"/api/undo/{restore_undo_id}").status_code == 200
    assert all(p["id"] != person_id for p in get_state(client)["people"])

    assert client.post(f"/api/undo/{delete_undo_id}").status_code == 200
    assert any(p["id"] == person_id for p in get_state(client)["people"])


def test_cannot_delete_last_active_person(client):
    state = get_state(client)
    ids = [p["id"] for p in state["people"]]

    assert client.delete(f"/api/people/{ids[0]}").status_code == 200
    assert client.delete(f"/api/people/{ids[1]}").status_code == 200

    response = client.delete(f"/api/people/{ids[2]}")
    assert response.status_code == 400
    assert len(get_state(client)["people"]) == 1


def test_task_create_edit_archive_and_undo(client):
    created = client.post(
        "/api/tasks",
        json=task_payload(title="Crear editar archivar"),
    )
    assert created.status_code == 200
    task_id = created.json()["id"]

    edited_payload = task_payload(
        title="Nombre editado",
        description="Nueva descripción",
        frequency_days=12,
    )
    edited = client.put(f"/api/tasks/{task_id}", json=edited_payload)
    assert edited.status_code == 200

    edited_task = task_from_state(get_state(client), task_id)
    assert edited_task["title"] == "Nombre editado"
    assert edited_task["description"] == "Nueva descripción"
    assert edited_task["frequency_days"] == 12

    archived = client.delete(f"/api/tasks/{task_id}")
    assert archived.status_code == 200
    assert task_from_state(get_state(client), task_id)["active"] is False

    undo = client.post(f"/api/undo/{archived.json()['undo_id']}")
    assert undo.status_code == 200
    assert task_from_state(get_state(client), task_id)["active"] is True


def test_area_owner_is_inherited_and_task_can_override_it(client):
    state = get_state(client)
    owner = state["people"][0]
    override_owner = state["people"][1]

    area_response = client.post(
        "/api/areas",
        json={
            "name": "Administración doméstica",
            "description": "Pagos, citas y documentación.",
            "color": "#e7eefb",
            "icon": "📋",
            "owner_person_id": owner["id"],
        },
    )
    assert area_response.status_code == 200
    area_id = area_response.json()["id"]

    created = client.post(
        "/api/tasks",
        json=task_payload(
            title="Revisar facturas",
            area_id=area_id,
            task_type="management",
            definition_of_done="Facturas revisadas y pagos programados.",
            responsibility_notes="Incluye detectar pagos próximos.",
        ),
    )
    assert created.status_code == 200
    task_id = created.json()["id"]

    task = task_from_state(get_state(client), task_id)
    assert task["area"]["id"] == area_id
    assert task["task_type"] == "management"
    assert task["definition_of_done"] == "Facturas revisadas y pagos programados."
    assert task["effective_owner"]["id"] == owner["id"]
    assert task["responsibility_source"] == "area"

    override_payload = task_payload(
        title="Revisar facturas",
        area_id=area_id,
        owner_person_id=override_owner["id"],
        task_type="management",
        definition_of_done="Facturas revisadas y pagos programados.",
        responsibility_notes="Incluye detectar pagos próximos.",
    )
    updated = client.put(f"/api/tasks/{task_id}", json=override_payload)
    assert updated.status_code == 200

    overridden = task_from_state(get_state(client), task_id)
    assert overridden["effective_owner"]["id"] == override_owner["id"]
    assert overridden["responsibility_source"] == "task"


def test_area_archive_and_undo_preserve_task(client):
    state = get_state(client)
    owner = state["people"][0]
    area_response = client.post(
        "/api/areas",
        json={
            "name": "Mascotas",
            "description": "Cuidados y suministros.",
            "color": "#f7dde4",
            "icon": "🐾",
            "owner_person_id": owner["id"],
        },
    )
    assert area_response.status_code == 200
    area_id = area_response.json()["id"]

    created = client.post(
        "/api/tasks",
        json=task_payload(title="Revisar pienso", area_id=area_id),
    )
    assert created.status_code == 200
    task_id = created.json()["id"]

    archived = client.delete(f"/api/areas/{area_id}")
    assert archived.status_code == 200
    undo_id = archived.json()["undo_id"]

    after = get_state(client)
    area = next(a for a in after["areas_all"] if a["id"] == area_id)
    assert area["active"] is False
    task = task_from_state(after, task_id)
    assert task["area"]["id"] == area_id
    assert task["effective_owner"] is None

    undone = client.post(f"/api/undo/{undo_id}")
    assert undone.status_code == 200
    restored = get_state(client)
    area = next(a for a in restored["areas"] if a["id"] == area_id)
    assert area["active"] is True
    assert task_from_state(restored, task_id)["effective_owner"]["id"] == owner["id"]


def test_task_rejects_invalid_area_owner_and_type(client):
    state = get_state(client)
    payload = task_payload(area_id=999999)
    assert client.post("/api/tasks", json=payload).status_code == 400

    payload = task_payload(owner_person_id=999999)
    assert client.post("/api/tasks", json=payload).status_code == 400

    payload = task_payload(task_type="unknown")
    assert client.post("/api/tasks", json=payload).status_code == 400


def test_area_cannot_be_deleted_until_all_tasks_are_moved(client):
    state = get_state(client)

    source = client.post(
        "/api/areas",
        json={
            "name": "Piso alquiler A",
            "description": "Gestión integral del inmueble.",
            "color": "#e7eefb",
            "icon": "🏢",
            "owner_person_id": state["people"][0]["id"],
        },
    )
    assert source.status_code == 200
    source_id = source.json()["id"]

    destination = client.post(
        "/api/areas",
        json={
            "name": "Administración patrimonial",
            "description": "Gestión general.",
            "color": "#ddf5e4",
            "icon": "📁",
            "owner_person_id": state["people"][1]["id"],
        },
    )
    assert destination.status_code == 200
    destination_id = destination.json()["id"]

    first = client.post(
        "/api/tasks",
        json=task_payload(title="Revisar alquiler", area_id=source_id, task_type="management"),
    )
    second = client.post(
        "/api/tasks",
        json=task_payload(title="Revisar seguro del piso", area_id=source_id, task_type="management"),
    )
    assert first.status_code == 200
    assert second.status_code == 200
    first_id = first.json()["id"]
    second_id = second.json()["id"]

    # Incluso una tarea archivada sigue contando como asociada.
    assert client.delete(f"/api/tasks/{second_id}").status_code == 200
    area = next(a for a in get_state(client)["areas"] if a["id"] == source_id)
    assert area["task_count"] == 1
    assert area["total_task_count"] == 2

    blocked = client.delete(f"/api/areas/{source_id}/hard")
    assert blocked.status_code == 409
    detail = blocked.json()["detail"]
    assert "2 tarea(s)" in detail
    assert "0 evento(s)" in detail

    moved_first = client.put(
        f"/api/tasks/{first_id}/area",
        json={"area_id": destination_id},
    )
    assert moved_first.status_code == 200

    still_blocked = client.delete(f"/api/areas/{source_id}/hard")
    assert still_blocked.status_code == 409

    moved_second = client.put(
        f"/api/tasks/{second_id}/area",
        json={"area_id": destination_id},
    )
    assert moved_second.status_code == 200

    source_after = next(a for a in get_state(client)["areas"] if a["id"] == source_id)
    assert source_after["total_task_count"] == 0

    deleted = client.delete(f"/api/areas/{source_id}/hard")
    assert deleted.status_code == 200
    assert all(a["id"] != source_id for a in get_state(client)["areas_all"])


def test_move_task_between_areas_is_undoable(client):
    state = get_state(client)
    area_a = state["areas"][0]["id"]
    area_b = state["areas"][1]["id"]

    created = client.post(
        "/api/tasks",
        json=task_payload(title="Mover entre áreas", area_id=area_a),
    )
    assert created.status_code == 200
    task_id = created.json()["id"]

    moved = client.put(
        f"/api/tasks/{task_id}/area",
        json={"area_id": area_b},
    )
    assert moved.status_code == 200
    undo_id = moved.json()["undo_id"]
    assert task_from_state(get_state(client), task_id)["area_id"] == area_b

    undone = client.post(f"/api/undo/{undo_id}")
    assert undone.status_code == 200
    assert task_from_state(get_state(client), task_id)["area_id"] == area_a


def test_task_cannot_be_moved_into_archived_area(client):
    state = get_state(client)
    area_id = state["areas"][0]["id"]
    task_id = state["tasks"][0]["id"]

    archived = client.delete(f"/api/areas/{area_id}")
    assert archived.status_code == 200

    response = client.put(
        f"/api/tasks/{task_id}/area",
        json={"area_id": area_id},
    )
    assert response.status_code == 400


def test_requested_household_people_and_areas_are_seeded_idempotently(client):
    state = get_state(client)
    assert [p["name"] for p in state["people"]] == ["Cosi", "Jose", "Li"]

    expected_areas = {
        "Piso Fanalwegle",
        "Piso Im Gapetsch",
        "Casa de Cosi",
        "Vehículos",
        "Krankenkassen",
    }
    names = {a["name"] for a in state["areas"]}
    assert expected_areas.issubset(names)

    # Volver a inicializar no debe duplicar personas ni áreas.
    import app as app_module
    app_module.init_db()
    again = get_state(client)
    assert [p["name"] for p in again["people"]] == ["Cosi", "Jose", "Li"]
    area_names = [a["name"] for a in again["areas_all"]]
    for name in expected_areas:
        assert area_names.count(name) == 1


def test_event_create_update_and_delete(client):
    import app as app_module

    state = get_state(client)
    area_id = state["areas"][0]["id"]
    event_at = (app_module.now_local() + timedelta(days=2)).replace(
        second=0, microsecond=0, tzinfo=None
    ).isoformat(timespec="minutes")

    created = client.post(
        "/api/events",
        json={
            "title": "Reunión de propietarios",
            "description": "Llevar documentación.",
            "area_id": area_id,
            "event_at": event_at,
            "reminders": [1440, 60, 60],
        },
    )
    assert created.status_code == 200
    event_id = created.json()["id"]

    state = get_state(client)
    event = next(e for e in state["events"] if e["id"] == event_id)
    assert event["title"] == "Reunión de propietarios"
    assert event["area"]["id"] == area_id
    assert event["reminders"] == [1440, 60]
    assert any(e["id"] == event_id for e in state["event_upcoming"])

    updated_at = (app_module.now_local() + timedelta(days=3)).replace(
        second=0, microsecond=0, tzinfo=None
    ).isoformat(timespec="minutes")
    updated = client.put(
        f"/api/events/{event_id}",
        json={
            "title": "Reunión comunidad",
            "description": "Nuevo orden del día.",
            "area_id": area_id,
            "event_at": updated_at,
            "reminders": [10080, 120],
        },
    )
    assert updated.status_code == 200

    event = next(e for e in get_state(client)["events"] if e["id"] == event_id)
    assert event["title"] == "Reunión comunidad"
    assert event["reminders"] == [10080, 120]

    deleted = client.delete(f"/api/events/{event_id}")
    assert deleted.status_code == 200
    assert all(e["id"] != event_id for e in get_state(client)["events"])


def test_event_due_reminder_can_be_acknowledged(client):
    import app as app_module

    event_at = (app_module.now_local() + timedelta(minutes=30)).replace(
        second=0, microsecond=0, tzinfo=None
    ).isoformat(timespec="minutes")

    created = client.post(
        "/api/events",
        json={
            "title": "Llamada administración",
            "description": "",
            "area_id": None,
            "event_at": event_at,
            "reminders": [60, 0],
        },
    )
    assert created.status_code == 200
    event_id = created.json()["id"]

    state = get_state(client)
    alert = next(
        a
        for a in state["alerts_due"]
        if a["event_id"] == event_id and a["reminder_minutes"] == 60
    )
    assert alert["title"] == "Llamada administración"
    assert not any(
        a["event_id"] == event_id and a["reminder_minutes"] == 0
        for a in state["alerts_due"]
    )

    ack = client.post(f"/api/events/{event_id}/reminders/60/ack")
    assert ack.status_code == 200
    after = get_state(client)
    assert not any(
        a["event_id"] == event_id and a["reminder_minutes"] == 60
        for a in after["alerts_due"]
    )


def test_event_today_and_upcoming_classification(client):
    import app as app_module

    now = app_module.now_local()
    today_event = (now + timedelta(minutes=30)).replace(
        second=0, microsecond=0, tzinfo=None
    ).isoformat(timespec="minutes")
    tomorrow_event = (now + timedelta(days=1, minutes=30)).replace(
        second=0, microsecond=0, tzinfo=None
    ).isoformat(timespec="minutes")

    today_created = client.post(
        "/api/events",
        json={
            "title": "Evento de hoy",
            "description": "",
            "area_id": None,
            "event_at": today_event,
            "reminders": [],
        },
    )
    tomorrow_created = client.post(
        "/api/events",
        json={
            "title": "Evento de mañana",
            "description": "",
            "area_id": None,
            "event_at": tomorrow_event,
            "reminders": [],
        },
    )
    assert today_created.status_code == 200
    assert tomorrow_created.status_code == 200

    state = get_state(client)
    assert any(e["id"] == today_created.json()["id"] for e in state["event_today"])
    assert any(e["id"] == tomorrow_created.json()["id"] for e in state["event_upcoming"])


def test_event_rejects_invalid_date_area_and_reminder(client):
    base = {
        "title": "Evento inválido",
        "description": "",
        "area_id": None,
        "event_at": "no-es-fecha",
        "reminders": [60],
    }
    assert client.post("/api/events", json=base).status_code == 400

    base["event_at"] = "2030-01-01T12:00"
    base["area_id"] = 999999
    assert client.post("/api/events", json=base).status_code == 400

    base["area_id"] = None
    base["reminders"] = [-1]
    assert client.post("/api/events", json=base).status_code == 400


def test_area_with_linked_event_cannot_be_deleted(client):
    import app as app_module

    state = get_state(client)
    area_id = state["areas"][0]["id"]
    event_at = (app_module.now_local() + timedelta(days=1)).replace(
        second=0, microsecond=0, tzinfo=None
    ).isoformat(timespec="minutes")

    created = client.post(
        "/api/events",
        json={
            "title": "Reunión del área",
            "description": "",
            "area_id": area_id,
            "event_at": event_at,
            "reminders": [60],
        },
    )
    assert created.status_code == 200

    area = next(a for a in get_state(client)["areas"] if a["id"] == area_id)
    assert area["event_count"] == 1

    blocked = client.delete(f"/api/areas/{area_id}/hard")
    assert blocked.status_code == 409
    assert "1 evento(s)" in blocked.json()["detail"]


def test_telegram_detect_connect_test_and_disconnect(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "TELEGRAM_BOT_TOKEN", "test-token")
    sent = []

    def fake_telegram(method, payload=None):
        if method == "getChat":
            assert int(payload["chat_id"]) == -1001234567890
            return {
                "id": -1001234567890,
                "title": 'Casa "Familia"',
                "type": "supergroup",
            }
        if method == "sendMessage":
            sent.append(dict(payload))
            return {"message_id": 1}
        raise AssertionError(f"Método inesperado: {method}")

    monkeypatch.setattr(app_module, "telegram_api_request", fake_telegram)

    # El único consumidor de getUpdates es el worker. Aquí simulamos que
    # ya vio un mensaje del grupo antes de seleccionarlo.
    app_module.process_telegram_update(
        {
            "update_id": 1,
            "message": {
                "chat": {
                    "id": -1001234567890,
                    "title": 'Casa "Familia"',
                    "type": "supergroup",
                },
                "text": "/casa",
            },
        }
    )

    detected = client.post("/api/telegram/chats")
    assert detected.status_code == 200
    chats = detected.json()["chats"]
    assert chats == [
        {
            "chat_id": -1001234567890,
            "title": 'Casa "Familia"',
            "type": "supergroup",
        }
    ]

    connected = client.put(
        "/api/telegram/chat",
        json={"chat_id": -1001234567890, "title": ""},
    )
    assert connected.status_code == 200
    assert connected.json()["chat_title"] == 'Casa "Familia"'

    status = client.get("/api/telegram/status")
    assert status.status_code == 200
    body = status.json()
    assert body["token_configured"] is True
    assert body["chat_id"] == -1001234567890
    assert body["chat_title"] == 'Casa "Familia"'
    assert "test-token" not in str(body)

    test_message = client.post("/api/telegram/test")
    assert test_message.status_code == 200
    assert len(sent) == 1
    assert sent[0]["chat_id"] == "-1001234567890"
    assert "Casa Tareas" in sent[0]["text"]

    disconnected = client.delete("/api/telegram/chat")
    assert disconnected.status_code == 200
    after = client.get("/api/telegram/status").json()
    assert after["chat_id"] is None
    assert after["chat_title"] == ""


def test_telegram_reminder_is_sent_once_and_skips_stale_reminders(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "TELEGRAM_BOT_TOKEN", "test-token")
    sent = []

    def fake_telegram(method, payload=None):
        if method == "sendMessage":
            sent.append(dict(payload))
            return {"message_id": len(sent)}
        raise AssertionError(f"Método inesperado: {method}")

    monkeypatch.setattr(app_module, "telegram_api_request", fake_telegram)

    with app_module.db() as conn:
        app_module.set_meta(conn, "telegram_chat_id", -1009876543210)
        app_module.set_meta(conn, "telegram_chat_title", "Casa Tareas")

    event_at = (app_module.now_local() + timedelta(minutes=30)).replace(
        second=0, microsecond=0, tzinfo=None
    ).isoformat(timespec="minutes")
    created = client.post(
        "/api/events",
        json={
            "title": "Reunión del piso",
            "description": "Llevar las actas.",
            "area_id": None,
            "event_at": event_at,
            "reminders": [1440, 60],
        },
    )
    assert created.status_code == 200
    event_id = created.json()["id"]

    assert app_module.process_telegram_reminders() == 1
    assert len(sent) == 1
    assert sent[0]["chat_id"] == "-1009876543210"
    assert "Reunión del piso" in sent[0]["text"]
    assert "1 hora antes" in sent[0]["text"]

    # Una segunda comprobación no debe duplicar el mismo aviso.
    assert app_module.process_telegram_reminders() == 0
    assert len(sent) == 1

    # Los recordatorios ya vencidos se marcan como procesados para evitar
    # enviar después el de 1 día con retraso.
    with app_module.db() as conn:
        rows = conn.execute(
            """SELECT reminder_minutes FROM notification_deliveries
               WHERE event_id=? AND channel='telegram'
               ORDER BY reminder_minutes DESC""",
            (event_id,),
        ).fetchall()
    assert [r["reminder_minutes"] for r in rows] == [1440, 60]


def test_editing_event_resets_telegram_delivery_state(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(
        app_module,
        "telegram_api_request",
        lambda method, payload=None: {"message_id": 1},
    )

    with app_module.db() as conn:
        app_module.set_meta(conn, "telegram_chat_id", -100111222333)

    event_at = (app_module.now_local() + timedelta(minutes=30)).replace(
        second=0, microsecond=0, tzinfo=None
    ).isoformat(timespec="minutes")
    created = client.post(
        "/api/events",
        json={
            "title": "Evento editable",
            "description": "",
            "area_id": None,
            "event_at": event_at,
            "reminders": [60],
        },
    )
    event_id = created.json()["id"]
    assert app_module.process_telegram_reminders() == 1

    later = (app_module.now_local() + timedelta(days=2)).replace(
        second=0, microsecond=0, tzinfo=None
    ).isoformat(timespec="minutes")
    updated = client.put(
        f"/api/events/{event_id}",
        json={
            "title": "Evento editable",
            "description": "",
            "area_id": None,
            "event_at": later,
            "reminders": [60],
        },
    )
    assert updated.status_code == 200

    with app_module.db() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM notification_deliveries WHERE event_id=?",
            (event_id,),
        ).fetchone()[0]
    assert count == 0


def test_telegram_commands_create_modify_and_undo_task(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "TELEGRAM_BOT_TOKEN", "test-token")
    sent = []

    def fake_telegram(method, payload=None):
        if method == "sendMessage":
            sent.append(dict(payload))
            return {"message_id": len(sent)}
        raise AssertionError(f"Método inesperado: {method}")

    monkeypatch.setattr(app_module, "telegram_api_request", fake_telegram)
    chat_id = -100500600700
    with app_module.db() as conn:
        app_module.set_meta(conn, "telegram_chat_id", chat_id)
        app_module.set_meta(conn, "telegram_chat_title", "Casa Tareas")

    app_module.telegram_handle_command(
        chat_id,
        "/tarea Revisar contrato | Piso Fanalwegle | gestión",
    )
    state = get_state(client)
    task = next(t for t in state["tasks"] if t["title"] == "Revisar contrato")
    assert task["area"]["name"] == "Piso Fanalwegle"
    assert task["task_type"] == "management"

    app_module.telegram_handle_command(
        chat_id,
        "/renombrar Revisar contrato | Revisar contrato anual",
    )
    renamed = task_from_state(get_state(client), task["id"])
    assert renamed["title"] == "Revisar contrato anual"

    app_module.telegram_handle_command(
        chat_id,
        "/mover Revisar contrato anual | Krankenkassen",
    )
    moved = task_from_state(get_state(client), task["id"])
    assert moved["area"]["name"] == "Krankenkassen"

    tomorrow = (app_module.today_local() + timedelta(days=1)).isoformat()
    app_module.telegram_handle_command(
        chat_id,
        "/posponer Revisar contrato anual | mañana",
    )
    postponed = task_from_state(get_state(client), task["id"])
    assert postponed["next_due"] == tomorrow

    # /deshacer revierte solo la última acción realizada desde Telegram.
    app_module.telegram_handle_command(chat_id, "/deshacer")
    restored = task_from_state(get_state(client), task["id"])
    assert restored["next_due"] == app_module.today_local().isoformat()

    assert any("Tarea creada" in m["text"] for m in sent)
    assert any("Krankenkassen" in m["text"] for m in sent)
    assert any("pospuesta" in m["text"] for m in sent)


def test_telegram_hecha_callback_is_single_use(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "TELEGRAM_BOT_TOKEN", "test-token")
    calls = []

    def fake_telegram(method, payload=None):
        calls.append((method, dict(payload or {})))
        if method == "sendMessage":
            return {"message_id": 321}
        if method in {"answerCallbackQuery", "editMessageReplyMarkup"}:
            return True
        raise AssertionError(f"Método inesperado: {method}")

    monkeypatch.setattr(app_module, "telegram_api_request", fake_telegram)
    chat_id = -100700800900
    with app_module.db() as conn:
        app_module.set_meta(conn, "telegram_chat_id", chat_id)
        task = conn.execute(
            "SELECT id,title FROM tasks WHERE title='Sacar basura' AND active=1"
        ).fetchone()
        person = conn.execute(
            "SELECT id,name FROM people WHERE name='Jose' AND active=1"
        ).fetchone()

    app_module.telegram_handle_command(chat_id, "/hecha Sacar basura")
    send_call = next(
        payload for method, payload in calls
        if method == "sendMessage" and "¿Quién hizo" in payload.get("text", "")
    )
    keyboard = json.loads(send_call["reply_markup"])
    assert len(keyboard["inline_keyboard"][0]) == 3

    with app_module.db() as conn:
        pending = conn.execute(
            """SELECT id FROM telegram_pending_actions
               WHERE action_type='complete' AND used_at IS NULL
               ORDER BY id DESC LIMIT 1"""
        ).fetchone()
    callback_data = f"done:{pending['id']}:{person['id']}"
    update = {
        "update_id": 55,
        "callback_query": {
            "id": "cb-1",
            "data": callback_data,
            "message": {
                "message_id": 321,
                "chat": {"id": chat_id, "title": "Casa Tareas", "type": "supergroup"},
            },
        },
    }

    app_module.process_telegram_update(update)
    after = get_state(client)
    matches = [
        h for h in after["history"]
        if h["task_id"] == task["id"] and h["name"] == "Jose"
    ]
    assert len(matches) == 1

    # Pulsar de nuevo el mismo botón no crea una segunda realización.
    update["callback_query"]["id"] = "cb-2"
    app_module.process_telegram_update(update)
    again = get_state(client)
    matches = [
        h for h in again["history"]
        if h["task_id"] == task["id"] and h["name"] == "Jose"
    ]
    assert len(matches) == 1


def test_telegram_ignores_commands_from_unconfigured_chat(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(
        app_module,
        "telegram_api_request",
        lambda method, payload=None: {"message_id": 1},
    )
    allowed_chat = -100111000111
    other_chat = -100222000222
    with app_module.db() as conn:
        app_module.set_meta(conn, "telegram_chat_id", allowed_chat)

    app_module.process_telegram_update(
        {
            "update_id": 10,
            "message": {
                "chat": {"id": other_chat, "title": "Otro grupo", "type": "supergroup"},
                "text": "/tarea No debe existir | Vehículos | gestión",
            },
        }
    )
    assert all(
        t["title"] != "No debe existir"
        for t in get_state(client)["tasks"]
    )

    with app_module.db() as conn:
        seen = conn.execute(
            "SELECT title FROM telegram_chats_seen WHERE chat_id=?",
            (other_chat,),
        ).fetchone()
    assert seen["title"] == "Otro grupo"


def test_telegram_update_offset_prevents_reprocessing(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "TELEGRAM_BOT_TOKEN", "test-token")
    chat_id = -100333000333
    requests = []
    first = True

    def fake_telegram(method, payload=None):
        nonlocal first
        payload = dict(payload or {})
        requests.append((method, payload))
        if method == "getUpdates":
            if first:
                first = False
                return [
                    {
                        "update_id": 42,
                        "message": {
                            "chat": {
                                "id": chat_id,
                                "title": "Casa",
                                "type": "supergroup",
                            },
                            "text": "/tarea Desde offset | Vehículos | gestión",
                        },
                    }
                ]
            return []
        if method == "sendMessage":
            return {"message_id": 1}
        raise AssertionError(f"Método inesperado: {method}")

    monkeypatch.setattr(app_module, "telegram_api_request", fake_telegram)
    with app_module.db() as conn:
        app_module.set_meta(conn, "telegram_chat_id", chat_id)

    assert app_module.process_telegram_updates(timeout=0) == 1
    assert app_module.process_telegram_updates(timeout=0) == 0

    get_calls = [payload for method, payload in requests if method == "getUpdates"]
    assert get_calls[0]["offset"] == 0
    assert get_calls[1]["offset"] == 43
    assert sum(
        1 for t in get_state(client)["tasks"] if t["title"] == "Desde offset"
    ) == 1


def test_telegram_event_command_creates_area_event(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "TELEGRAM_BOT_TOKEN", "test-token")
    sent = []
    monkeypatch.setattr(
        app_module,
        "telegram_api_request",
        lambda method, payload=None: (
            sent.append(dict(payload or {})) or {"message_id": 1}
        ),
    )
    chat_id = -100444000444
    with app_module.db() as conn:
        app_module.set_meta(conn, "telegram_chat_id", chat_id)

    app_module.telegram_handle_command(
        chat_id,
        "/evento Reunión propietarios | 2030-11-12 19:00 | Piso Im Gapetsch | 1d,2h",
    )

    state = get_state(client)
    event = next(e for e in state["events"] if e["title"] == "Reunión propietarios")
    assert event["area"]["name"] == "Piso Im Gapetsch"
    assert event["reminders"] == [1440, 120]
    assert any("12.11.2030" in m.get("text", "") for m in sent)


def test_task_need_score_and_estimated_duration(client):
    import app as app_module

    today = app_module.today_local()

    due_now = client.post(
        "/api/tasks",
        json=task_payload(
            title="Necesidad alta",
            frequency_days=10,
            initial_due_date=today.isoformat(),
            anchor_date=today.isoformat(),
            estimated_minutes=20,
        ),
    )
    assert due_now.status_code == 200

    due_soon = client.post(
        "/api/tasks",
        json=task_payload(
            title="Necesidad sugerida",
            frequency_days=10,
            initial_due_date=(today + timedelta(days=3)).isoformat(),
            anchor_date=(today + timedelta(days=3)).isoformat(),
            estimated_minutes=10,
        ),
    )
    assert due_soon.status_code == 200

    not_yet = client.post(
        "/api/tasks",
        json=task_payload(
            title="Necesidad próxima",
            frequency_days=10,
            initial_due_date=(today + timedelta(days=4)).isoformat(),
            anchor_date=(today + timedelta(days=4)).isoformat(),
            estimated_minutes=30,
        ),
    )
    assert not_yet.status_code == 200

    state = get_state(client)
    high = task_from_state(state, due_now.json()["id"])
    suggested = task_from_state(state, due_soon.json()["id"])
    soon = task_from_state(state, not_yet.json()["id"])

    assert high["estimated_minutes"] == 20
    assert high["need_score"] == 100
    assert high["need_label"] == "Pendiente"
    assert high["is_suggested"] is True

    assert suggested["need_score"] == 70
    assert suggested["need_label"] == "Conviene hacer"
    assert suggested["is_suggested"] is True

    assert soon["need_score"] == 60
    assert soon["need_label"] == "Pronto"
    assert soon["is_suggested"] is False

    suggested_ids = [t["id"] for t in state["suggested"]]
    assert due_now.json()["id"] in suggested_ids
    assert due_soon.json()["id"] in suggested_ids
    assert not_yet.json()["id"] not in suggested_ids

    # La lista prioriza mayor necesidad y usa duración como desempate secundario.
    assert suggested_ids.index(due_now.json()["id"]) < suggested_ids.index(due_soon.json()["id"])


def test_today_queue_removes_task_from_suggestions(client):
    import app as app_module

    today = app_module.today_local()
    created = client.post(
        "/api/tasks",
        json=task_payload(
            title="Sugerida pero manual",
            frequency_days=7,
            initial_due_date=today.isoformat(),
            anchor_date=today.isoformat(),
            estimated_minutes=5,
        ),
    )
    assert created.status_code == 200
    task_id = created.json()["id"]

    before = get_state(client)
    assert any(t["id"] == task_id for t in before["suggested"])

    added = client.post(f"/api/today/{task_id}")
    assert added.status_code == 200

    after = get_state(client)
    assert any(t["id"] == task_id for t in after["today"])
    assert all(t["id"] != task_id for t in after["suggested"])


def test_completion_resets_cycle_need(client):
    import app as app_module

    today = app_module.today_local()
    created = client.post(
        "/api/tasks",
        json=task_payload(
            title="Necesidad reiniciable",
            frequency_days=10,
            initial_due_date=today.isoformat(),
            anchor_date=today.isoformat(),
            estimated_minutes=15,
        ),
    )
    assert created.status_code == 200
    task_id = created.json()["id"]

    before = task_from_state(get_state(client), task_id)
    assert before["need_score"] == 100

    person_id = get_state(client)["people"][0]["id"]
    completed = client.post(
        f"/api/tasks/{task_id}/complete",
        json={"person_id": person_id},
    )
    assert completed.status_code == 200

    after = task_from_state(get_state(client), task_id)
    assert after["need_score"] == 0
    assert after["need_label"] == "Puede esperar"
    assert after["is_suggested"] is False


def test_postpone_recalculates_need_from_new_due_date(client):
    import app as app_module

    today = app_module.today_local()
    created = client.post(
        "/api/tasks",
        json=task_payload(
            title="Necesidad pospuesta",
            frequency_days=10,
            initial_due_date=today.isoformat(),
            anchor_date=today.isoformat(),
        ),
    )
    assert created.status_code == 200
    task_id = created.json()["id"]

    postponed_to = today + timedelta(days=5)
    postponed = client.post(
        f"/api/tasks/{task_id}/postpone",
        json={"due_date": postponed_to.isoformat()},
    )
    assert postponed.status_code == 200

    task = task_from_state(get_state(client), task_id)
    assert task["next_due"] == postponed_to.isoformat()
    assert task["need_score"] == 50
    assert task["need_label"] == "Pronto"
    assert task["is_suggested"] is False


def test_one_off_task_has_no_need_score_and_duration_validation(client):
    created = client.post(
        "/api/tasks",
        json=task_payload(
            title="Puntual sin porcentaje",
            recurrence_type="none",
            frequency_days=None,
            estimated_minutes=60,
        ),
    )
    assert created.status_code == 200
    task = task_from_state(get_state(client), created.json()["id"])
    assert task["estimated_minutes"] == 60
    assert task["need_score"] is None
    assert task["need_label"] is None
    assert task["is_suggested"] is False

    invalid = client.post(
        "/api/tasks",
        json=task_payload(title="Duración inválida", estimated_minutes=0),
    )
    assert invalid.status_code == 422


def test_estimated_duration_can_be_changed(client):
    import app as app_module

    today = app_module.today_local()
    created = client.post(
        "/api/tasks",
        json=task_payload(
            title="Duración editable",
            estimated_minutes=10,
            initial_due_date=today.isoformat(),
            anchor_date=today.isoformat(),
        ),
    )
    assert created.status_code == 200
    task_id = created.json()["id"]

    updated = client.put(
        f"/api/tasks/{task_id}",
        json=task_payload(
            title="Duración editable",
            estimated_minutes=45,
            initial_due_date=today.isoformat(),
            anchor_date=today.isoformat(),
        ),
    )
    assert updated.status_code == 200
    assert task_from_state(get_state(client), task_id)["estimated_minutes"] == 45


def test_vacation_hides_tasks_but_keeps_excluded_area_and_agenda(client):
    import app as app_module

    base = app_module.today_local()
    state = get_state(client)
    included_area = next(a for a in state["areas"] if a["name"] == "Alimentación")
    excluded_area = next(a for a in state["areas"] if a["name"] == "Piso Fanalwegle")

    included = client.post(
        "/api/tasks",
        json=task_payload(
            title="Tarea de vacaciones",
            area_id=included_area["id"],
            initial_due_date=base.isoformat(),
            anchor_date=base.isoformat(),
        ),
    )
    excluded = client.post(
        "/api/tasks",
        json=task_payload(
            title="Tarea que sigue activa",
            area_id=excluded_area["id"],
            initial_due_date=base.isoformat(),
            anchor_date=base.isoformat(),
        ),
    )
    assert included.status_code == 200
    assert excluded.status_code == 200
    included_id = included.json()["id"]
    excluded_id = excluded.json()["id"]

    assert client.post(f"/api/today/{included_id}").status_code == 200
    assert client.post(f"/api/today/{excluded_id}").status_code == 200

    event_at = (app_module.now_local() + timedelta(days=1)).replace(
        second=0, microsecond=0, tzinfo=None
    ).isoformat(timespec="minutes")
    event = client.post(
        "/api/events",
        json={
            "title": "Reunión durante vacaciones",
            "description": "",
            "area_id": included_area["id"],
            "event_at": event_at,
            "reminders": [60],
        },
    )
    assert event.status_code == 200

    started = client.post(
        "/api/vacation/start",
        json={
            "return_date": (base + timedelta(days=7)).isoformat(),
            "resume_mode": "continue_cycle",
            "excluded_area_ids": [excluded_area["id"]],
        },
    )
    assert started.status_code == 200

    during = get_state(client)
    assert during["vacation"]["active"] is True
    assert during["vacation"]["excluded_area_ids"] == [excluded_area["id"]]

    included_task = task_from_state(during, included_id)
    excluded_task = task_from_state(during, excluded_id)
    assert included_task["paused"] is True
    assert included_task["pause"]["source"] == "vacation"
    assert excluded_task["paused"] is False

    assert all(t["id"] != included_id for t in during["today"])
    assert any(t["id"] == excluded_id for t in during["today"])
    assert all(t["id"] != included_id for t in during["suggested"])
    assert all(t["id"] != included_id for t in during["upcoming"])
    assert any(e["id"] == event.json()["id"] for e in during["event_upcoming"])

    # La cola se conserva internamente y reaparecerá tras la pausa.
    with app_module.db() as conn:
        assert conn.execute(
            "SELECT 1 FROM today_queue WHERE task_id=?", (included_id,)
        ).fetchone() is not None


def test_continue_cycle_vacation_shifts_due_dates_on_return(client, monkeypatch):
    import app as app_module

    base = app_module.today_local()
    area = next(a for a in get_state(client)["areas"] if a["name"] == "Alimentación")
    excluded_area = next(
        a for a in get_state(client)["areas"] if a["name"] == "Piso Fanalwegle"
    )

    cycle = client.post(
        "/api/tasks",
        json=task_payload(
            title="Ciclo pausado",
            area_id=area["id"],
            frequency_days=10,
            initial_due_date=(base + timedelta(days=2)).isoformat(),
            anchor_date=(base + timedelta(days=2)).isoformat(),
        ),
    )
    fixed = client.post(
        "/api/tasks",
        json=task_payload(
            title="Fija pausada",
            area_id=area["id"],
            recurrence_type="fixed",
            frequency_days=7,
            initial_due_date=(base + timedelta(days=2)).isoformat(),
            anchor_date=(base + timedelta(days=2)).isoformat(),
        ),
    )
    excluded = client.post(
        "/api/tasks",
        json=task_payload(
            title="Ciclo excluido",
            area_id=excluded_area["id"],
            frequency_days=10,
            initial_due_date=(base + timedelta(days=2)).isoformat(),
            anchor_date=(base + timedelta(days=2)).isoformat(),
        ),
    )
    assert cycle.status_code == fixed.status_code == excluded.status_code == 200

    return_day = base + timedelta(days=5)
    started = client.post(
        "/api/vacation/start",
        json={
            "return_date": return_day.isoformat(),
            "resume_mode": "continue_cycle",
            "excluded_area_ids": [excluded_area["id"]],
        },
    )
    assert started.status_code == 200

    monkeypatch.setattr(app_module, "today_local", lambda: return_day)
    after = get_state(client)
    assert after["vacation"]["active"] is False

    cycle_task = task_from_state(after, cycle.json()["id"])
    fixed_task = task_from_state(after, fixed.json()["id"])
    excluded_task = task_from_state(after, excluded.json()["id"])

    assert cycle_task["next_due"] == (base + timedelta(days=7)).isoformat()
    assert fixed_task["next_due"] == (base + timedelta(days=7)).isoformat()
    assert excluded_task["next_due"] == (base + timedelta(days=2)).isoformat()


def test_keep_calendar_vacation_does_not_shift_due_dates(client, monkeypatch):
    import app as app_module

    base = app_module.today_local()
    created = client.post(
        "/api/tasks",
        json=task_payload(
            title="Calendario conservado",
            frequency_days=10,
            initial_due_date=(base + timedelta(days=2)).isoformat(),
            anchor_date=(base + timedelta(days=2)).isoformat(),
        ),
    )
    task_id = created.json()["id"]

    return_day = base + timedelta(days=5)
    assert client.post(
        "/api/vacation/start",
        json={
            "return_date": return_day.isoformat(),
            "resume_mode": "keep_calendar",
            "excluded_area_ids": [],
        },
    ).status_code == 200

    monkeypatch.setattr(app_module, "today_local", lambda: return_day)
    task = task_from_state(get_state(client), task_id)
    assert task["paused"] is False
    assert task["next_due"] == (base + timedelta(days=2)).isoformat()
    assert task["need_score"] == 100


def test_task_pause_blocks_actions_and_restores_today_queue(client, monkeypatch):
    import app as app_module

    base = app_module.today_local()
    created = client.post(
        "/api/tasks",
        json=task_payload(
            title="Pausa individual",
            frequency_days=7,
            initial_due_date=(base + timedelta(days=1)).isoformat(),
            anchor_date=(base + timedelta(days=1)).isoformat(),
        ),
    )
    task_id = created.json()["id"]
    assert client.post(f"/api/today/{task_id}").status_code == 200

    return_day = base + timedelta(days=3)
    paused = client.post(
        f"/api/tasks/{task_id}/pause",
        json={
            "return_date": return_day.isoformat(),
            "resume_mode": "continue_cycle",
        },
    )
    assert paused.status_code == 200

    during = get_state(client)
    task = task_from_state(during, task_id)
    assert task["paused"] is True
    assert task["pause"]["source"] == "task"
    assert all(t["id"] != task_id for t in during["today"])

    assert client.post(f"/api/today/{task_id}").status_code == 409
    assert client.post(
        f"/api/tasks/{task_id}/postpone",
        json={"due_date": (base + timedelta(days=10)).isoformat()},
    ).status_code == 409
    assert client.post(
        f"/api/tasks/{task_id}/complete",
        json={"person_id": during["people"][0]["id"]},
    ).status_code == 409

    monkeypatch.setattr(app_module, "today_local", lambda: return_day)
    after = get_state(client)
    task = task_from_state(after, task_id)
    assert task["paused"] is False
    assert task["next_due"] == (base + timedelta(days=4)).isoformat()
    assert any(t["id"] == task_id for t in after["today"])


def test_area_pause_keep_calendar_and_resume(client, monkeypatch):
    import app as app_module

    base = app_module.today_local()
    area = next(a for a in get_state(client)["areas"] if a["name"] == "Vehículos")
    created = client.post(
        "/api/tasks",
        json=task_payload(
            title="Revisar vehículo",
            area_id=area["id"],
            initial_due_date=(base + timedelta(days=1)).isoformat(),
            anchor_date=(base + timedelta(days=1)).isoformat(),
        ),
    )
    task_id = created.json()["id"]

    return_day = base + timedelta(days=4)
    paused = client.post(
        f"/api/areas/{area['id']}/pause",
        json={
            "return_date": return_day.isoformat(),
            "resume_mode": "keep_calendar",
        },
    )
    assert paused.status_code == 200

    during = get_state(client)
    paused_area = next(a for a in during["areas"] if a["id"] == area["id"])
    task = task_from_state(during, task_id)
    assert paused_area["paused"] is True
    assert paused_area["pause"]["source"] == "area"
    assert task["paused"] is True
    assert task["pause"]["source"] == "area"

    monkeypatch.setattr(app_module, "today_local", lambda: return_day)
    after = get_state(client)
    task = task_from_state(after, task_id)
    area_after = next(a for a in after["areas"] if a["id"] == area["id"])
    assert task["paused"] is False
    assert area_after["paused"] is False
    assert task["next_due"] == (base + timedelta(days=1)).isoformat()


def test_pause_overlap_is_rejected_unless_area_is_excluded(client):
    import app as app_module

    base = app_module.today_local()
    area = next(a for a in get_state(client)["areas"] if a["name"] == "Vehículos")
    created = client.post(
        "/api/tasks",
        json=task_payload(title="Tarea ya pausada", area_id=area["id"]),
    )
    task_id = created.json()["id"]
    return_day = (base + timedelta(days=5)).isoformat()

    assert client.post(
        f"/api/tasks/{task_id}/pause",
        json={"return_date": return_day, "resume_mode": "continue_cycle"},
    ).status_code == 200

    blocked = client.post(
        "/api/vacation/start",
        json={
            "return_date": return_day,
            "resume_mode": "continue_cycle",
            "excluded_area_ids": [],
        },
    )
    assert blocked.status_code == 409

    allowed = client.post(
        "/api/vacation/start",
        json={
            "return_date": return_day,
            "resume_mode": "continue_cycle",
            "excluded_area_ids": [area["id"]],
        },
    )
    assert allowed.status_code == 200


def test_vacation_rejects_invalid_return_date_mode_and_area(client):
    import app as app_module

    today = app_module.today_local().isoformat()
    assert client.post(
        "/api/vacation/start",
        json={
            "return_date": today,
            "resume_mode": "continue_cycle",
            "excluded_area_ids": [],
        },
    ).status_code == 400

    future = (app_module.today_local() + timedelta(days=2)).isoformat()
    assert client.post(
        "/api/vacation/start",
        json={
            "return_date": future,
            "resume_mode": "inventado",
            "excluded_area_ids": [],
        },
    ).status_code == 400

    assert client.post(
        "/api/vacation/start",
        json={
            "return_date": future,
            "resume_mode": "continue_cycle",
            "excluded_area_ids": [999999],
        },
    ).status_code == 400


def test_reorder_today_ignores_hidden_paused_tasks(client):
    import app as app_module

    base = app_module.today_local()
    state = get_state(client)
    paused_area = next(a for a in state["areas"] if a["name"] == "Alimentación")
    active_area = next(a for a in state["areas"] if a["name"] == "Piso Fanalwegle")

    paused_task = client.post(
        "/api/tasks",
        json=task_payload(title="Oculta en vacaciones", area_id=paused_area["id"]),
    ).json()["id"]
    visible_a = client.post(
        "/api/tasks",
        json=task_payload(title="Visible A", area_id=active_area["id"]),
    ).json()["id"]
    visible_b = client.post(
        "/api/tasks",
        json=task_payload(title="Visible B", area_id=active_area["id"]),
    ).json()["id"]

    for task_id in (paused_task, visible_a, visible_b):
        assert client.post(f"/api/today/{task_id}").status_code == 200

    assert client.post(
        "/api/vacation/start",
        json={
            "return_date": (base + timedelta(days=5)).isoformat(),
            "resume_mode": "continue_cycle",
            "excluded_area_ids": [active_area["id"]],
        },
    ).status_code == 200

    during = get_state(client)
    assert [t["id"] for t in during["today"]] == [visible_a, visible_b]

    reordered = client.post(
        "/api/today/reorder",
        json={"task_ids": [visible_b, visible_a]},
    )
    assert reordered.status_code == 200
    assert [t["id"] for t in get_state(client)["today"]] == [visible_b, visible_a]

    assert client.post(f"/api/undo/{reordered.json()['undo_id']}").status_code == 200
    assert [t["id"] for t in get_state(client)["today"]] == [visible_a, visible_b]

    with app_module.db() as conn:
        hidden = conn.execute(
            "SELECT position FROM today_queue WHERE task_id=?", (paused_task,)
        ).fetchone()
    assert hidden is not None


def test_inventory_drives_shopping_and_task_supplies(client):
    created_item = client.post(
        "/api/inventory",
        json={
            "name": "Limpiador de baño",
            "category": "Limpieza",
            "area_id": None,
            "unit": "botella",
            "purchase_quantity": "1 botella",
            "stock_status": "ok",
            "shopping_requested": False,
            "notes": "Sin perfume fuerte.",
        },
    )
    assert created_item.status_code == 200
    item_id = created_item.json()["id"]

    task = client.post(
        "/api/tasks",
        json=task_payload(
            title="Limpiar baño",
            supply_ids=[item_id],
        ),
    )
    assert task.status_code == 200
    task_id = task.json()["id"]

    state = get_state(client)
    linked = task_from_state(state, task_id)
    assert [x["id"] for x in linked["supplies"]] == [item_id]
    assert linked["missing_supplies"] == []
    assert state["shopping_list"] == []

    low = client.post(
        f"/api/inventory/{item_id}/stock",
        json={"stock_status": "low", "shopping_requested": None},
    )
    assert low.status_code == 200
    state = get_state(client)
    shopping = next(x for x in state["shopping_list"] if x["id"] == item_id)
    assert shopping["needs_purchase"] is True
    assert shopping["stock_status"] == "low"
    assert [t["title"] for t in shopping["required_by"]] == ["Limpiar baño"]
    assert task_from_state(state, task_id)["missing_supplies"] == []

    out = client.post(
        f"/api/inventory/{item_id}/stock",
        json={"stock_status": "out", "shopping_requested": None},
    )
    assert out.status_code == 200
    state = get_state(client)
    assert [
        x["name"] for x in task_from_state(state, task_id)["missing_supplies"]
    ] == ["Limpiador de baño"]

    blocked = client.delete(f"/api/inventory/{item_id}")
    assert blocked.status_code == 409

    replenished = client.post(
        f"/api/inventory/{item_id}/stock",
        json={"stock_status": "ok", "shopping_requested": False},
    )
    assert replenished.status_code == 200
    assert all(x["id"] != item_id for x in get_state(client)["shopping_list"])


def test_inventory_manual_buy_request(client):
    item = client.post(
        "/api/inventory",
        json={
            "name": "Guantes",
            "category": "Limpieza",
            "area_id": None,
            "unit": "caja",
            "purchase_quantity": "1 caja",
            "stock_status": "ok",
            "shopping_requested": True,
            "notes": "",
        },
    )
    assert item.status_code == 200
    item_id = item.json()["id"]
    assert any(x["id"] == item_id for x in get_state(client)["shopping_list"])

    done = client.post(
        f"/api/inventory/{item_id}/stock",
        json={"stock_status": "ok", "shopping_requested": False},
    )
    assert done.status_code == 200
    assert all(x["id"] != item_id for x in get_state(client)["shopping_list"])


def test_task_and_area_document_attachments(client):
    state = get_state(client)
    task_id = state["tasks"][0]["id"]
    area = client.post(
        "/api/areas",
        json={
            "name": "Área con documentos",
            "description": "",
            "color": "#e7eefb",
            "icon": "📁",
            "owner_person_id": None,
        },
    )
    assert area.status_code == 200
    area_id = area.json()["id"]

    upload_task = client.post(
        "/api/attachments",
        data={"entity_type": "task", "entity_id": str(task_id)},
        files={"file": ("manual.pdf", b"%PDF-test-content", "application/pdf")},
    )
    assert upload_task.status_code == 200
    task_attachment_id = upload_task.json()["id"]

    upload_area = client.post(
        "/api/attachments",
        data={"entity_type": "area", "entity_id": str(area_id)},
        files={"file": ("contrato.txt", b"contrato", "text/plain")},
    )
    assert upload_area.status_code == 200
    area_attachment_id = upload_area.json()["id"]

    state = get_state(client)
    task = task_from_state(state, task_id)
    assert task["attachment_count"] == 1
    assert task["attachments"][0]["original_name"] == "manual.pdf"
    assert "stored_name" not in task["attachments"]

    area_state = next(a for a in state["areas"] if a["id"] == area_id)
    assert area_state["attachment_count"] == 1
    assert area_state["attachments"][0]["original_name"] == "contrato.txt"

    downloaded = client.get(f"/api/attachments/{task_attachment_id}/download")
    assert downloaded.status_code == 200
    assert downloaded.content == b"%PDF-test-content"
    assert "manual.pdf" in downloaded.headers["content-disposition"]

    blocked = client.delete(f"/api/areas/{area_id}/hard")
    assert blocked.status_code == 409
    assert "1 documento(s)" in blocked.json()["detail"]

    assert client.delete(f"/api/attachments/{area_attachment_id}").status_code == 200
    assert client.delete(f"/api/areas/{area_id}/hard").status_code == 200

    assert client.delete(f"/api/attachments/{task_attachment_id}").status_code == 200
    assert task_from_state(get_state(client), task_id)["attachment_count"] == 0


def test_activity_feed_records_household_changes(client):
    created = client.post(
        "/api/tasks",
        json=task_payload(title="Actividad visible"),
    )
    assert created.status_code == 200
    task_id = created.json()["id"]

    state = get_state(client)
    person_id = state["people"][0]["id"]
    completed = client.post(
        f"/api/tasks/{task_id}/complete",
        json={"person_id": person_id},
    )
    assert completed.status_code == 200

    activity = get_state(client)["activity"]
    summaries = [a["summary"] for a in activity]
    assert any('Creada la tarea "Actividad visible"' in x for x in summaries)
    assert any("completó" in x and "Actividad visible" in x for x in summaries)


def test_ical_subscription_expands_recurring_events_and_hides_secret_url(
    client, monkeypatch
):
    import app as app_module

    tomorrow = app_module.today_local() + timedelta(days=1)
    start = datetime.combine(tomorrow, datetime.min.time()).replace(hour=10)
    end = start + timedelta(hours=1)
    ics = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//Casa Tareas Test//EN\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:reunion-test\r\n"
        f"DTSTART:{start.strftime('%Y%m%dT%H%M%S')}Z\r\n"
        f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}Z\r\n"
        "RRULE:FREQ=DAILY;COUNT=2\r\n"
        "SUMMARY:Reunión externa\r\n"
        "LOCATION:Sala común\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    ).encode()

    monkeypatch.setattr(
        app_module,
        "normalize_calendar_url",
        lambda value: value.strip(),
    )
    monkeypatch.setattr(
        app_module,
        "fetch_calendar_bytes",
        lambda url: ics,
    )

    created = client.post(
        "/api/calendars",
        json={
            "name": "Comunidad",
            "url": "https://calendar.example/secret-token/calendar.ics",
            "area_id": None,
        },
    )
    assert created.status_code == 200
    assert created.json()["synced"] is True
    assert created.json()["event_count"] == 2
    subscription_id = created.json()["id"]

    state = get_state(client)
    subscription = next(
        x for x in state["calendar_subscriptions"] if x["id"] == subscription_id
    )
    assert "url" not in subscription
    assert subscription["url_display"] == "calendar.example"
    assert "secret-token" not in str(subscription)

    external = [
        e for e in state["external_events"]
        if e["subscription_id"] == subscription_id
    ]
    assert len(external) == 2
    assert all(e["external"] is True for e in external)
    assert external[0]["title"] == "Reunión externa"
    assert external[0]["location"] == "Sala común"
    assert any(
        e["external"] and e["title"] == "Reunión externa"
        for e in state["event_upcoming"]
    )

    deleted = client.delete(f"/api/calendars/{subscription_id}")
    assert deleted.status_code == 200
    after = get_state(client)
    assert all(
        e["subscription_id"] != subscription_id
        for e in after["external_events"]
    )


def test_ical_sync_failure_keeps_last_valid_cache(client, monkeypatch):
    import app as app_module

    tomorrow = app_module.today_local() + timedelta(days=1)
    ics = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:cache-test\r\n"
        f"DTSTART:{tomorrow.strftime('%Y%m%d')}\r\n"
        "SUMMARY:Evento conservado\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    ).encode()

    monkeypatch.setattr(app_module, "normalize_calendar_url", lambda value: value.strip())
    monkeypatch.setattr(app_module, "fetch_calendar_bytes", lambda url: ics)

    created = client.post(
        "/api/calendars",
        json={
            "name": "Calendario cacheado",
            "url": "https://calendar.example/cache.ics",
            "area_id": None,
        },
    )
    subscription_id = created.json()["id"]
    before = [
        e for e in get_state(client)["external_events"]
        if e["subscription_id"] == subscription_id
    ]
    assert len(before) == 1

    def fail_fetch(url):
        raise RuntimeError("fallo de red")

    monkeypatch.setattr(app_module, "fetch_calendar_bytes", fail_fetch)
    failed = client.post(f"/api/calendars/{subscription_id}/sync")
    assert failed.status_code == 502

    state = get_state(client)
    after = [
        e for e in state["external_events"]
        if e["subscription_id"] == subscription_id
    ]
    assert len(after) == 1
    sub = next(
        x for x in state["calendar_subscriptions"] if x["id"] == subscription_id
    )
    assert "fallo de red" in sub["last_error"]


def test_telegram_inventory_commands(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "TELEGRAM_BOT_TOKEN", "test-token")
    sent = []

    def fake_telegram(method, payload=None):
        if method == "sendMessage":
            sent.append(dict(payload or {}))
            return {"message_id": len(sent)}
        raise AssertionError(f"Método inesperado: {method}")

    monkeypatch.setattr(app_module, "telegram_api_request", fake_telegram)
    chat_id = -100565656565
    with app_module.db() as conn:
        app_module.set_meta(conn, "telegram_chat_id", chat_id)

    item = client.post(
        "/api/inventory",
        json={
            "name": "Detergente",
            "category": "Limpieza",
            "area_id": None,
            "unit": "botella",
            "purchase_quantity": "1 botella",
            "stock_status": "ok",
            "shopping_requested": False,
            "notes": "",
        },
    )
    assert item.status_code == 200

    app_module.telegram_handle_command(chat_id, "/stock Detergente | falta")
    state = get_state(client)
    stored = next(x for x in state["inventory"] if x["name"] == "Detergente")
    assert stored["stock_status"] == "out"

    app_module.telegram_handle_command(chat_id, "/comprar")
    assert any("Detergente" in m.get("text", "") for m in sent)

    app_module.telegram_handle_command(chat_id, "/stock Detergente | hay")
    assert all(
        x["name"] != "Detergente"
        for x in get_state(client)["shopping_list"]
    )

    app_module.telegram_handle_command(chat_id, "/comprar Detergente")
    assert any(
        x["name"] == "Detergente"
        for x in get_state(client)["shopping_list"]
    )


def test_remove_from_today_preserves_schedule_and_is_undoable(client):
    import app as app_module

    base = app_module.today_local()
    due = (base + timedelta(days=5)).isoformat()
    created = client.post(
        "/api/tasks",
        json=task_payload(
            title="Seleccionada por error",
            recurrence_type="cycle",
            frequency_days=14,
            initial_due_date=due,
            anchor_date=due,
            estimated_minutes=20,
        ),
    )
    assert created.status_code == 200
    task_id = created.json()["id"]

    added = client.post(f"/api/today/{task_id}")
    assert added.status_code == 200

    before = get_state(client)
    task_before = task_from_state(before, task_id)
    today_before = [t["id"] for t in before["today"]]
    assert task_id in today_before
    assert task_before["next_due"] == due
    recurrence_before = task_before["recurrence_type"]
    need_before = task_before["need_score"]

    removed = client.delete(f"/api/today/{task_id}")
    assert removed.status_code == 200
    assert removed.json()["already_removed"] is False
    assert removed.json()["undo_id"] is not None

    after = get_state(client)
    task_after = task_from_state(after, task_id)
    assert all(t["id"] != task_id for t in after["today"])
    assert any(t["id"] == task_id for t in after["upcoming"])
    assert task_after["next_due"] == due
    assert task_after["recurrence_type"] == recurrence_before
    assert task_after["need_score"] == need_before

    undone = client.post(f"/api/undo/{removed.json()['undo_id']}")
    assert undone.status_code == 200
    restored = get_state(client)
    assert [t["id"] for t in restored["today"]] == today_before
    restored_task = task_from_state(restored, task_id)
    assert restored_task["next_due"] == due
    assert restored_task["recurrence_type"] == recurrence_before


def test_remove_from_today_is_idempotent(client):
    created = client.post(
        "/api/tasks",
        json=task_payload(title="No estaba en Hoy"),
    )
    assert created.status_code == 200
    task_id = created.json()["id"]

    removed = client.delete(f"/api/today/{task_id}")
    assert removed.status_code == 200
    assert removed.json() == {
        "ok": True,
        "undo_id": None,
        "already_removed": True,
    }


def test_completed_today_task_can_return_to_today(client):
    import app as app_module

    base = app_module.today_local()
    due = (base + timedelta(days=3)).isoformat()
    created = client.post(
        "/api/tasks",
        json=task_payload(
            title="Realización reversible",
            recurrence_type="cycle",
            frequency_days=10,
            initial_due_date=due,
            anchor_date=due,
        ),
    )
    assert created.status_code == 200
    task_id = created.json()["id"]

    assert client.post(f"/api/today/{task_id}").status_code == 200
    before = get_state(client)
    original_today_order = [t["id"] for t in before["today"]]
    original_task = task_from_state(before, task_id)

    person_id = before["people"][0]["id"]
    completed = client.post(
        f"/api/tasks/{task_id}/complete",
        json={"person_id": person_id},
    )
    assert completed.status_code == 200

    after_complete = get_state(client)
    history_item = next(
        h for h in after_complete["history"] if h["task_id"] == task_id
    )
    assert history_item["can_undo_to_today"] is True
    assert all(t["id"] != task_id for t in after_complete["today"])

    restored = client.post(
        f"/api/completions/{history_item['id']}/undo-to-today"
    )
    assert restored.status_code == 200

    after_restore = get_state(client)
    assert [t["id"] for t in after_restore["today"]] == original_today_order
    assert all(h["id"] != history_item["id"] for h in after_restore["history"])
    restored_task = task_from_state(after_restore, task_id)
    assert restored_task["active"] is True
    assert restored_task["next_due"] == original_task["next_due"]
    assert restored_task["need_score"] == original_task["need_score"]


def test_one_off_completion_rollback_reactivates_task(client):
    created = client.post(
        "/api/tasks",
        json=task_payload(
            title="Puntual reversible",
            recurrence_type="none",
            frequency_days=None,
        ),
    )
    assert created.status_code == 200
    task_id = created.json()["id"]
    assert client.post(f"/api/today/{task_id}").status_code == 200

    state = get_state(client)
    person_id = state["people"][0]["id"]
    assert client.post(
        f"/api/tasks/{task_id}/complete",
        json={"person_id": person_id},
    ).status_code == 200

    completed_state = get_state(client)
    completed_task = task_from_state(completed_state, task_id)
    assert completed_task["active"] is False
    history_item = next(
        h for h in completed_state["history"] if h["task_id"] == task_id
    )
    assert history_item["can_undo_to_today"] is True

    undone = client.post(
        f"/api/completions/{history_item['id']}/undo-to-today"
    )
    assert undone.status_code == 200

    restored = get_state(client)
    task = task_from_state(restored, task_id)
    assert task["active"] is True
    assert any(t["id"] == task_id for t in restored["today"])


def test_only_latest_completion_of_same_task_can_roll_back(client):
    created = client.post(
        "/api/tasks",
        json=task_payload(
            title="Dos realizaciones",
            recurrence_type="cycle",
            frequency_days=1,
        ),
    )
    assert created.status_code == 200
    task_id = created.json()["id"]
    person_id = get_state(client)["people"][0]["id"]

    completion_ids = []
    for _ in range(2):
        assert client.post(f"/api/today/{task_id}").status_code == 200
        assert client.post(
            f"/api/tasks/{task_id}/complete",
            json={"person_id": person_id},
        ).status_code == 200
        completion_ids.append(
            next(
                h["id"]
                for h in get_state(client)["history"]
                if h["task_id"] == task_id
            )
        )

    state = get_state(client)
    task_history = [h for h in state["history"] if h["task_id"] == task_id]
    assert task_history[0]["id"] == completion_ids[1]
    assert task_history[0]["can_undo_to_today"] is True
    assert task_history[1]["id"] == completion_ids[0]
    assert task_history[1]["can_undo_to_today"] is False

    blocked = client.post(
        f"/api/completions/{completion_ids[0]}/undo-to-today"
    )
    assert blocked.status_code == 409

    newest = client.post(
        f"/api/completions/{completion_ids[1]}/undo-to-today"
    )
    assert newest.status_code == 200

    after = get_state(client)
    older = next(h for h in after["history"] if h["id"] == completion_ids[0])
    assert older["can_undo_to_today"] is True


def test_completion_not_originating_in_today_is_not_drag_reversible(client):
    created = client.post(
        "/api/tasks",
        json=task_payload(
            title="Hecha fuera de Hoy",
            recurrence_type="cycle",
            frequency_days=7,
        ),
    )
    assert created.status_code == 200
    task_id = created.json()["id"]
    person_id = get_state(client)["people"][0]["id"]

    completed = client.post(
        f"/api/tasks/{task_id}/complete",
        json={"person_id": person_id},
    )
    assert completed.status_code == 200

    state = get_state(client)
    history_item = next(
        h for h in state["history"] if h["task_id"] == task_id
    )
    assert history_item["can_undo_to_today"] is False

    blocked = client.post(
        f"/api/completions/{history_item['id']}/undo-to-today"
    )
    assert blocked.status_code == 409


def test_web_managed_telegram_token_is_validated_stored_and_never_exposed(
    client, monkeypatch
):
    import app as app_module

    monkeypatch.setattr(app_module, "TELEGRAM_BOT_TOKEN", "")
    secret = "123456789:TEST_SECRET_TOKEN_NEVER_EXPOSE"
    calls = []

    def fake_telegram(method, payload=None, token=None):
        calls.append((method, dict(payload or {}), token))
        assert token == secret
        if method == "getMe":
            return {
                "id": 123456789,
                "username": "casa_tareas_test_bot",
                "first_name": "Casa Tareas",
            }
        if method == "setMyCommands":
            return True
        if method == "getUpdates":
            return []
        raise AssertionError(f"Método inesperado: {method}")

    monkeypatch.setattr(app_module, "telegram_api_request", fake_telegram)

    saved = client.put(
        "/api/settings/telegram-token",
        json={"token": secret},
    )
    assert saved.status_code == 200
    telegram = saved.json()["telegram"]
    assert telegram["token_configured"] is True
    assert telegram["token_source"] == "application"
    assert telegram["token_editable"] is True
    assert telegram["bot_username"] == "casa_tareas_test_bot"
    assert secret not in str(saved.json())

    with app_module.db() as conn:
        assert app_module.get_meta(conn, "telegram_bot_token") == secret

    settings = client.get("/api/settings")
    assert settings.status_code == 200
    assert secret not in settings.text
    assert settings.json()["telegram"]["token_source"] == "application"

    state = get_state(client)
    assert secret not in str(state)
    assert state["settings"]["telegram"]["token_configured"] is True

    assert any(method == "getMe" for method, _, _ in calls)
    assert any(method == "setMyCommands" for method, _, _ in calls)

    deleted = client.delete("/api/settings/telegram-token")
    assert deleted.status_code == 200
    assert deleted.json()["telegram"]["token_configured"] is False
    with app_module.db() as conn:
        assert app_module.get_meta(conn, "telegram_bot_token") is None
        assert app_module.get_meta(conn, "telegram_bot_username") is None


def test_environment_telegram_token_cannot_be_overwritten_from_web(
    client, monkeypatch
):
    import app as app_module

    environment_secret = "987654321:ENVIRONMENT_SECRET_TOKEN"
    monkeypatch.setattr(
        app_module,
        "TELEGRAM_BOT_TOKEN",
        environment_secret,
    )

    settings = client.get("/api/settings")
    assert settings.status_code == 200
    telegram = settings.json()["telegram"]
    assert telegram["token_configured"] is True
    assert telegram["token_source"] == "environment"
    assert telegram["token_editable"] is False
    assert environment_secret not in settings.text

    blocked = client.put(
        "/api/settings/telegram-token",
        json={"token": "123456789:OTHER_VALID_LOOKING_TOKEN"},
    )
    assert blocked.status_code == 409

    blocked_delete = client.delete("/api/settings/telegram-token")
    assert blocked_delete.status_code == 409


def test_runtime_settings_apply_without_container_restart(client):
    import app as app_module

    updated = client.put(
        "/api/settings/runtime",
        json={
            "timezone": "UTC",
            "telegram_poll_seconds": 90,
            "ical_sync_minutes": 15,
            "max_attachment_mb": 32,
        },
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["runtime"] == {
        "timezone": "UTC",
        "telegram_poll_seconds": 90,
        "ical_sync_minutes": 15,
        "max_attachment_bytes": 32 * 1024 * 1024,
        "max_attachment_mb": 32,
    }
    assert app_module.TZ.key == "UTC"
    assert app_module.TELEGRAM_POLL_SECONDS == 90
    assert app_module.ICAL_SYNC_MINUTES == 15
    assert app_module.MAX_ATTACHMENT_BYTES == 32 * 1024 * 1024

    with app_module.db() as conn:
        assert app_module.get_meta(conn, "setting_timezone") == "UTC"
        assert app_module.get_meta(conn, "setting_telegram_poll_seconds") == "90"
        assert app_module.get_meta(conn, "setting_ical_sync_minutes") == "15"
        assert (
            app_module.get_meta(conn, "setting_max_attachment_bytes")
            == str(32 * 1024 * 1024)
        )

    settings = client.get("/api/settings").json()
    assert settings["runtime"]["timezone"] == "UTC"
    assert settings["attachments"]["max_mb"] == 32


def test_runtime_settings_reject_invalid_timezone(client):
    invalid = client.put(
        "/api/settings/runtime",
        json={
            "timezone": "Mars/Olympus",
            "telegram_poll_seconds": 60,
            "ical_sync_minutes": 30,
            "max_attachment_mb": 20,
        },
    )
    assert invalid.status_code == 400


def test_frontend_uses_external_script_bundle(client):
    root = client.get("/")
    assert root.status_code == 200
    assert root.headers["cache-control"] == "no-store"
    assert '/static/app.js?v=1.3.0' in root.text
    assert '/static/gastos.js?v=1.3.0' in root.text
    assert '/static/gastos.css?v=1.3.0' in root.text
    assert "Cargando Casa Tareas" in root.text
    assert "<script>" not in root.text

    bundle = client.get("/static/app.js?v=1.3.0")
    assert bundle.status_code == 200
    assert "async function load()" in bundle.text
    assert 'api("/api/state")' in bundle.text


def test_gastos_comida_integration_settings_and_connection(client, monkeypatch):
    import app as app_module

    saved = client.put(
        "/api/settings/gastos-comida",
        json={"url": "http://gastos-comida:8000/"},
    )
    assert saved.status_code == 200
    integration = saved.json()["integration"]
    assert integration["configured"] is True
    assert integration["url"] == "http://gastos-comida:8000"
    assert integration["source"] == "application"

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                {
                    "ok": True,
                    "service": "gastos-comida",
                    "api_version": "1",
                    "products": 303,
                    "tickets": 62,
                    "items": 461,
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout=0):
        assert request.full_url == "http://gastos-comida:8000/api/v1/health"
        assert timeout == 5
        return FakeResponse()

    monkeypatch.setattr(app_module.urllib.request, "urlopen", fake_urlopen)

    tested = client.post("/api/integrations/gastos-comida/test")
    assert tested.status_code == 200
    assert tested.json()["health"] == {
        "api_version": "1",
        "products": 303,
        "tickets": 62,
        "items": 461,
    }

    settings = client.get("/api/settings").json()
    integration = settings["integrations"]["gastos_comida"]
    assert integration["configured"] is True
    assert integration["last_ok_at"] is not None
    assert integration["last_error"] == ""


def test_gastos_comida_integration_rejects_unsafe_base_url_shapes(client):
    credentials = client.put(
        "/api/settings/gastos-comida",
        json={"url": "http://user:secret@gastos-comida:8000"},
    )
    assert credentials.status_code == 400

    path = client.put(
        "/api/settings/gastos-comida",
        json={"url": "http://gastos-comida:8000/api"},
    )
    assert path.status_code == 400

    invalid_scheme = client.put(
        "/api/settings/gastos-comida",
        json={"url": "file:///tmp/gastos.db"},
    )
    assert invalid_scheme.status_code == 400


def test_gastos_proxy_dashboard_and_ticket_write(client, monkeypatch):
    import app as app_module

    saved = client.put(
        "/api/settings/gastos-comida",
        json={"url": "http://gastos-comida:8000"},
    )
    assert saved.status_code == 200

    seen = []

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout=0):
        seen.append((request.full_url, request.get_method(), request.data, timeout))
        if request.full_url.startswith("http://gastos-comida:8000/api/v1/dashboard"):
            return FakeResponse(
                {
                    "metrics": [],
                    "filters": {"chart_year": 2026},
                    "lookups": {"articles": [], "users": [], "supermarkets": []},
                    "years": [2026],
                    "recent_tickets": [],
                    "counts": {"products": 3, "tickets": 2, "items": 4},
                }
            )
        if request.full_url == "http://gastos-comida:8000/api/v1/tickets":
            assert request.get_method() == "POST"
            body = json.loads(request.data.decode("utf-8"))
            assert body["supermarket"] == "Coop"
            return FakeResponse({"ok": True, "ticket": {"id": 9, **body, "date": body["purchase_date"], "total": 1.5}})
        raise AssertionError(request.full_url)

    monkeypatch.setattr(app_module.urllib.request, "urlopen", fake_urlopen)

    dashboard = client.get("/api/gastos/dashboard?chart_year=2026")
    assert dashboard.status_code == 200
    assert dashboard.json()["counts"]["tickets"] == 2

    created = client.post(
        "/api/gastos/tickets",
        json={
            "purchase_date": "2026-10-04",
            "supermarket": "Coop",
            "items": [
                {
                    "article": "Pan",
                    "quantity": 1,
                    "price": 1.5,
                    "net_price": "",
                    "discount": "",
                    "discount_percent": "",
                    "user_name": "Jose",
                }
            ],
        },
    )
    assert created.status_code == 200
    assert created.json()["ticket"]["id"] == 9
    assert any(method == "POST" for _url, method, _data, _timeout in seen)


def test_gastos_purchase_restock_linked_inventory_item(client, monkeypatch):
    import app as app_module

    saved = client.put(
        "/api/settings/gastos-comida",
        json={"url": "http://gastos-comida:8000"},
    )
    assert saved.status_code == 200

    created_inventory = client.post(
        "/api/inventory",
        json={
            "name": "Pan",
            "category": "Alimentación",
            "area_id": None,
            "unit": "paquete",
            "purchase_quantity": "1 paquete",
            "stock_status": "out",
            "shopping_requested": True,
            "notes": "",
            "gastos_product_id": 77,
        },
    )
    assert created_inventory.status_code == 200
    inventory_id = created_inventory.json()["id"]

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout=0):
        assert request.full_url == "http://gastos-comida:8000/api/v1/tickets"
        assert request.get_method() == "POST"
        return FakeResponse(
            {
                "ok": True,
                "ticket": {
                    "id": 101,
                    "date": "2026-10-05",
                    "supermarket": "Coop",
                    "total": 2.5,
                    "items": [
                        {
                            "product_id": 77,
                            "article": "Pan",
                            "quantity": 1,
                            "price": 2.5,
                            "net_price": None,
                            "discount": 0,
                            "discount_percent": 0,
                            "total": 2.5,
                            "user_name": "Jose",
                        }
                    ],
                },
            }
        )

    monkeypatch.setattr(app_module.urllib.request, "urlopen", fake_urlopen)

    result = client.post(
        "/api/gastos/tickets",
        json={
            "purchase_date": "2026-10-05",
            "supermarket": "Coop",
            "items": [
                {
                    "article": "Pan",
                    "quantity": 1,
                    "price": 2.5,
                    "net_price": "",
                    "discount": "",
                    "discount_percent": "",
                    "user_name": "Jose",
                }
            ],
        },
    )
    assert result.status_code == 200
    assert result.json()["inventory_restocked"] == [{"id": inventory_id, "name": "Pan"}]

    state = client.get("/api/state").json()
    item = next(x for x in state["inventory"] if x["id"] == inventory_id)
    assert item["stock_status"] == "ok"
    assert item["shopping_requested"] is False
    assert item["gastos_product_id"] == 77
    assert item["gastos_linked"] is True
    assert item["last_purchased_at"] == "2026-10-05"
    assert item["last_purchase_ticket_id"] == 101
    assert all(x["id"] != inventory_id for x in state["shopping_list"])


def test_inventory_gastos_product_link_is_unique(client):
    first = client.post(
        "/api/inventory",
        json={
            "name": "Leche",
            "category": "Alimentación",
            "stock_status": "ok",
            "gastos_product_id": 12,
        },
    )
    assert first.status_code == 200

    second = client.post(
        "/api/inventory",
        json={
            "name": "Otra leche",
            "category": "Alimentación",
            "stock_status": "ok",
            "gastos_product_id": 12,
        },
    )
    assert second.status_code == 409
    assert "ya está vinculado" in second.json()["detail"]


def test_shopping_list_creates_and_resolves_automatic_task(client):
    initial = client.get("/api/state")
    assert initial.status_code == 200
    assert all(t["title"] != "Hacer la compra" or not t["active"] for t in initial.json()["tasks"])

    created = client.post(
        "/api/inventory",
        json={
            "name": "Papel de cocina",
            "category": "Alimentación",
            "stock_status": "out",
            "shopping_requested": False,
        },
    )
    assert created.status_code == 200
    item_id = created.json()["id"]

    state = client.get("/api/state").json()
    shopping_task = next(t for t in state["tasks"] if t["title"] == "Hacer la compra")
    assert shopping_task["active"] is True
    assert shopping_task["is_suggested"] is True
    assert shopping_task["need_score"] == 100
    assert "Papel de cocina" in shopping_task["description"]
    assert [item["id"] for item in shopping_task["supplies"]] == [item_id]
    assert any(t["id"] == shopping_task["id"] for t in state["suggested"])
    assert all(t["id"] != shopping_task["id"] for t in state["today"])

    restocked = client.post(
        f"/api/inventory/{item_id}/stock",
        json={"stock_status": "ok", "shopping_requested": False},
    )
    assert restocked.status_code == 200

    state = client.get("/api/state").json()
    same_task = next(t for t in state["tasks"] if t["id"] == shopping_task["id"])
    assert same_task["active"] is False
    assert not state["shopping_list"]
    assert all(t["id"] != shopping_task["id"] for t in state["suggested"])


def test_shopping_task_reuses_single_task_when_list_changes(client):
    first = client.post(
        "/api/inventory",
        json={"name": "Leche", "category": "Alimentación", "stock_status": "low"},
    )
    assert first.status_code == 200

    state = client.get("/api/state").json()
    task = next(t for t in state["tasks"] if t["title"] == "Hacer la compra")
    task_id = task["id"]

    second = client.post(
        "/api/inventory",
        json={"name": "Pan", "category": "Alimentación", "stock_status": "out"},
    )
    assert second.status_code == 200

    state = client.get("/api/state").json()
    tasks = [t for t in state["tasks"] if t["title"] == "Hacer la compra"]
    assert len(tasks) == 1
    assert tasks[0]["id"] == task_id
    assert "Leche" in tasks[0]["description"]
    assert "Pan" in tasks[0]["description"]

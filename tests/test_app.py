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
    assert "2 tarea(s) asociada(s)" in blocked.json()["detail"]

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

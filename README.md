# Casa Tareas

MVP autohospedado para gestionar tareas domésticas con una cola pequeña de **Hoy**, tareas futuras, catálogo e historial por persona.

## Funciones

- Cola **Hoy** con reordenación por drag & drop.
- Arrastrar una tarea a **Realizada** y elegir quién la hizo.
- La persona se atribuye al completar; no hay preasignación obligatoria.
- Tareas puntuales, por ciclo y de calendario fijo.
- Próximas tareas calculadas sin generar ocurrencias futuras.
- Posponer una aparición sin cambiar la frecuencia base.
- Catálogo editable y archivado sin perder el historial.
- Historial y resumen por persona de los últimos 30 días.
- SQLite y una sola aplicación FastAPI.
- Interfaz responsive para móvil.

## Arranque con Docker

```bash
docker compose up -d --build
```

Abre:

```text
http://localhost:3000
```

Los datos persisten en `./data/chores.db`.

## Arranque sin Docker

Requiere Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

Abre `http://localhost:8000`.

## Recurrencias

- `none`: puntual; se archiva al completarla.
- `cycle`: próxima fecha = última realización + X días.
- `fixed`: serie fija desde una fecha de anclaje; hacerla antes no desplaza la serie.

## Seguridad

El MVP no tiene autenticación. Está pensado para una red doméstica o VPN privada. No lo expongas directamente a Internet sin autenticación y HTTPS.

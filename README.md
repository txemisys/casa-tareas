# Casa Tareas

MVP autohospedado para gestionar tareas domésticas con una cola pequeña de **Hoy**, tareas futuras, catálogo, personas e historial.

## Funciones

- Tablero con **Próximamente → Hoy → Realizadas**.
- **Hoy es una cola manual**: mover una tarea a Hoy no arrastra automáticamente todas las tareas vencidas.
- Drag & drop protegido contra dobles drops y duplicados.
- Botón **Deshacer** persistente para los cambios recientes (24 h) y aviso con deshacer tras completar, posponer, mover a Hoy, reordenar, archivar o eliminar una persona.
- La persona se elige al completar la tarea; no hay preasignación obligatoria.
- Gestión de personas: **crear, editar, eliminar y restaurar**.
- Al eliminar una persona se conserva su historial, pero deja de aparecer en el selector de finalización.
- Tareas puntuales, por ciclo y de calendario fijo.
- Posponer una aparición sin cambiar la frecuencia base.
- Catálogo editable y archivado sin perder el historial.
- Historial y resumen por persona de los últimos 30 días.
- SQLite y una sola aplicación FastAPI.
- Interfaz responsive para móvil.

## Arranque con Docker

Requiere Docker Engine o Docker Desktop con Compose.

```bash
git clone https://github.com/txemisys/casa-tareas.git
cd casa-tareas
docker compose up -d --build
```

Abre:

```text
http://localhost:3000
```

Comprobar estado:

```bash
docker compose ps
```

Ver logs:

```bash
docker compose logs -f
```

Parar:

```bash
docker compose down
```

### Puerto y zona horaria

Puedes cambiarlos sin editar archivos:

```bash
APP_PORT=8080 APP_TIMEZONE=Europe/Madrid docker compose up -d --build
```

En PowerShell:

```powershell
$env:APP_PORT="8080"
$env:APP_TIMEZONE="Europe/Madrid"
docker compose up -d --build
```

## Portabilidad y backup

Toda la información persistente está en:

```text
data/chores.db
```

Para mover la aplicación a otro equipo:

1. Para el contenedor con `docker compose down`.
2. Copia la carpeta del proyecto, incluida `data/chores.db`.
3. En el equipo nuevo ejecuta `docker compose up -d --build`.

Para hacer un backup basta con copiar `data/chores.db` con el contenedor parado.

> La carpeta `data/` está ignorada por Git para no publicar información doméstica en GitHub.

## Arranque sin Docker

Requiere Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

En Windows, la activación del entorno virtual es:

```powershell
.venv\Scripts\Activate.ps1
```

Abre `http://localhost:8000`.

## Recurrencias

- `none`: puntual; se archiva al completarla.
- `cycle`: próxima fecha = última realización + X días.
- `fixed`: serie fija desde una fecha de anclaje; hacerla antes no desplaza la serie.

## Seguridad

El MVP no tiene autenticación. Está pensado para una red doméstica o VPN privada. No lo expongas directamente a Internet sin autenticación y HTTPS.

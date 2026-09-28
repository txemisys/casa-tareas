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

## Áreas y responsabilidad total

La aplicación diferencia entre **quién es responsable de que algo ocurra** y **quién ejecuta la tarea esta vez**.

- Las **Áreas** representan ámbitos completos del hogar, como Alimentación, Ropa y textil o Limpieza y mantenimiento.
- Cada área puede tener una persona responsable.
- Las tareas pueden heredar ese responsable o definir una excepción propia.
- Cada tarea puede marcarse como **🧹 Ejecución** o **🧠 Gestión / carga mental**.
- La ficha de tarea incluye **“Se considera terminada cuando…”** para acordar el estándar una sola vez.
- Las notas de responsabilidad permiten describir qué incluye la concepción, planificación y cierre sin crear un árbol de subtareas.
- Al completar una tarea se sigue preguntando **quién la hizo realmente**, independientemente de quién sea responsable del área.

Las bases existentes se migran de forma aditiva al arrancar; no es necesario borrar `data/chores.db`.

### Mover y eliminar áreas

En **Áreas** se muestran también las tareas asociadas a cada ámbito.

- En escritorio se pueden arrastrar tareas de un área a otra.
- En móvil o con teclado se puede usar el botón **Mover** de cada tarea.
- También existe **Sin área** como destino temporal.
- Las tareas archivadas siguen contando como asociadas y también se pueden mover.
- **Eliminar definitivamente** solo se habilita cuando el área tiene 0 tareas asociadas.
- La API aplica la misma restricción, por lo que no puede saltarse desde fuera de la interfaz.
- Mover una tarea entre áreas se puede **Deshacer**.

## Agenda y avisos

La aplicación incluye una **Agenda** separada de las tareas para reuniones, citas, vencimientos y otras fechas concretas.

- Cada evento puede asociarse a un Área.
- Puede tener fecha, hora, notas y varios recordatorios.
- Los eventos de hoy aparecen en la columna **Hoy** del tablero.
- Los eventos futuros aparecen en **Próximamente**.
- Los recordatorios vencidos aparecen como avisos dentro de Casa Tareas hasta marcarlos como **Visto**.
- Se pueden activar notificaciones del navegador cuando la app está abierta y el navegador dispone de un contexto seguro (HTTPS o localhost).
- Las Áreas con eventos asociados tampoco se pueden eliminar definitivamente hasta mover o reasignar esos eventos.

Las notificaciones del navegador de esta versión no garantizan avisos con la aplicación completamente cerrada. Para eso se necesita un canal externo o push web con servicio de notificaciones.

## Telegram

Casa Tareas puede enviar los recordatorios de la Agenda a un chat o grupo de Telegram aunque nadie tenga abierta la web.

### Activación

1. Crea un bot con **@BotFather** en Telegram y guarda el token.
2. Copia el archivo de ejemplo:

```bash
cp .env.example .env
```

En PowerShell:

```powershell
Copy-Item .env.example .env
```

3. Edita únicamente el archivo local `.env` y añade el token:

```text
TELEGRAM_BOT_TOKEN=pega_aqui_el_token
```

El archivo `.env` está excluido de Git y no debe subirse al repositorio.

4. Reinicia la aplicación:

```bash
docker compose down
docker compose up -d --build
```

5. Añade el bot al grupo de Telegram donde quieras recibir los avisos.
6. Envía un comando en el grupo, por ejemplo `/casa`.
7. En **Agenda → Telegram**, pulsa **Detectar chats**, selecciona el grupo y después **Enviar prueba**.

### Funcionamiento

El contenedor revisa los recordatorios cada 60 segundos por defecto. El intervalo puede cambiarse con `TELEGRAM_POLL_SECONDS`.

Los envíos realizados se registran en SQLite para evitar duplicados después de un reinicio. Si el servidor estuvo apagado y varios avisos de un mismo evento ya han vencido, Casa Tareas envía el más reciente y marca los anteriores como procesados, evitando una ráfaga de mensajes atrasados.

El token del bot nunca se devuelve a la interfaz ni se almacena en SQLite; solo se lee de la variable de entorno. En SQLite se guarda únicamente el identificador y el nombre del chat seleccionado.

## Pruebas automáticas

El repositorio incluye pruebas de regresión para los flujos principales: cola Hoy, duplicados, reordenación, deshacer, finalización, recurrencias, personas y edición/archivado de tareas.

Para ejecutarlas localmente:

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -q
```

GitHub Actions ejecuta automáticamente los tests y construye la imagen Docker en cada cambio a `main` y en cada pull request.

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

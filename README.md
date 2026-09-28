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

El bot es bidireccional: además de enviar recordatorios, acepta comandos **únicamente desde el chat seleccionado en Casa Tareas**. Mensajes de otros grupos o chats se registran para poder detectarlos, pero no pueden modificar datos.

Comandos principales:

```text
/hoy
/agenda
/pendientes Piso Fanalwegle
/tarea Revisar contrato | Piso Fanalwegle | gestión
/hecha Sacar basura
/mover Revisar seguro | Krankenkassen
/renombrar Revisar contrato | Revisar contrato anual
/posponer Limpiar baño | mañana
/evento Reunión propietarios | 2026-11-12 19:00 | Piso Im Gapetsch | 1d,2h
/deshacer
/ayuda
```

También se admite el prefijo `/casa`, por ejemplo `/casa hecha Sacar basura` o `/casa añade Revisar contrato | Piso Fanalwegle | gestión`.

`/hecha` no intenta adivinar quién realizó la tarea: Telegram muestra botones con las personas activas y la confirmación solo puede utilizarse una vez. No existen comandos de borrado desde Telegram.

El worker mantiene en SQLite el último `update_id` procesado de Telegram, por lo que un reinicio de Docker no vuelve a ejecutar comandos antiguos. El contenedor revisa los recordatorios cada 60 segundos por defecto; el intervalo puede cambiarse con `TELEGRAM_POLL_SECONDS`.

Los envíos realizados se registran en SQLite para evitar duplicados después de un reinicio. Si el servidor estuvo apagado y varios avisos de un mismo evento ya han vencido, Casa Tareas envía el más reciente y marca los anteriores como procesados, evitando una ráfaga de mensajes atrasados.

El token del bot nunca se devuelve a la interfaz ni se almacena en SQLite; solo se lee de la variable de entorno. En SQLite se guarda únicamente el identificador y el nombre del chat seleccionado.

## Corregir la cola de Hoy

Añadir una tarea a **Hoy** no cambia su recurrencia ni su fecha: solo la coloca en una cola manual.

Si se añadió por error, puede devolverse a **Próximamente** de dos formas:

- En escritorio, arrastrando la tarjeta de **Hoy → Próximamente**.
- En cualquier dispositivo, pulsando **← Quitar de Hoy**.

La acción solo elimina la entrada de `today_queue`; no cambia `next_due`, recurrencia, necesidad ni historial. También genera una acción **Deshacer**, que restaura la tarea en la misma posición que tenía en Hoy.

## Necesidad, sugerencias y duración

Las tareas recurrentes calculan una **necesidad** entre 0 % y 100 % según cuánto ha avanzado su ciclo.

- **Puede esperar**: menos del 40 %.
- **Pronto**: del 40 % al 69 %.
- **Conviene hacer**: del 70 % al 99 %.
- **Pendiente**: 100 %.

El porcentaje está limitado a 100 % para evitar indicadores alarmistas. Las tareas recurrentes con una necesidad del 70 % o más aparecen en **Sugeridas ahora**. Esta lista es informativa: una tarea no entra en **Hoy** hasta que alguien pulse **+ Hoy**.

Las tareas puntuales no reciben un porcentaje artificial; siguen usando su fecha prevista.

Cada tarea puede tener una **duración estimada**. La interfaz ofrece valores rápidos como 5, 10, 20 o 30 minutos y 1–2 horas. En **Sugeridas ahora** se puede filtrar por el tiempo disponible, por ejemplo **≤20 min**. Las tareas sin duración estimada siguen apareciendo en la vista completa, pero se excluyen cuando se aplica un filtro de tiempo porque no se puede garantizar que quepan en ese intervalo.

Al completar una tarea de ciclo, su necesidad vuelve al principio del ciclo. Si se pospone una tarea, la necesidad se recalcula respecto a la nueva fecha.

## Modo vacaciones y pausas

Casa Tareas permite pausar temporalmente tareas sin archivarlas ni perder su posición en **Hoy**.

### Modo vacaciones

Desde el **Tablero → Modo vacaciones** se configura una **fecha de regreso**. La pausa termina al comenzar ese día.

Se pueden excluir áreas que deban seguir funcionando durante las vacaciones, por ejemplo pisos en alquiler, Vehículos o Krankenkassen. Las tareas sin área quedan incluidas en la pausa global.

La **Agenda y los eventos no se pausan**: reuniones, citas, vencimientos y recordatorios de Telegram continúan activos.

Mientras una tarea está pausada:

- no aparece en **Hoy**, **Próximamente** ni **Sugeridas ahora**;
- conserva internamente su posición en Hoy y reaparece al reanudarse;
- no puede añadirse a Hoy, completarse, posponerse ni moverse a otra área;
- sigue visible en el catálogo de **Tareas** con la indicación de pausa.

Hay dos modos de reanudación:

- **Continuar ciclo**: los días de pausa no cuentan. Al regresar, la próxima fecha se desplaza por el tiempo realmente pausado. También se desplaza el anclaje de las tareas de calendario fijo.
- **Mantener calendario**: no se cambian las fechas. Al regresar, una tarea puede aparecer ya pendiente si su fecha cayó durante la pausa.

El modo vacaciones puede terminarse antes de la fecha prevista. En **Continuar ciclo**, solo se descuentan los días que realmente transcurrieron en pausa.

### Pausa por tarea o por área

Desde **Tareas** se puede pausar una tarea individual. Desde **Áreas** se puede pausar un área completa. Estas pausas usan los mismos dos modos de reanudación.

Para evitar dobles desplazamientos de fechas, Casa Tareas no permite superponer dos pausas sobre la misma tarea. Una pausa individual o de área puede coexistir con el modo vacaciones únicamente cuando su área está excluida de la pausa global.

## Novedades, documentos, calendarios e inventario

### Desde tu última visita

El Tablero incluye un bloque de **Novedades** con cambios recientes: tareas creadas, modificadas, movidas, pospuestas o completadas, cambios en Áreas, eventos, inventario, documentos, calendarios y modo vacaciones.

El punto de lectura se guarda en el navegador. Por tanto, cada móvil, tablet u ordenador conserva su propio "visto hasta aquí", sin necesitar cuentas individuales.

### Documentos y adjuntos

Las **Tareas** y las **Áreas** pueden guardar documentos relacionados: contratos, facturas, garantías, manuales, actas, imágenes o PDF.

Los archivos se guardan dentro de `data/attachments` con un nombre interno aleatorio; la interfaz conserva y muestra el nombre original. El tamaño máximo predeterminado es 20 MiB por archivo y puede cambiarse con `MAX_ATTACHMENT_BYTES`.

Una copia de seguridad de la carpeta `data` debe incluir tanto `chores.db` como `attachments/`.

Un Área con documentos asociados no se puede eliminar definitivamente hasta eliminar esos documentos. Al borrar definitivamente una tarea se eliminan también sus adjuntos.

### Calendarios externos iCal

En **Agenda → Calendarios externos** se pueden conectar calendarios iCal/ICS mediante una URL HTTPS, por ejemplo calendarios escolares, deportivos o de una comunidad.

- Se importan en modo **solo lectura**.
- Las recurrencias del calendario se expanden y aparecen junto a los eventos propios.
- Cada calendario puede asociarse opcionalmente a un Área.
- Se sincronizan automáticamente cada 30 minutos por defecto, además de poder sincronizarse manualmente.
- Si una sincronización falla, se conserva la última copia válida y se muestra el error.
- La URL completa no se devuelve a la interfaz, porque algunas URLs iCal contienen tokens privados.
- Los avisos propios de Casa Tareas y Telegram siguen aplicándose a los eventos creados en Casa Tareas. Los eventos iCal importados no generan recordatorios duplicados de Casa Tareas.

El intervalo automático se configura con `ICAL_SYNC_MINUTES`.

### Inventario y Comprar

Dentro de **Tareas → Inventario y Comprar** hay un inventario ligero pensado para consumibles domésticos.

Cada producto tiene uno de tres estados:

- **Hay**: disponible.
- **Poco**: queda, pero entra automáticamente en **Comprar**.
- **Falta**: entra en **Comprar** y las tareas que lo necesitan muestran que falta ese producto.

También se puede añadir manualmente un producto a **Comprar** aunque su estado sea **Hay**. Al pulsar **Repuesto**, vuelve a **Hay** y sale de la lista.

Las tareas pueden declarar varios **productos necesarios**. La lista Comprar agrega cada producto una sola vez aunque lo necesiten varias tareas, y muestra para qué tareas se necesita. No se descuenta stock automáticamente al completar una tarea: el objetivo es que mantener el inventario sea rápido, no llevar una contabilidad exacta de unidades.

Desde Telegram:

```text
/comprar
/comprar Limpiador de baño
/stock Limpiador de baño | falta
/stock Limpiador de baño | poco
/stock Limpiador de baño | hay
```

### Categorías

La categoría de una tarea sigue siendo libre. **Vacaciones-Viajes** aparece ahora entre las sugerencias junto con las categorías ya utilizadas.

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

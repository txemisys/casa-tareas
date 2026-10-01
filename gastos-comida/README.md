# Gastos de comida

Aplicación Flask importada desde el proyecto local original y versionada dentro de Casa Tareas.

## Arquitectura actual

- Flask 3 + Flask-SQLAlchemy.
- SQLite en `data/gastos.db`.
- Tickets con fecha, supermercado, total y líneas de compra.
- Las líneas guardan artículo, cantidad, precios/descuentos, usuario y ahora un `product_id` estable.
- Interfaz Jinja + JavaScript.
- El arranque migra de forma aditiva las bases antiguas: crea el catálogo `product`, añade `ticket_item.product_id` si falta y vincula los artículos históricos sin borrar tickets.

## API v1

La API de integración se mantiene separada de la interfaz web:

```text
GET /api/v1/health
GET /api/v1/products?q=leche
GET /api/v1/products/<id>
GET /api/v1/products/<id>/stats
GET /api/v1/spending/summary?from=2026-09-01&to=2026-09-30
GET /api/v1/purchases/recent?after_ticket_id=62
```

Se conserva también `GET /api/tickets` por compatibilidad.

Los IDs de producto son la referencia que Casa Tareas utilizará más adelante para vincular su inventario sin depender del texto del nombre.

## Datos

La base real `data/gastos.db` **no se guarda en Git**. El repositorio `casa-tareas` es público y el histórico de compras puede contener información personal.

La carpeta conserva solamente `data/.gitkeep`. Para ejecutar esta copia con los datos actuales habrá que copiar la base existente al servidor en:

```text
gastos-comida/data/gastos.db
```

No borres la instalación actual ni muevas su base de datos hasta preparar la migración del contenedor. El archivo `compose.yml` incluido aquí sigue separado del `docker-compose.yml` principal hasta que hagamos esa migración de forma controlada.

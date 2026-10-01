# Gastos de comida

Aplicación Flask importada desde el proyecto local original para poder versionarla junto con Casa Tareas y preparar una integración posterior.

## Arquitectura actual

- Flask 3 + Flask-SQLAlchemy.
- SQLite en `data/gastos.db`.
- Tickets con fecha, supermercado, total y líneas de compra.
- Las líneas guardan artículo, cantidad, precios/descuentos y usuario.
- Interfaz Jinja + JavaScript.
- API existente: `GET /api/tickets`.

## Datos

La base real `data/gastos.db` **no se guarda en Git**. El repositorio `casa-tareas` es público y el histórico de compras puede contener información personal.

La carpeta conserva solamente `data/.gitkeep`. Para ejecutar esta copia con los datos actuales hay que copiar la base existente al servidor en:

```text
gastos-comida/data/gastos.db
```

No borres la instalación actual ni muevas su base de datos hasta preparar la migración del contenedor. El archivo `compose.yml` incluido aquí es el original importado y, por ahora, no forma parte del `docker-compose.yml` principal de Casa Tareas.

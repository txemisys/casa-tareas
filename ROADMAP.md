# Roadmap de misión — Casa Tareas + Gastos

Última actualización: 2026-10-07

Este archivo existe para poder retomar la misión aunque se cierre el chat. La fuente de verdad del proyecto es este repositorio.

## Objetivo general

Mantener Casa Tareas como la aplicación principal del hogar, integrando Gastos de comida sin perder ninguna funcionalidad de Gastos y mejorando la experiencia conjunta.

Principios:
- Casa Tareas mantiene su estética y navegación principal.
- Gastos conserva tickets, filtros, gráficos, productos, métricas, listas y API.
- La integración usa la API interna; no se mezclan ni copian las bases de datos.
- Los cambios destructivos de Casa y Gastos siguen separados.
- Idiomas configurables desde Configuración: español, inglés y alemán.
- No traducir automáticamente contenido libre escrito por el usuario; sí traducir textos del sistema y datos iniciales conocidos.

## Estado actual

### Integración Casa + Gastos
- [x] Pestaña Gastos nativa en Casa.
- [x] Proxy same-origin /api/gastos/*.
- [x] Gastos independiente sigue disponible en :8000.
- [x] CRUD completo de tickets.
- [x] Filtros, resultados, métricas, productos y gráfico anual.
- [x] Catálogo de productos estable con product_id.
- [x] Vínculo Inventario Casa ↔ Producto Gastos.
- [x] Reposición automática al registrar ticket a través de Casa.
- [x] Tarea automática “Hacer la compra”.
- [x] Tareas bloqueadas por falta de material.
- [x] Resumen del hogar.
- [x] Plan de compra por supermercado.
- [x] Estimación de ahorro frente al supermercado habitual.
- [x] Reset independiente de Casa y Gastos.
- [x] Español, inglés y alemán configurables.
- [x] Traducción de textos del sistema, registros de actividad y datos iniciales conocidos.

### Limitaciones conocidas
- Una edición de ticket se reconcilia si contiene productos vinculados, pero eliminar un producto de un ticket o borrar el ticket no revierte automáticamente una reposición anterior, porque Casa no puede reconstruir con seguridad el stock físico previo.
- La reposición automática inmediata se ejecuta al crear tickets por el proxy de Casa; cambios hechos directamente en la UI standalone de Gastos no siempre se reflejan inmediatamente en Casa.
- El ahorro actual es por unidad/base y no un total real de cesta porque purchase_quantity sigue siendo texto libre.
- El gráfico integrado no tiene todavía toda la interacción/riqueza que podría ofrecer la versión standalone.
- En móvil, la navegación tiene muchas secciones y conviene seguir puliéndola.
- La internacionalización debe seguir auditándose visualmente; contenido libre del usuario no se traduce.

## Próximos hitos

### 1. Mejorar la calidad de la recomendación de supermercado — COMPLETADO
Objetivo: evitar recomendar una tienda por un precio antiguo o una única promoción.

Pendiente:
- [x] Calcular estadísticas recientes además del histórico completo.
- [x] Dar más peso a compras recientes.
- [x] Considerar número de muestras por supermercado.
- [x] Añadir nivel de confianza de la recomendación.
- [x] No recomendar cambio de supermercado si el ahorro esperado es insignificante.
- [x] Mantener compatibilidad con los campos actuales de /api/v1/products/{id}/stats.
- [x] Mostrar en UI por qué se recomienda una tienda.
- [x] Añadir tests de precios antiguos, promoción aislada, pocas muestras y empate.

Criterio de aceptación:
- Una tienda no debe ganar únicamente por una compra aislada muy antigua si existe histórico reciente suficiente en otra.
- La UI debe distinguir recomendación fuerte, moderada o débil.
- El ahorro mostrado debe usar el mismo criterio que la recomendación.

### 2. Estimación real de cesta y cantidades — COMPLETADO
Objetivo: pasar de €/u aproximado a un total de compra útil.

Pendiente:
- [x] Normalizar cantidades cuando sean interpretables con seguridad.
- [x] Soportar formatos claros como “2 unidades”, “3 botellas”, “1.5 kg”.
- [x] No inventar conversiones cuando las unidades sean ambiguas.
- [x] Conservar purchase_quantity original.
- [x] Mostrar total de cesta solo cuando haya cobertura suficiente.
- [x] Mostrar qué productos quedan fuera del cálculo.
- [x] Tests de cantidades y unidades.

### 3. Sincronización más profunda desde Gastos standalone — COMPLETADO
Objetivo: que Casa se actualice aunque un ticket se cree o edite directamente en :8000.

Opciones a evaluar:
- [x] Endpoint de reconciliación incremental.
- [x] Polling por último ticket/modificación.
- [x] Webhook interno. — descartado como innecesario por ahora; se usa polling incremental idempotente.
- [x] Reconciliar también PUT/edición de ticket.
- [x] Evitar dobles reposiciones o efectos repetidos.

### 4. Paridad y mejora del gráfico — COMPLETADO
- [x] Tooltips.
- [x] Valores al pasar el cursor.
- [x] Leyenda más clara.
- [x] Comparación entre usuarios.
- [x] Mejor experiencia móvil.
- [x] Verificar que ninguna función útil del gráfico standalone se pierde.

### 5. Pulido de navegación y UX — PRIORIDAD ACTUAL
- [ ] Botón principal contextual: Nueva tarea / Nuevo ticket / Nuevo producto según sección.
- [ ] Revisar navegación móvil con muchas pestañas.
- [ ] Atajos Inventario ↔ Gastos ↔ Plan de compra.
- [ ] Estados de carga/error homogéneos.
- [ ] Auditoría visual completa de español, inglés y alemán.

### 6. Personas compartidas
Objetivo futuro: evaluar si los usuarios/personas de Gastos deben vincularse con las personas de Casa sin romper históricos ni nombres existentes.
- [ ] Diseñar vínculo estable por ID.
- [ ] No fusionar por nombre de forma agresiva.
- [ ] Mantener compatibilidad con tickets históricos.

## Reglas de trabajo

Antes de mergear cambios relevantes:
1. Crear rama feature/fix desde main.
2. Añadir o actualizar tests.
3. Esperar CI verde.
4. Mergear a main solo cuando el cambio esté validado.
5. Subir versión de assets cuando cambie frontend para evitar caché.

No hacer:
- No copiar ni sobrescribir gastos.db.
- No borrar datos reales durante pruebas.
- No exponer secretos de .env.
- No desactivar la protección GASTOS_REQUIRE_EXISTING_DB.
- No hacer fuzzy matching agresivo de productos.
- No traducir automáticamente nombres/descripciones libres creados por el usuario.

## Despliegue habitual

```bash
cd ~/casa-tareas
git checkout main
git pull
sudo docker compose --profile gastos up -d --build casa-tareas gastos-comida
```

Después, recarga fuerte del navegador si cambia frontend:

```text
Ctrl + Shift + R
```

## Punto exacto para retomar

La siguiente tarea es el hito 5: pulir navegación y UX, empezando por botón principal contextual, navegación móvil y atajos entre Inventario, Gastos y Plan de compra.

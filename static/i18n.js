(function(){
"use strict";

/*
  Casa Tareas client-side i18n.
  Spanish remains the canonical UI source language. The renderer can keep
  producing Spanish strings while this layer translates visible UI text,
  dynamic activity entries, validation messages and dialogs consistently.
*/

var currentLanguage="es";
var supported={es:true,en:true,de:true};
var textSource=new WeakMap();
var attrSource=new WeakMap();

var EN={
"Tablero":"Dashboard","Tareas":"Tasks","Agenda":"Calendar","Áreas":"Areas","Personas":"People","Gastos":"Expenses","Historial":"History","Configuración":"Settings",
"Hoy":"Today","Próximamente":"Upcoming","Todas las tareas":"All tasks","Realizadas":"Completed","Sugeridas ahora":"Suggested now",
"Nueva tarea":"New task","Nueva persona":"New person","Nueva área":"New area","Nuevo evento":"New event","Nuevo producto":"New product","Nuevo ticket":"New receipt",
"Editar":"Edit","Eliminar":"Delete","Guardar":"Save","Cancelar":"Cancel","Cerrar":"Close","Restaurar":"Restore","Archivar":"Archive","Deshacer":"Undo","Reintentar":"Retry",
"Añadir":"Add","Sincronizar":"Sync","Sincronizar todos":"Sync all","Buscar":"Search","Limpiar":"Clear","Quitar":"Remove",
"Activa":"Active","Eliminada":"Deleted","Activo":"Active","Detenido":"Stopped","Automático":"Automatic","Manual":"Manual",
"Sin área":"No area","Sin responsable":"No owner","Sin responsable asignado":"No owner assigned","Sin estimar":"Not estimated","Sin fecha":"No date",
"Sin configurar":"Not configured","Configurado":"Configured","No configurado":"Not configured","Sin grupo seleccionado":"No group selected","Sin comunicación todavía":"No communication yet",
"Gestionado por .env / entorno":"Managed by .env / environment","Guardado en Casa Tareas":"Saved in Casa Tareas",
"Catálogo activo · usa + Hoy para añadir":"Active catalog · use + Today to add",
"Arrastra a Próximamente para quitar de Hoy":"Drag to Upcoming to remove from Today",
"Arrastra aquí desde Hoy para corregir una selección":"Drag here from Today to correct a selection",
"Arrastra una realización reversible a Hoy para corregirla":"Drag a reversible completion to Today to correct it",
"Nada pendiente para hoy.":"Nothing pending for today.","No hay nada próximo.":"Nothing upcoming.","No hay tareas activas.":"No active tasks.","Aún no hay tareas realizadas.":"No completed tasks yet.",
"Una cola pequeña para lo que toca ahora.":"A small queue for what needs doing now.",
"Lo que viene después, ordenado por fecha.":"What comes next, ordered by date.",
"Tareas y agenda doméstica en un mismo vistazo.":"Household tasks and calendar at a glance.",
"Catálogo maestro de tareas domésticas.":"Master catalog of household tasks.",
"Productos necesarios para hacer las tareas y una lista de compra agregada.":"Supplies needed for tasks and an aggregated shopping list.",
"Organiza responsabilidades, mueve tareas y pausa temporalmente ámbitos completos.":"Organize responsibilities, move tasks and temporarily pause whole areas.",
"Gestiona quién puede figurar como autor de una tarea.":"Manage who can be shown as the author of a task.",
"Eventos propios y calendarios externos en un mismo lugar.":"Your events and external calendars in one place.",
"Realizaciones y reparto de los últimos 30 días.":"Completions and distribution over the last 30 days.",
"Tareas recurrentes cerca de su ciclo. Nada entra en Hoy automáticamente.":"Recurring tasks close to their cycle. Nothing is added to Today automatically.",
"No hay tareas que necesiten atención ahora.":"No tasks need attention right now.",
"No hay sugerencias que quepan en ese tiempo con duración estimada.":"No suggestions fit that estimated duration.",
"Actividad reciente":"Recent activity","Desde tu última visita":"Since your last visit","Cambios realizados desde este navegador.":"Changes made from this browser.","Marcar como visto":"Mark as seen",
"Volver a Hoy":"Return to Today","Quitar de Hoy":"Remove from Today","Añadir a Hoy":"Add to Today","Hecha":"Done","Posponer":"Postpone","Mover":"Move",
"Elegir chat de Telegram":"Choose Telegram chat","Mover tarea":"Move task","Nueva fecha":"New date","¿Quién la hizo?":"Who did it?","Solo cambia esta aparición.":"Only changes this occurrence.",
"Si no aparece el grupo, envía /casa en él, espera unos segundos y vuelve a detectar.":"If the group does not appear, send /casa in it, wait a few seconds and detect again.",
"Volver a detectar":"Detect again","No se han encontrado chats recientes.":"No recent chats found.",
"Área de destino":"Destination area","Área de responsabilidad":"Responsibility area","Responsable total":"Overall owner","Heredar del área":"Inherit from area",
"Descripción":"Description","Categoría":"Category","Primera / próxima fecha":"First / next date","Fecha de anclaje":"Anchor date",
"Se considera terminada cuando…":"Considered complete when…","Notas de responsabilidad":"Responsibility notes","Productos necesarios":"Required supplies",
"Qué incluye":"What it includes","Tareas todavía no asignadas a un ámbito de responsabilidad.":"Tasks not yet assigned to a responsibility area.",
"Suelta aquí tareas de otra área":"Drop tasks from another area here","No hay áreas configuradas.":"No areas configured.","No hay áreas activas.":"No active areas.",
"Responsable inactivo:":"Inactive owner:","Todas las áreas de tareas están pausadas":"All task areas are paused",
"Vacaciones":"Vacation","Terminar vacaciones ahora":"End vacation now","La Agenda continúa activa.":"The Calendar remains active.",
"Las fechas se desplazarán solo por los días que habéis estado en vacaciones.":"Dates will move only by the number of days you were on vacation.",
"Inventario y Comprar":"Inventory & Shopping","Inventario":"Inventory","Comprar":"Shopping","Producto":"Product","Unidad":"Unit","Qué comprar":"What to buy","Estado":"Status",
"Producto correspondiente en Gastos":"Matching product in Expenses","Sin vincular":"Not linked","vinculado":"linked","sin vincular":"not linked","Gastos vinculado":"Expenses linked",
"Hay":"In stock","Poco":"Low","Falta":"Out","Repuesto":"Restocked","Quitar de Comprar":"Remove from Shopping",
"No falta ningún producto.":"No products are missing.","Todavía no hay productos.":"No products yet.","Añadido manualmente a Comprar.":"Manually added to Shopping.",
"No hay productos en Inventario. Puedes crearlos desde Tareas → Inventario y Comprar.":"There are no products in Inventory. You can create them from Tasks → Inventory & Shopping.",
"Plan de compra":"Shopping plan","Plan de compra por supermercado":"Shopping plan by supermarket","Cargando recomendaciones…":"Loading recommendations…","Calculando supermercados…":"Calculating supermarkets…",
"Sin recomendación":"No recommendation","Abrir inventario":"Open inventory","Ver compra":"View shopping","Ver en inventario":"View in inventory",
"Por comprar":"To buy","Ahorro estimado siguiendo las recomendaciones:":"Estimated saving following recommendations:","Basado en el precio medio del supermercado habitual; no es todavía un total real de cesta.":"Based on the average price at the usual supermarket; this is not yet a real basket total.",
"Comparación contra el precio medio del supermercado habitual para los productos con histórico comparable. No representa todavía el total real de la cesta.":"Comparison against the average price at the usual supermarket for products with comparable history. It does not yet represent the real basket total.",
"Funcionamiento":"Operation","Zona horaria":"Time zone","Idioma":"Language","Español":"Spanish","Inglés":"English","Alemán":"German",
"Revisar recordatorios Telegram cada":"Check Telegram reminders every","Sincronizar calendarios cada":"Sync calendars every","Máximo por adjunto":"Maximum per attachment",
"segundos":"seconds","minutos":"minutes","Guardar ajustes":"Save settings",
"Estos cambios se aplican en caliente. El puerto HTTP sigue siendo una opción de Docker y no se cambia desde la aplicación.":"These changes apply immediately. The HTTP port remains a Docker option and is not changed from the application.",
"Ajustes de Casa Tareas sin editar archivos del servidor.":"Casa Tareas settings without editing server files.",
"El token nunca vuelve a mostrarse después de guardarlo.":"The token is never shown again after it is saved.",
"Origen del token":"Token source","Bot":"Bot","Grupo":"Group","Worker":"Worker","Último contacto":"Last contact",
"Pega aquí el token de BotFather":"Paste the BotFather token here","Pega un token nuevo para sustituir el actual":"Paste a new token to replace the current one",
"Guardar y validar":"Save and validate","Sustituir":"Replace","Eliminar token guardado":"Delete saved token","Enviar prueba":"Send test","Cambiar grupo":"Change group","Desconectar grupo":"Disconnect group","Detectar grupos":"Detect groups",
"Avisos y control rápido de Casa Tareas desde el grupo.":"Alerts and quick control of Casa Tareas from the group.",
"Solo este chat puede modificar Casa Tareas.":"Only this chat can modify Casa Tareas.",
"Para conectarlo a un grupo: añade el bot al grupo, escribe /casa, espera unos segundos y pulsa Detectar grupos.":"To connect it to a group: add the bot to the group, type /casa, wait a few seconds and press Detect groups.",
"Si el token se guarda aquí queda dentro de data/chores.db; trata las copias de seguridad de data/ como información sensible.":"If the token is saved here it is stored in data/chores.db; treat backups of data/ as sensitive information.",
"Este token viene de TELEGRAM_BOT_TOKEN. Para administrarlo desde esta pantalla, elimina esa variable de .env y recrea el contenedor una única vez.":"This token comes from TELEGRAM_BOT_TOKEN. To manage it from this screen, remove that variable from .env and recreate the container once.",
"Gastos de comida":"Food expenses","Conecta Casa Tareas con el histórico de compras mediante la API interna.":"Connect Casa Tareas to purchase history through the internal API.",
"URL del servicio":"Service URL","Probar conexión":"Test connection","Desconectar":"Disconnect","Última prueba correcta":"Last successful test","Último error":"Last error",
"En el despliegue conjunto la URL interna es http://gastos-comida:8000. El servicio está protegido para no arrancar con una base vacía: antes de activarlo hay que apuntar GASTOS_DATA_DIR a la carpeta que contiene tu gastos.db real.":"In the combined deployment the internal URL is http://gastos-comida:8000. The service is protected from starting with an empty database: before enabling it, point GASTOS_DATA_DIR to the folder containing your real gastos.db.",
"Diagnóstico":"Diagnostics","Versión":"Version","Calendarios externos":"External calendars","Documentos":"Documents","Datos persistentes":"Persistent data","Acceso":"Access",
"Casa Tareas no tiene autenticación de usuarios. Mantén la aplicación en una red privada de confianza, especialmente ahora que puede guardar un token de Telegram.":"Casa Tareas has no user authentication. Keep the application on a trusted private network, especially now that it can store a Telegram token.",
"Zona peligrosa":"Danger zone","Estas acciones borran datos de forma permanente y no se pueden deshacer. Casa Tareas y Gastos se reinician por separado.":"These actions permanently delete data and cannot be undone. Casa Tareas and Expenses are reset separately.",
"Borrar datos de Casa Tareas":"Delete Casa Tareas data","Borrar datos de Gastos":"Delete Expenses data",
"Casa Tareas: elimina tareas, áreas, personas, agenda, inventario, historial y adjuntos, pero conserva la configuración de la aplicación. Gastos: elimina tickets, líneas, productos y listas auxiliares, sin tocar Casa Tareas.":"Casa Tareas: deletes tasks, areas, people, calendar, inventory, history and attachments, while preserving application settings. Expenses: deletes receipts, lines, products and auxiliary lists without touching Casa Tareas.",
"Borrar base de Gastos":"Delete Expenses database","Esta acción no se puede deshacer.":"This action cannot be undone.","No, cancelar":"No, cancel","Sí, borrar":"Yes, delete",
"Se eliminarán definitivamente todos los tickets, artículos, productos y datos históricos de Gastos. Casa Tareas no se borrará.":"All receipts, items, products and historical Expenses data will be permanently deleted. Casa Tareas will not be deleted.",
"Se eliminarán definitivamente tareas, áreas, personas, agenda, inventario, historial y adjuntos. La configuración general se conservará y los ejemplos no volverán a crearse.":"Tasks, areas, people, calendar, inventory, history and attachments will be permanently deleted. General settings will be preserved and sample data will not be recreated.",
"Calendarios externos":"External calendars","Suscripciones iCal de solo lectura. La URL completa no se muestra porque puede contener un token privado.":"Read-only iCal subscriptions. The full URL is not shown because it may contain a private token.",
"Todavía sin sincronizar":"Not synced yet","Sincronizar todos":"Sync all","Calendario externo":"External calendar",
"Documentos":"Documents","PDF, imágenes, facturas, garantías, contratos o manuales. Máximo 20 MB por archivo.":"PDFs, images, invoices, warranties, contracts or manuals. Maximum 20 MB per file.",
"Sin documentos adjuntos.":"No attached documents.","Subir documento":"Upload document",
"Avisos del navegador":"Browser notifications","Próximos":"Upcoming","Pasados":"Past","Visto":"Seen","Todo el día":"All day","A la hora":"At the time",
"No hay eventos próximos.":"No upcoming events.","No hay tareas futuras.":"No future tasks.","Todavía no hay realizaciones.":"No completions yet.",
"Avisos pendientes":"Pending alerts","Próximos eventos":"Upcoming events",
"Resumen":"Summary","Tickets":"Receipts","Análisis":"Analysis","Productos":"Products","Listas":"Lists","Artículo":"Item","Artículos":"Items","Usuario":"User","Usuarios":"Users",
"Supermercado":"Supermarket","Fecha":"Date","Cantidad":"Quantity","Precio":"Price","Precio neto":"Net price","Descuento":"Discount","Total":"Total","Resultados":"Results",
"Desde":"From","Hasta":"To","Año gráfica":"Chart year","Filtros":"Filters","Consultas y filtros":"Queries and filters",
"Filtra por artículo, usuario, supermercado y fechas.":"Filter by item, user, supermarket and dates.",
"Alta, edición y eliminación de compras completas.":"Create, edit and delete complete purchases.",
"Últimos tickets":"Latest receipts","Las compras más recientes.":"Most recent purchases.","Ver todos":"View all",
"Evolución anual":"Yearly trend","Gráfica anual":"Yearly chart","Total mensual y desglose por usuario.":"Monthly total and breakdown by user.",
"Gasto mensual del año seleccionado y desglose por usuario.":"Monthly spending for the selected year and breakdown by user.",
"Estado":"Status","Datos disponibles en Gastos.":"Data available in Expenses.","Líneas":"Lines",
"Precio unitario medio":"Average unit price","Mejor precio histórico":"Best historical price","Último cambio":"Latest change",
"Supermercado recomendado":"Recommended supermarket","Supermercado habitual":"Usual supermarket","Comparativa por supermercado":"Comparison by supermarket",
"Compras":"Purchases","Última compra":"Last purchase","Gasto total":"Total spend","Histórico de precio y supermercados.":"Price and supermarket history.",
"Sin precio histórico":"No price history","Sin datos suficientes":"Not enough data","Media":"Average","Último":"Latest",
"Limpiar desplegables":"Clean dropdowns","Equivale a la función de limpieza de la aplicación Gastos original.":"Equivalent to the cleanup function in the original Expenses app.",
"Oculta errores de los desplegables sin borrar el histórico.":"Hides erroneous dropdown entries without deleting history.",
"Opción ocultada de las listas":"Option hidden from lists","Selecciona algún filtro para ver el listado detallado.":"Select a filter to see the detailed list.",
"Sin resultados para los filtros seleccionados.":"No results for the selected filters.","No hay datos para la gráfica.":"No chart data.","No hay productos que coincidan.":"No matching products.",
"No hay tickets.":"No receipts.","Todavía no hay tickets.":"No receipts yet.","La lista de compra está vacía.":"The shopping list is empty.","Cargando…":"Loading…",
"No se pudo cargar Gastos.":"Expenses could not be loaded.","Total entre fechas por usuario":"Total between dates by user",
"Editar ticket":"Edit receipt","Quitar":"Remove","Importado desde Gastos":"Imported from Expenses","Producto añadido al Inventario":"Product added to Inventory",
"Ticket creado":"Receipt created","Ticket actualizado":"Receipt updated","Ticket eliminado":"Receipt deleted",
"Alimentación":"Food","General":"General","Comida":"Food","Compra":"Shopping","Gestión":"Management","Ejecución":"Execution",
"Bloqueada por material":"Blocked by missing supply","Hacer la compra":"Do the shopping","Tarea automática generada desde Inventario y Comprar.":"Automatic task generated from Inventory & Shopping.",
"Planificación, compra, cocina y gestión de alimentos.":"Planning, shopping, cooking and food management.",
"Lavado, sábanas, toallas y productos textiles.":"Laundry, sheets, towels and textile products.",
"Limpieza, consumibles y mantenimiento doméstico.":"Cleaning, consumables and household maintenance.",
"Gestión y mantenimiento del piso Fanalwegle.":"Management and maintenance of the Fanalwegle apartment.",
"Gestión y mantenimiento del piso Im Gapetsch.":"Management and maintenance of the Im Gapetsch apartment.",
"Gestión, mantenimiento y asuntos relacionados con Casa de Cosi.":"Management, maintenance and matters related to Cosi's house.",
"Mantenimiento, seguros, revisiones y gestiones de vehículos.":"Vehicle maintenance, insurance, inspections and administration.",
"Seguros médicos, facturas, reembolsos y gestiones de Krankenkassen.":"Health insurance, bills, reimbursements and Krankenkassen administration.",
"Material pendiente":"Supply pending","tareas por material":"tasks blocked by supplies","productos":"products","este mes":"this month",
"tareas · 30 días":"tasks · 30 days","Sin comparación":"No comparison"
};

var DE={
"Tablero":"Übersicht","Tareas":"Aufgaben","Agenda":"Kalender","Áreas":"Bereiche","Personas":"Personen","Gastos":"Ausgaben","Historial":"Verlauf","Configuración":"Einstellungen",
"Hoy":"Heute","Próximamente":"Demnächst","Todas las tareas":"Alle Aufgaben","Realizadas":"Erledigt","Sugeridas ahora":"Jetzt vorgeschlagen",
"Nueva tarea":"Neue Aufgabe","Nueva persona":"Neue Person","Nueva área":"Neuer Bereich","Nuevo evento":"Neuer Termin","Nuevo producto":"Neues Produkt","Nuevo ticket":"Neuer Beleg",
"Editar":"Bearbeiten","Eliminar":"Löschen","Guardar":"Speichern","Cancelar":"Abbrechen","Cerrar":"Schließen","Restaurar":"Wiederherstellen","Archivar":"Archivieren","Deshacer":"Rückgängig","Reintentar":"Erneut versuchen",
"Añadir":"Hinzufügen","Sincronizar":"Synchronisieren","Sincronizar todos":"Alle synchronisieren","Buscar":"Suchen","Limpiar":"Zurücksetzen","Quitar":"Entfernen",
"Activa":"Aktiv","Eliminada":"Gelöscht","Activo":"Aktiv","Detenido":"Gestoppt","Automático":"Automatisch","Manual":"Manuell",
"Sin área":"Ohne Bereich","Sin responsable":"Ohne Verantwortlichen","Sin responsable asignado":"Kein Verantwortlicher zugewiesen","Sin estimar":"Nicht geschätzt","Sin fecha":"Kein Datum",
"Sin configurar":"Nicht konfiguriert","Configurado":"Konfiguriert","No configurado":"Nicht konfiguriert","Sin grupo seleccionado":"Keine Gruppe ausgewählt","Sin comunicación todavía":"Noch keine Kommunikation",
"Gestionado por .env / entorno":"Über .env / Umgebung verwaltet","Guardado en Casa Tareas":"In Casa Tareas gespeichert",
"Catálogo activo · usa + Hoy para añadir":"Aktiver Katalog · mit + Heute hinzufügen",
"Arrastra a Próximamente para quitar de Hoy":"Nach Demnächst ziehen, um aus Heute zu entfernen",
"Arrastra aquí desde Hoy para corregir una selección":"Von Heute hierher ziehen, um eine Auswahl zu korrigieren",
"Arrastra una realización reversible a Hoy para corregirla":"Eine rückgängig machbare Erledigung nach Heute ziehen, um sie zu korrigieren",
"Nada pendiente para hoy.":"Heute ist nichts offen.","No hay nada próximo.":"Nichts demnächst.","No hay tareas activas.":"Keine aktiven Aufgaben.","Aún no hay tareas realizadas.":"Noch keine erledigten Aufgaben.",
"Una cola pequeña para lo que toca ahora.":"Eine kleine Liste für das, was jetzt ansteht.",
"Lo que viene después, ordenado por fecha.":"Was als Nächstes kommt, nach Datum sortiert.",
"Tareas y agenda doméstica en un mismo vistazo.":"Haushaltsaufgaben und Kalender auf einen Blick.",
"Catálogo maestro de tareas domésticas.":"Hauptkatalog der Haushaltsaufgaben.",
"Productos necesarios para hacer las tareas y una lista de compra agregada.":"Benötigte Produkte für Aufgaben und eine zusammengefasste Einkaufsliste.",
"Organiza responsabilidades, mueve tareas y pausa temporalmente ámbitos completos.":"Verantwortlichkeiten organisieren, Aufgaben verschieben und ganze Bereiche vorübergehend pausieren.",
"Gestiona quién puede figurar como autor de una tarea.":"Verwalte, wer als Autor einer Aufgabe erscheinen kann.",
"Eventos propios y calendarios externos en un mismo lugar.":"Eigene Termine und externe Kalender an einem Ort.",
"Realizaciones y reparto de los últimos 30 días.":"Erledigungen und Verteilung der letzten 30 Tage.",
"Tareas recurrentes cerca de su ciclo. Nada entra en Hoy automáticamente.":"Wiederkehrende Aufgaben nahe an ihrem Zyklus. Nichts wird automatisch zu Heute hinzugefügt.",
"No hay tareas que necesiten atención ahora.":"Derzeit benötigen keine Aufgaben Aufmerksamkeit.",
"No hay sugerencias que quepan en ese tiempo con duración estimada.":"Keine Vorschläge passen in diese geschätzte Dauer.",
"Actividad reciente":"Letzte Aktivität","Desde tu última visita":"Seit deinem letzten Besuch","Cambios realizados desde este navegador.":"Änderungen aus diesem Browser.","Marcar como visto":"Als gesehen markieren",
"Volver a Hoy":"Zurück zu Heute","Quitar de Hoy":"Aus Heute entfernen","Añadir a Hoy":"Zu Heute hinzufügen","Hecha":"Erledigt","Posponer":"Verschieben","Mover":"Verschieben",
"Elegir chat de Telegram":"Telegram-Chat auswählen","Mover tarea":"Aufgabe verschieben","Nueva fecha":"Neues Datum","¿Quién la hizo?":"Wer hat sie erledigt?","Solo cambia esta aparición.":"Ändert nur dieses Vorkommen.",
"Si no aparece el grupo, envía /casa en él, espera unos segundos y vuelve a detectar.":"Wenn die Gruppe nicht erscheint, sende /casa darin, warte einige Sekunden und suche erneut.",
"Volver a detectar":"Erneut suchen","No se han encontrado chats recientes.":"Keine aktuellen Chats gefunden.",
"Área de destino":"Zielbereich","Área de responsabilidad":"Verantwortungsbereich","Responsable total":"Gesamtverantwortung","Heredar del área":"Vom Bereich übernehmen",
"Descripción":"Beschreibung","Categoría":"Kategorie","Primera / próxima fecha":"Erstes / nächstes Datum","Fecha de anclaje":"Ankerdatum",
"Se considera terminada cuando…":"Gilt als erledigt, wenn…","Notas de responsabilidad":"Hinweise zur Verantwortung","Productos necesarios":"Benötigte Produkte",
"Qué incluye":"Was enthalten ist","Tareas todavía no asignadas a un ámbito de responsabilidad.":"Aufgaben, die noch keinem Verantwortungsbereich zugewiesen sind.",
"Suelta aquí tareas de otra área":"Aufgaben aus einem anderen Bereich hier ablegen","No hay áreas configuradas.":"Keine Bereiche konfiguriert.","No hay áreas activas.":"Keine aktiven Bereiche.",
"Responsable inactivo:":"Inaktiver Verantwortlicher:","Todas las áreas de tareas están pausadas":"Alle Aufgabenbereiche sind pausiert",
"Vacaciones":"Urlaub","Terminar vacaciones ahora":"Urlaub jetzt beenden","La Agenda continúa activa.":"Der Kalender bleibt aktiv.",
"Las fechas se desplazarán solo por los días que habéis estado en vacaciones.":"Die Daten werden nur um die tatsächlichen Urlaubstage verschoben.",
"Inventario y Comprar":"Inventar & Einkauf","Inventario":"Inventar","Comprar":"Einkaufen","Producto":"Produkt","Unidad":"Einheit","Qué comprar":"Was kaufen","Estado":"Status",
"Producto correspondiente en Gastos":"Passendes Produkt in Ausgaben","Sin vincular":"Nicht verknüpft","vinculado":"verknüpft","sin vincular":"nicht verknüpft","Gastos vinculado":"Ausgaben verknüpft",
"Hay":"Vorhanden","Poco":"Wenig","Falta":"Fehlt","Repuesto":"Nachgefüllt","Quitar de Comprar":"Aus Einkauf entfernen",
"No falta ningún producto.":"Keine Produkte fehlen.","Todavía no hay productos.":"Noch keine Produkte.","Añadido manualmente a Comprar.":"Manuell zur Einkaufsliste hinzugefügt.",
"No hay productos en Inventario. Puedes crearlos desde Tareas → Inventario y Comprar.":"Im Inventar sind keine Produkte. Du kannst sie unter Aufgaben → Inventar & Einkauf anlegen.",
"Plan de compra":"Einkaufsplan","Plan de compra por supermercado":"Einkaufsplan nach Supermarkt","Cargando recomendaciones…":"Empfehlungen werden geladen…","Calculando supermercados…":"Supermärkte werden berechnet…",
"Sin recomendación":"Keine Empfehlung","Abrir inventario":"Inventar öffnen","Ver compra":"Einkauf ansehen","Ver en inventario":"Im Inventar ansehen",
"Por comprar":"Zu kaufen","Ahorro estimado siguiendo las recomendaciones:":"Geschätzte Ersparnis nach Empfehlungen:","Basado en el precio medio del supermercado habitual; no es todavía un total real de cesta.":"Basierend auf dem Durchschnittspreis im üblichen Supermarkt; dies ist noch kein echter Warenkorb-Gesamtpreis.",
"Comparación contra el precio medio del supermercado habitual para los productos con histórico comparable. No representa todavía el total real de la cesta.":"Vergleich mit dem Durchschnittspreis im üblichen Supermarkt für Produkte mit vergleichbarer Historie. Dies entspricht noch nicht dem tatsächlichen Warenkorb-Gesamtpreis.",
"Funcionamiento":"Betrieb","Zona horaria":"Zeitzone","Idioma":"Sprache","Español":"Spanisch","Inglés":"Englisch","Alemán":"Deutsch",
"Revisar recordatorios Telegram cada":"Telegram-Erinnerungen prüfen alle","Sincronizar calendarios cada":"Kalender synchronisieren alle","Máximo por adjunto":"Maximal pro Anhang",
"segundos":"Sekunden","minutos":"Minuten","Guardar ajustes":"Einstellungen speichern",
"Estos cambios se aplican en caliente. El puerto HTTP sigue siendo una opción de Docker y no se cambia desde la aplicación.":"Diese Änderungen werden sofort übernommen. Der HTTP-Port bleibt eine Docker-Option und wird nicht in der Anwendung geändert.",
"Ajustes de Casa Tareas sin editar archivos del servidor.":"Casa-Tareas-Einstellungen ohne Serverdateien zu bearbeiten.",
"El token nunca vuelve a mostrarse después de guardarlo.":"Der Token wird nach dem Speichern nie wieder angezeigt.",
"Origen del token":"Token-Quelle","Bot":"Bot","Grupo":"Gruppe","Worker":"Worker","Último contacto":"Letzter Kontakt",
"Pega aquí el token de BotFather":"BotFather-Token hier einfügen","Pega un token nuevo para sustituir el actual":"Neuen Token einfügen, um den aktuellen zu ersetzen",
"Guardar y validar":"Speichern und prüfen","Sustituir":"Ersetzen","Eliminar token guardado":"Gespeicherten Token löschen","Enviar prueba":"Test senden","Cambiar grupo":"Gruppe wechseln","Desconectar grupo":"Gruppe trennen","Detectar grupos":"Gruppen erkennen",
"Avisos y control rápido de Casa Tareas desde el grupo.":"Benachrichtigungen und Schnellsteuerung von Casa Tareas über die Gruppe.",
"Solo este chat puede modificar Casa Tareas.":"Nur dieser Chat kann Casa Tareas ändern.",
"Para conectarlo a un grupo: añade el bot al grupo, escribe /casa, espera unos segundos y pulsa Detectar grupos.":"Zum Verbinden mit einer Gruppe: Bot hinzufügen, /casa schreiben, einige Sekunden warten und Gruppen erkennen drücken.",
"Si el token se guarda aquí queda dentro de data/chores.db; trata las copias de seguridad de data/ como información sensible.":"Wenn der Token hier gespeichert wird, liegt er in data/chores.db; behandle Sicherungen von data/ als vertraulich.",
"Este token viene de TELEGRAM_BOT_TOKEN. Para administrarlo desde esta pantalla, elimina esa variable de .env y recrea el contenedor una única vez.":"Dieser Token kommt aus TELEGRAM_BOT_TOKEN. Um ihn hier zu verwalten, entferne die Variable aus .env und erstelle den Container einmal neu.",
"Gastos de comida":"Lebensmittelausgaben","Conecta Casa Tareas con el histórico de compras mediante la API interna.":"Casa Tareas über die interne API mit der Einkaufshistorie verbinden.",
"URL del servicio":"Service-URL","Probar conexión":"Verbindung testen","Desconectar":"Trennen","Última prueba correcta":"Letzter erfolgreicher Test","Último error":"Letzter Fehler",
"En el despliegue conjunto la URL interna es http://gastos-comida:8000. El servicio está protegido para no arrancar con una base vacía: antes de activarlo hay que apuntar GASTOS_DATA_DIR a la carpeta que contiene tu gastos.db real.":"Im kombinierten Betrieb ist die interne URL http://gastos-comida:8000. Der Dienst startet nicht mit einer leeren Datenbank: vor dem Aktivieren muss GASTOS_DATA_DIR auf den Ordner mit der echten gastos.db zeigen.",
"Diagnóstico":"Diagnose","Versión":"Version","Calendarios externos":"Externe Kalender","Documentos":"Dokumente","Datos persistentes":"Persistente Daten","Acceso":"Zugriff",
"Casa Tareas no tiene autenticación de usuarios. Mantén la aplicación en una red privada de confianza, especialmente ahora que puede guardar un token de Telegram.":"Casa Tareas hat keine Benutzeranmeldung. Halte die Anwendung in einem vertrauenswürdigen privaten Netzwerk, besonders weil sie einen Telegram-Token speichern kann.",
"Zona peligrosa":"Gefahrenzone","Estas acciones borran datos de forma permanente y no se pueden deshacer. Casa Tareas y Gastos se reinician por separado.":"Diese Aktionen löschen Daten dauerhaft und können nicht rückgängig gemacht werden. Casa Tareas und Ausgaben werden getrennt zurückgesetzt.",
"Borrar datos de Casa Tareas":"Casa-Tareas-Daten löschen","Borrar datos de Gastos":"Ausgabendaten löschen",
"Casa Tareas: elimina tareas, áreas, personas, agenda, inventario, historial y adjuntos, pero conserva la configuración de la aplicación. Gastos: elimina tickets, líneas, productos y listas auxiliares, sin tocar Casa Tareas.":"Casa Tareas: löscht Aufgaben, Bereiche, Personen, Kalender, Inventar, Verlauf und Anhänge, behält aber die Anwendungseinstellungen. Ausgaben: löscht Belege, Positionen, Produkte und Hilfslisten, ohne Casa Tareas zu verändern.",
"Borrar base de Gastos":"Ausgabendatenbank löschen","Esta acción no se puede deshacer.":"Diese Aktion kann nicht rückgängig gemacht werden.","No, cancelar":"Nein, abbrechen","Sí, borrar":"Ja, löschen",
"Se eliminarán definitivamente todos los tickets, artículos, productos y datos históricos de Gastos. Casa Tareas no se borrará.":"Alle Belege, Artikel, Produkte und historischen Ausgabendaten werden dauerhaft gelöscht. Casa Tareas wird nicht gelöscht.",
"Se eliminarán definitivamente tareas, áreas, personas, agenda, inventario, historial y adjuntos. La configuración general se conservará y los ejemplos no volverán a crearse.":"Aufgaben, Bereiche, Personen, Kalender, Inventar, Verlauf und Anhänge werden dauerhaft gelöscht. Allgemeine Einstellungen bleiben erhalten und Beispieldaten werden nicht neu erstellt.",
"Calendarios externos":"Externe Kalender","Suscripciones iCal de solo lectura. La URL completa no se muestra porque puede contener un token privado.":"Schreibgeschützte iCal-Abonnements. Die vollständige URL wird nicht angezeigt, da sie einen privaten Token enthalten kann.",
"Todavía sin sincronizar":"Noch nicht synchronisiert","Sincronizar todos":"Alle synchronisieren","Calendario externo":"Externer Kalender",
"Documentos":"Dokumente","PDF, imágenes, facturas, garantías, contratos o manuales. Máximo 20 MB por archivo.":"PDFs, Bilder, Rechnungen, Garantien, Verträge oder Handbücher. Maximal 20 MB pro Datei.",
"Sin documentos adjuntos.":"Keine angehängten Dokumente.","Subir documento":"Dokument hochladen",
"Avisos del navegador":"Browser-Benachrichtigungen","Próximos":"Bevorstehend","Pasados":"Vergangen","Visto":"Gesehen","Todo el día":"Ganztägig","A la hora":"Zum Zeitpunkt",
"No hay eventos próximos.":"Keine bevorstehenden Termine.","No hay tareas futuras.":"Keine zukünftigen Aufgaben.","Todavía no hay realizaciones.":"Noch keine Erledigungen.",
"Avisos pendientes":"Ausstehende Benachrichtigungen","Próximos eventos":"Bevorstehende Termine",
"Resumen":"Übersicht","Tickets":"Belege","Análisis":"Analyse","Productos":"Produkte","Listas":"Listen","Artículo":"Artikel","Artículos":"Artikel","Usuario":"Benutzer","Usuarios":"Benutzer",
"Supermercado":"Supermarkt","Fecha":"Datum","Cantidad":"Menge","Precio":"Preis","Precio neto":"Nettopreis","Descuento":"Rabatt","Total":"Summe","Resultados":"Ergebnisse",
"Desde":"Von","Hasta":"Bis","Año gráfica":"Diagrammjahr","Filtros":"Filter","Consultas y filtros":"Abfragen und Filter",
"Filtra por artículo, usuario, supermercado y fechas.":"Nach Artikel, Benutzer, Supermarkt und Datum filtern.",
"Alta, edición y eliminación de compras completas.":"Vollständige Einkäufe anlegen, bearbeiten und löschen.",
"Últimos tickets":"Letzte Belege","Las compras más recientes.":"Die letzten Einkäufe.","Ver todos":"Alle anzeigen",
"Evolución anual":"Jahresentwicklung","Gráfica anual":"Jahresdiagramm","Total mensual y desglose por usuario.":"Monatssumme und Aufschlüsselung nach Benutzer.",
"Gasto mensual del año seleccionado y desglose por usuario.":"Monatliche Ausgaben des gewählten Jahres und Aufschlüsselung nach Benutzer.",
"Estado":"Status","Datos disponibles en Gastos.":"Verfügbare Daten in Ausgaben.","Líneas":"Positionen",
"Precio unitario medio":"Durchschnittlicher Stückpreis","Mejor precio histórico":"Historisch bester Preis","Último cambio":"Letzte Änderung",
"Supermercado recomendado":"Empfohlener Supermarkt","Supermercado habitual":"Üblicher Supermarkt","Comparativa por supermercado":"Vergleich nach Supermarkt",
"Compras":"Einkäufe","Última compra":"Letzter Einkauf","Gasto total":"Gesamtausgaben","Histórico de precio y supermercados.":"Preis- und Supermarkthistorie.",
"Sin precio histórico":"Keine Preishistorie","Sin datos suficientes":"Nicht genügend Daten","Media":"Durchschnitt","Último":"Letzter",
"Limpiar desplegables":"Dropdowns bereinigen","Equivale a la función de limpieza de la aplicación Gastos original.":"Entspricht der Bereinigungsfunktion der ursprünglichen Ausgaben-App.",
"Oculta errores de los desplegables sin borrar el histórico.":"Blendet fehlerhafte Dropdown-Einträge aus, ohne die Historie zu löschen.",
"Opción ocultada de las listas":"Option aus Listen ausgeblendet","Selecciona algún filtro para ver el listado detallado.":"Wähle einen Filter, um die Detailansicht zu sehen.",
"Sin resultados para los filtros seleccionados.":"Keine Ergebnisse für die gewählten Filter.","No hay datos para la gráfica.":"Keine Diagrammdaten.","No hay productos que coincidan.":"Keine passenden Produkte.",
"No hay tickets.":"Keine Belege.","Todavía no hay tickets.":"Noch keine Belege.","La lista de compra está vacía.":"Die Einkaufsliste ist leer.","Cargando…":"Lädt…",
"No se pudo cargar Gastos.":"Ausgaben konnten nicht geladen werden.","Total entre fechas por usuario":"Summe zwischen Datumsangaben pro Benutzer",
"Editar ticket":"Beleg bearbeiten","Quitar":"Entfernen","Importado desde Gastos":"Aus Ausgaben importiert","Producto añadido al Inventario":"Produkt zum Inventar hinzugefügt",
"Ticket creado":"Beleg erstellt","Ticket actualizado":"Beleg aktualisiert","Ticket eliminado":"Beleg gelöscht",
"Alimentación":"Lebensmittel","General":"Allgemein","Comida":"Essen","Compra":"Einkauf","Gestión":"Verwaltung","Ejecución":"Ausführung",
"Bloqueada por material":"Durch fehlendes Material blockiert","Hacer la compra":"Einkaufen gehen","Tarea automática generada desde Inventario y Comprar.":"Automatische Aufgabe aus Inventar & Einkauf.",
"Planificación, compra, cocina y gestión de alimentos.":"Planung, Einkauf, Kochen und Lebensmittelverwaltung.",
"Lavado, sábanas, toallas y productos textiles.":"Wäsche, Bettwäsche, Handtücher und Textilprodukte.",
"Limpieza, consumibles y mantenimiento doméstico.":"Reinigung, Verbrauchsmaterial und Haushaltswartung.",
"Gestión y mantenimiento del piso Fanalwegle.":"Verwaltung und Instandhaltung der Wohnung Fanalwegle.",
"Gestión y mantenimiento del piso Im Gapetsch.":"Verwaltung und Instandhaltung der Wohnung Im Gapetsch.",
"Gestión, mantenimiento y asuntos relacionados con Casa de Cosi.":"Verwaltung, Instandhaltung und Angelegenheiten rund um Cosis Haus.",
"Mantenimiento, seguros, revisiones y gestiones de vehículos.":"Fahrzeugwartung, Versicherungen, Inspektionen und Verwaltung.",
"Seguros médicos, facturas, reembolsos y gestiones de Krankenkassen.":"Krankenversicherung, Rechnungen, Erstattungen und Krankenkassen-Verwaltung.",
"Material pendiente":"Material fehlt","tareas por material":"durch Material blockierte Aufgaben","productos":"Produkte","este mes":"diesen Monat",
"tareas · 30 días":"Aufgaben · 30 Tage","Sin comparación":"Kein Vergleich"
};


Object.assign(EN,{
"Resumen del hogar":"Household summary","Tareas, compra e impacto de Gastos en un solo vistazo.":"Tasks, shopping and Expenses impact at a glance.",
"Gasto del mes":"Monthly spending","Bloqueadas":"Blocked","Abrir Gastos":"Open Expenses","Activar vacaciones":"Start vacation",
"Modo vacaciones":"Vacation mode","Modo vacaciones activo":"Vacation mode active","Pausa temporalmente las tareas sin ocultar reuniones, citas ni vencimientos de la Agenda.":"Temporarily pause tasks without hiding meetings, appointments or Calendar deadlines.",
"Las tareas se ocultan de Hoy, Próximamente y Sugeridas. La Agenda continúa funcionando.":"Tasks are hidden from Today, Upcoming and Suggested. The Calendar remains active.",
"Fecha de regreso":"Return date","Áreas que deben seguir activas":"Areas that should remain active","Útil para pisos en alquiler, Krankenkassen u otros asuntos que deban seguir visibles.":"Useful for rental apartments, Krankenkassen or other matters that should remain visible.",
"Continuar ciclo · vacaciones no cuentan":"Continue cycle · vacation does not count","Continuar ciclo · pausa no cuenta":"Continue cycle · pause does not count","Mantener calendario original":"Keep original schedule",
"Cada X días":"Every X days","Cada X días desde última vez":"Every X days since last time","Calendario fijo":"Fixed calendar","Duración estimada":"Estimated duration",
"Responsable de esta tarea":"Owner of this task","La responsabilidad puede heredarse del área o sobrescribirse para esta tarea.":"Responsibility can be inherited from the area or overridden for this task.",
"Quien sea responsable se encarga de detectar, planificar, ejecutar o coordinar y cerrar lo necesario.":"The owner is responsible for identifying, planning, carrying out or coordinating, and closing what is needed.",
"Nombre del área":"Area name","Área opcional":"Optional area","Título":"Title","Fecha y hora":"Date and time","Documentación que llevar, dirección, temas a tratar…":"Documents to bring, address, topics to discuss…",
"Ej. Limpiador de baño":"E.g. bathroom cleaner","Ej. botella, paquete":"E.g. bottle, pack","Ej. encimera y fregadero limpios, basura revisada y productos guardados":"E.g. worktop and sink clean, rubbish checked and products put away",
"Ej. incluye comprobar consumibles y decidir cuándo hacerlo":"E.g. includes checking supplies and deciding when to do it","Ej. planificación, compras, ejecución y reposición de consumibles":"E.g. planning, shopping, execution and replenishing supplies",
"Usa Hay / Poco / Falta. Si lo vinculas con Gastos, una compra registrada puede marcarlo automáticamente como repuesto.":"Use In stock / Low / Out. If linked to Expenses, a recorded purchase can automatically mark it as restocked.",
"Al registrar un ticket con este producto se marcará como Hay y saldrá de Comprar.":"When a receipt containing this product is recorded, it will be marked In stock and removed from Shopping.",
"Cargando catálogo de Gastos…":"Loading Expenses catalog…","Gastos no configurado":"Expenses not configured","No se pudo cargar Gastos":"Could not load Expenses",
"No se pudo cargar Casa Tareas":"Could not load Casa Tareas","El servidor responde, pero el navegador no pudo leer correctamente la API.":"The server responds, but the browser could not read the API correctly.",
"Esta sesión contiene":"This session contains","un parámetro que puede ser añadido por un proxy corporativo. Casa Tareas lo está propagando también a las llamadas de la API.":"a parameter that may be added by a corporate proxy. Casa Tareas is also forwarding it to API calls.",
"muestra JSON con tus tareas pero esta pantalla sigue apareciendo, prueba una ventana InPrivate del navegador corporativo.":"shows JSON with your tasks but this screen still appears, try an InPrivate window in the corporate browser.",
"No se pudo subir el archivo.":"The file could not be uploaded.","Configurar Telegram":"Configure Telegram","Sin chat":"No chat",
"Crea el bot con @BotFather y guarda el token desde":"Create the bot with @BotFather and save the token from","No hace falta reiniciar Docker.":"Docker does not need to be restarted.",
"Añade el bot al grupo y envía allí":"Add the bot to the group and send","El bot registra chats en segundo plano; espera unos segundos y pulsa Detectar chats.":"The bot records chats in the background; wait a few seconds and press Detect chats.",
"También puedes usar":"You can also use","No hay comandos de borrado.":"There are no delete commands.","Usar este chat":"Use this chat",
"No hay calendarios externos conectados.":"No external calendars connected.","Pega una URL iCal/ICS HTTPS. Puede ser un calendario escolar, deportivo, de comunidad, etc.":"Paste an HTTPS iCal/ICS URL. It can be a school, sports, community or other calendar.",
"PDF, imágenes, facturas, garantías, contratos o manuales. Máximo 20 MB por archivo.":"PDFs, images, invoices, warranties, contracts or manuals. Maximum 20 MB per file.",
"Arrastra aquí una tarea terminada":"Drag a completed task here","o usa el botón ✓ Hecha":"or use the ✓ Done button",
"No hay personas configuradas.":"No people configured.","No hay áreas configuradas.":"No areas configured.","No hay tareas futuras.":"No future tasks.","No hay eventos próximos.":"No upcoming events.",
"No hay tareas en la cola de hoy.":"There are no tasks in Today's queue.","Nada pendiente para hoy.":"Nothing pending for today.",
"Editar tarea":"Edit task","Editar persona":"Edit person","Editar área":"Edit area","Editar evento":"Edit event","Editar producto":"Edit product",
"Abrir Configuración":"Open Settings","Aplicar filtros":"Apply filters","Buscar producto…":"Search product…","Cargando gastos…":"Loading expenses…","Selecciona…":"Select…",
"Compras, tickets, análisis y productos con la misma experiencia de Casa Tareas.":"Purchases, receipts, analysis and products with the same Casa Tareas experience.",
"Configura la integración en Configuración y vuelve a esta sección.":"Configure the integration in Settings and return to this section.",
"Gastos de comida no está configurado.":"Food expenses is not configured.","Todos los campos de la aplicación original siguen disponibles.":"All fields from the original application remain available.",
"Precio neto tiene prioridad; si está vacío se aplican descuento o porcentaje.":"Net price has priority; if empty, discount or percentage is applied.",
"Catálogo estable construido a partir de las compras históricas.":"Stable catalog built from historical purchases.",
"Media histórica por unidad y última compra registrada.":"Historical average per unit and latest recorded purchase.",
"Productos de Casa Tareas agrupados por supermercado recomendado cuando hay histórico suficiente.":"Casa Tareas products grouped by recommended supermarket when enough history is available.",
"Fecha inicio":"Start date","Fecha fin":"End date","Total entre fechas":"Total between dates","Total ticket":"Receipt total","Última fecha":"Latest date","Último/u.":"Latest/unit",
"Supermercados":"Supermarkets","Detalle de compras":"Purchase detail","líneas encontradas":"lines found",
"Gráfica anual de gastos":"Yearly spending chart","Precio medio":"Average price",
"Esta acción no se puede deshacer.":"This action cannot be undone.","Mueve primero todas las tareas y eventos a otra área":"Move all tasks and events to another area first",
"Pausada":"Paused","pendiente":"overdue"
});
Object.assign(DE,{
"Resumen del hogar":"Haushaltsübersicht","Tareas, compra e impacto de Gastos en un solo vistazo.":"Aufgaben, Einkauf und Auswirkungen der Ausgaben auf einen Blick.",
"Gasto del mes":"Ausgaben des Monats","Bloqueadas":"Blockiert","Abrir Gastos":"Ausgaben öffnen","Activar vacaciones":"Urlaub starten",
"Modo vacaciones":"Urlaubsmodus","Modo vacaciones activo":"Urlaubsmodus aktiv","Pausa temporalmente las tareas sin ocultar reuniones, citas ni vencimientos de la Agenda.":"Aufgaben vorübergehend pausieren, ohne Besprechungen, Termine oder Fristen im Kalender auszublenden.",
"Las tareas se ocultan de Hoy, Próximamente y Sugeridas. La Agenda continúa funcionando.":"Aufgaben werden aus Heute, Demnächst und Vorschläge ausgeblendet. Der Kalender bleibt aktiv.",
"Fecha de regreso":"Rückkehrdatum","Áreas que deben seguir activas":"Bereiche, die aktiv bleiben sollen","Útil para pisos en alquiler, Krankenkassen u otros asuntos que deban seguir visibles.":"Nützlich für Mietwohnungen, Krankenkassen oder andere Themen, die sichtbar bleiben sollen.",
"Continuar ciclo · vacaciones no cuentan":"Zyklus fortsetzen · Urlaub zählt nicht","Continuar ciclo · pausa no cuenta":"Zyklus fortsetzen · Pause zählt nicht","Mantener calendario original":"Ursprünglichen Kalender beibehalten",
"Cada X días":"Alle X Tage","Cada X días desde última vez":"Alle X Tage seit dem letzten Mal","Calendario fijo":"Fester Kalender","Duración estimada":"Geschätzte Dauer",
"Responsable de esta tarea":"Verantwortlich für diese Aufgabe","La responsabilidad puede heredarse del área o sobrescribirse para esta tarea.":"Die Verantwortung kann vom Bereich geerbt oder für diese Aufgabe überschrieben werden.",
"Quien sea responsable se encarga de detectar, planificar, ejecutar o coordinar y cerrar lo necesario.":"Die verantwortliche Person erkennt, plant, erledigt oder koordiniert und schließt das Notwendige ab.",
"Nombre del área":"Bereichsname","Área opcional":"Optionaler Bereich","Título":"Titel","Fecha y hora":"Datum und Uhrzeit","Documentación que llevar, dirección, temas a tratar…":"Mitzubringende Unterlagen, Adresse, zu besprechende Themen…",
"Ej. Limpiador de baño":"Z. B. Badreiniger","Ej. botella, paquete":"Z. B. Flasche, Packung","Ej. encimera y fregadero limpios, basura revisada y productos guardados":"Z. B. Arbeitsfläche und Spüle sauber, Müll geprüft und Produkte weggeräumt",
"Ej. incluye comprobar consumibles y decidir cuándo hacerlo":"Z. B. Verbrauchsmaterial prüfen und entscheiden, wann es erledigt wird","Ej. planificación, compras, ejecución y reposición de consumibles":"Z. B. Planung, Einkauf, Durchführung und Nachfüllen von Verbrauchsmaterial",
"Usa Hay / Poco / Falta. Si lo vinculas con Gastos, una compra registrada puede marcarlo automáticamente como repuesto.":"Verwende Vorhanden / Wenig / Fehlt. Bei Verknüpfung mit Ausgaben kann ein erfasster Einkauf automatisch als nachgefüllt markiert werden.",
"Al registrar un ticket con este producto se marcará como Hay y saldrá de Comprar.":"Wird ein Beleg mit diesem Produkt erfasst, wird es als Vorhanden markiert und aus Einkauf entfernt.",
"Cargando catálogo de Gastos…":"Ausgabenkatalog wird geladen…","Gastos no configurado":"Ausgaben nicht konfiguriert","No se pudo cargar Gastos":"Ausgaben konnten nicht geladen werden",
"No se pudo cargar Casa Tareas":"Casa Tareas konnte nicht geladen werden","El servidor responde, pero el navegador no pudo leer correctamente la API.":"Der Server antwortet, aber der Browser konnte die API nicht korrekt lesen.",
"Esta sesión contiene":"Diese Sitzung enthält","un parámetro que puede ser añadido por un proxy corporativo. Casa Tareas lo está propagando también a las llamadas de la API.":"einen Parameter, der von einem Unternehmensproxy hinzugefügt werden kann. Casa Tareas gibt ihn auch an API-Aufrufe weiter.",
"muestra JSON con tus tareas pero esta pantalla sigue apareciendo, prueba una ventana InPrivate del navegador corporativo.":"zeigt JSON mit deinen Aufgaben, aber diese Ansicht bleibt sichtbar; probiere ein InPrivate-Fenster im Unternehmensbrowser.",
"No se pudo subir el archivo.":"Die Datei konnte nicht hochgeladen werden.","Configurar Telegram":"Telegram konfigurieren","Sin chat":"Kein Chat",
"Crea el bot con @BotFather y guarda el token desde":"Erstelle den Bot mit @BotFather und speichere den Token unter","No hace falta reiniciar Docker.":"Docker muss nicht neu gestartet werden.",
"Añade el bot al grupo y envía allí":"Füge den Bot zur Gruppe hinzu und sende dort","El bot registra chats en segundo plano; espera unos segundos y pulsa Detectar chats.":"Der Bot erfasst Chats im Hintergrund; warte einige Sekunden und drücke Chats erkennen.",
"También puedes usar":"Du kannst auch verwenden","No hay comandos de borrado.":"Es gibt keine Löschbefehle.","Usar este chat":"Diesen Chat verwenden",
"No hay calendarios externos conectados.":"Keine externen Kalender verbunden.","Pega una URL iCal/ICS HTTPS. Puede ser un calendario escolar, deportivo, de comunidad, etc.":"Füge eine HTTPS-iCal/ICS-URL ein, z. B. für Schule, Sport oder Gemeinde.",
"PDF, imágenes, facturas, garantías, contratos o manuales. Máximo 20 MB por archivo.":"PDFs, Bilder, Rechnungen, Garantien, Verträge oder Handbücher. Maximal 20 MB pro Datei.",
"Arrastra aquí una tarea terminada":"Erledigte Aufgabe hierher ziehen","o usa el botón ✓ Hecha":"oder die Schaltfläche ✓ Erledigt verwenden",
"No hay personas configuradas.":"Keine Personen konfiguriert.","No hay áreas configuradas.":"Keine Bereiche konfiguriert.","No hay tareas futuras.":"Keine zukünftigen Aufgaben.","No hay eventos próximos.":"Keine bevorstehenden Termine.",
"No hay tareas en la cola de hoy.":"Keine Aufgaben in der Heute-Liste.","Nada pendiente para hoy.":"Heute ist nichts offen.",
"Editar tarea":"Aufgabe bearbeiten","Editar persona":"Person bearbeiten","Editar área":"Bereich bearbeiten","Editar evento":"Termin bearbeiten","Editar producto":"Produkt bearbeiten",
"Abrir Configuración":"Einstellungen öffnen","Aplicar filtros":"Filter anwenden","Buscar producto…":"Produkt suchen…","Cargando gastos…":"Ausgaben werden geladen…","Selecciona…":"Auswählen…",
"Compras, tickets, análisis y productos con la misma experiencia de Casa Tareas.":"Einkäufe, Belege, Analysen und Produkte mit derselben Casa-Tareas-Oberfläche.",
"Configura la integración en Configuración y vuelve a esta sección.":"Konfiguriere die Integration unter Einstellungen und kehre zu diesem Bereich zurück.",
"Gastos de comida no está configurado.":"Lebensmittelausgaben sind nicht konfiguriert.","Todos los campos de la aplicación original siguen disponibles.":"Alle Felder der ursprünglichen Anwendung bleiben verfügbar.",
"Precio neto tiene prioridad; si está vacío se aplican descuento o porcentaje.":"Der Nettopreis hat Vorrang; wenn er leer ist, werden Rabatt oder Prozentsatz angewendet.",
"Catálogo estable construido a partir de las compras históricas.":"Stabiler Katalog auf Basis historischer Einkäufe.",
"Media histórica por unidad y última compra registrada.":"Historischer Durchschnitt pro Einheit und letzter erfasster Einkauf.",
"Productos de Casa Tareas agrupados por supermercado recomendado cuando hay histórico suficiente.":"Casa-Tareas-Produkte nach empfohlenem Supermarkt gruppiert, wenn genügend Historie vorhanden ist.",
"Fecha inicio":"Startdatum","Fecha fin":"Enddatum","Total entre fechas":"Summe zwischen Daten","Total ticket":"Belegsumme","Última fecha":"Letztes Datum","Último/u.":"Letzter/Einheit",
"Supermercados":"Supermärkte","Detalle de compras":"Einkaufsdetails","líneas encontradas":"Positionen gefunden",
"Gráfica anual de gastos":"Jahresdiagramm der Ausgaben","Precio medio":"Durchschnittspreis",
"Esta acción no se puede deshacer.":"Diese Aktion kann nicht rückgängig gemacht werden.","Mueve primero todas las tareas y eventos a otra área":"Verschiebe zuerst alle Aufgaben und Termine in einen anderen Bereich",
"Pausada":"Pausiert","pendiente":"überfällig"
});


Object.assign(EN,{
"Área":"Area","Tarea":"Task","Responsable:":"Owner:","Gestión / carga mental":"Management / mental load",
"Casa Tareas:":"Casa Tareas:","Gastos:":"Expenses:",
"En el despliegue conjunto la URL interna es":"In the combined deployment the internal URL is",
"El servicio está protegido para no arrancar con una base vacía: antes de activarlo hay que apuntar":"The service is protected from starting with an empty database: before enabling it, point",
"a la carpeta que contiene tu":"to the folder containing your","Este token viene de":"This token comes from",
"Para administrarlo desde esta pantalla, elimina esa variable de":"To manage it from this screen, remove that variable from",
"y recrea el contenedor una única vez.":"and recreate the container once.",
"Si el token se guarda aquí queda dentro de":"If the token is saved here it is stored in","trata las copias de seguridad de":"treat backups of","como información sensible.":"as sensitive information.",
"Para conectarlo a un grupo: añade el bot al grupo, escribe":"To connect it to a group: add the bot to the group and type",
"Añade el bot al grupo, envía":"Add the bot to the group, send","y prueba de nuevo.":"and try again.",
"etc. No hay comandos de borrado.":"etc. There are no delete commands.",
"— ver tareas y eventos de hoy":"— view today's tasks and events","— ver la lista de compra":"— view the shopping list","— pregunta quién la hizo":"— asks who did it","— deshacer el último cambio hecho desde Telegram":"— undo the latest change made from Telegram",
"Configuración → Telegram":"Settings → Telegram","Comprueba la conexión o el proxy de red.":"Check the connection or network proxy.",
"devolvió HTML en lugar de datos JSON. Un proxy o filtro de red puede estar interceptando la API.":"returned HTML instead of JSON. A proxy or network filter may be intercepting the API.",
"devolvió una respuesta no válida.":"returned an invalid response.","La llamada":"The call",
"elimina tareas, áreas, personas, agenda, inventario, historial y adjuntos, pero conserva la configuración de la aplicación.":"deletes tasks, areas, people, calendar, inventory, history and attachments, but preserves application settings.",
"elimina tickets, líneas, productos y listas auxiliares, sin tocar Casa Tareas.":"deletes receipts, lines, products and auxiliary lists without touching Casa Tareas."
});
Object.assign(DE,{
"Área":"Bereich","Tarea":"Aufgabe","Responsable:":"Verantwortlich:","Gestión / carga mental":"Verwaltung / mentale Belastung",
"Casa Tareas:":"Casa Tareas:","Gastos:":"Ausgaben:",
"En el despliegue conjunto la URL interna es":"Im kombinierten Betrieb ist die interne URL",
"El servicio está protegido para no arrancar con una base vacía: antes de activarlo hay que apuntar":"Der Dienst startet nicht mit einer leeren Datenbank: vor dem Aktivieren muss",
"a la carpeta que contiene tu":"auf den Ordner mit deiner","Este token viene de":"Dieser Token kommt aus",
"Para administrarlo desde esta pantalla, elimina esa variable de":"Um ihn hier zu verwalten, entferne diese Variable aus",
"y recrea el contenedor una única vez.":"und erstelle den Container einmal neu.",
"Si el token se guarda aquí queda dentro de":"Wenn der Token hier gespeichert wird, liegt er in","trata las copias de seguridad de":"behandle Sicherungen von","como información sensible.":"als vertrauliche Informationen.",
"Para conectarlo a un grupo: añade el bot al grupo, escribe":"Zum Verbinden mit einer Gruppe: Bot hinzufügen und eingeben",
"Añade el bot al grupo, envía":"Füge den Bot zur Gruppe hinzu, sende","y prueba de nuevo.":"und versuche es erneut.",
"etc. No hay comandos de borrado.":"usw. Es gibt keine Löschbefehle.",
"— ver tareas y eventos de hoy":"— heutige Aufgaben und Termine anzeigen","— ver la lista de compra":"— Einkaufsliste anzeigen","— pregunta quién la hizo":"— fragt, wer sie erledigt hat","— deshacer el último cambio hecho desde Telegram":"— letzte über Telegram vorgenommene Änderung rückgängig machen",
"Configuración → Telegram":"Einstellungen → Telegram","Comprueba la conexión o el proxy de red.":"Prüfe Verbindung oder Netzwerkproxy.",
"devolvió HTML en lugar de datos JSON. Un proxy o filtro de red puede estar interceptando la API.":"lieferte HTML statt JSON. Ein Proxy oder Netzwerkfilter könnte die API abfangen.",
"devolvió una respuesta no válida.":"lieferte eine ungültige Antwort.","La llamada":"Der Aufruf",
"elimina tareas, áreas, personas, agenda, inventario, historial y adjuntos, pero conserva la configuración de la aplicación.":"löscht Aufgaben, Bereiche, Personen, Kalender, Inventar, Verlauf und Anhänge, behält aber die Anwendungseinstellungen.",
"elimina tickets, líneas, productos y listas auxiliares, sin tocar Casa Tareas.":"löscht Belege, Positionen, Produkte und Hilfslisten, ohne Casa Tareas zu verändern."
});


Object.assign(EN,{
"Todos":"All","Pendiente":"Due","Puede esperar":"Can wait","Pronto":"Soon","Conviene hacer":"Worth doing",
"Sin estimar":"Not estimated","Sin área":"No area",
"Limpiar baño":"Clean bathroom","Poner lavadora":"Do laundry","Sacar basura":"Take out rubbish","Aspirar salón":"Vacuum living room",
"Cambiar sábanas":"Change bed sheets","Limpiar frigorífico":"Clean fridge","Limpiar cristales":"Clean windows","Limpiar horno":"Clean oven",
"Lavabo, ducha, espejo e inodoro":"Sink, shower, mirror and toilet","Ropa blanca":"Whites laundry","Contenedor general":"General waste bin",
"Sofá, alfombras y zonas de paso":"Sofa, rugs and walkways","Dormitorio principal":"Main bedroom","Interior y estantes":"Interior and shelves",
"Ventanas y espejos":"Windows and mirrors","Interior y bandejas":"Interior and trays",
"Baño":"Bathroom","Ropa":"Laundry","Casa":"Home","Salón":"Living room","Dormitorio":"Bedroom","Cocina":"Kitchen",
"Ropa y textil":"Laundry and textiles","Limpieza y mantenimiento":"Cleaning and maintenance","Vehículos":"Vehicles"
});
Object.assign(DE,{
"Todos":"Alle","Pendiente":"Fällig","Puede esperar":"Kann warten","Pronto":"Bald","Conviene hacer":"Sollte erledigt werden",
"Sin estimar":"Nicht geschätzt","Sin área":"Ohne Bereich",
"Limpiar baño":"Bad reinigen","Poner lavadora":"Wäsche waschen","Sacar basura":"Müll rausbringen","Aspirar salón":"Wohnzimmer saugen",
"Cambiar sábanas":"Bettwäsche wechseln","Limpiar frigorífico":"Kühlschrank reinigen","Limpiar cristales":"Fenster reinigen","Limpiar horno":"Backofen reinigen",
"Lavabo, ducha, espejo e inodoro":"Waschbecken, Dusche, Spiegel und Toilette","Ropa blanca":"Weiße Wäsche","Contenedor general":"Restmüllbehälter",
"Sofá, alfombras y zonas de paso":"Sofa, Teppiche und Laufwege","Dormitorio principal":"Hauptschlafzimmer","Interior y estantes":"Innenraum und Ablagen",
"Ventanas y espejos":"Fenster und Spiegel","Interior y bandejas":"Innenraum und Bleche",
"Baño":"Bad","Ropa":"Wäsche","Casa":"Haus","Salón":"Wohnzimmer","Dormitorio":"Schlafzimmer","Cocina":"Küche",
"Ropa y textil":"Wäsche und Textilien","Limpieza y mantenimiento":"Reinigung und Instandhaltung","Vehículos":"Fahrzeuge"
});


Object.assign(EN,{
"Confianza alta":"High confidence","Confianza media":"Medium confidence","Confianza baja":"Low confidence",
"confianza alta":"high confidence","confianza media":"medium confidence","confianza baja":"low confidence",
"Precio recomendado":"Recommended price","Precio recomendación/u.":"Recommendation price/unit","Recientes":"Recent","Confianza":"Confidence",
"Precio reciente ponderado, muestras y última compra registrada.":"Recency-weighted price, sample count and latest recorded purchase."
});
Object.assign(DE,{
"Confianza alta":"Hohe Sicherheit","Confianza media":"Mittlere Sicherheit","Confianza baja":"Geringe Sicherheit",
"confianza alta":"hohe Sicherheit","confianza media":"mittlere Sicherheit","confianza baja":"geringe Sicherheit",
"Precio recomendado":"Empfohlener Preis","Precio recomendación/u.":"Empfehlungspreis/Einheit","Recientes":"Aktuell","Confianza":"Sicherheit",
"Precio reciente ponderado, muestras y última compra registrada.":"Nach Aktualität gewichteter Preis, Stichprobenzahl und letzter erfasster Einkauf."
});


Object.assign(EN,{
"Cesta estimada":"Estimated basket","Cesta":"Basket","Cálculo parcial":"Partial estimate",
"Cálculo completo con las cantidades interpretables de la lista.":"Complete estimate using the interpretable quantities in the list.",
"No hay cantidades suficientemente claras para calcular la cesta.":"There are not enough clear quantities to calculate the basket.",
"No hay cantidades suficientemente claras para calcular un total de cesta.":"There are not enough clear quantities to calculate a basket total."
});
Object.assign(DE,{
"Cesta estimada":"Geschätzter Warenkorb","Cesta":"Warenkorb","Cálculo parcial":"Teilschätzung",
"Cálculo completo con las cantidades interpretables de la lista.":"Vollständige Schätzung mit den eindeutig interpretierbaren Mengen der Liste.",
"No hay cantidades suficientemente claras para calcular la cesta.":"Es gibt nicht genügend eindeutige Mengen, um den Warenkorb zu berechnen.",
"No hay cantidades suficientemente claras para calcular un total de cesta.":"Es gibt nicht genügend eindeutige Mengen, um einen Warenkorb-Gesamtbetrag zu berechnen."
});


Object.assign(EN,{
"Sincronizar ahora":"Sync now","Última sincronización":"Last sync","Sincronización automática":"Automatic sync",
"Error de sincronización":"Sync error","Gastos sincronizado":"Expenses synced","sin cambios":"no changes",
"Las compras nuevas o editadas directamente en Gastos se sincronizan automáticamente con el Inventario de Casa.":"Purchases created or edited directly in Expenses are automatically synchronized with Casa Inventory."
});
Object.assign(DE,{
"Sincronizar ahora":"Jetzt synchronisieren","Última sincronización":"Letzte Synchronisierung","Sincronización automática":"Automatische Synchronisierung",
"Error de sincronización":"Synchronisierungsfehler","Gastos sincronizado":"Ausgaben synchronisiert","sin cambios":"keine Änderungen",
"Las compras nuevas o editadas directamente en Gastos se sincronizan automáticamente con el Inventario de Casa.":"Direkt in Ausgaben neu erstellte oder bearbeitete Einkäufe werden automatisch mit dem Casa-Inventar synchronisiert."
});

var dictionaries={en:EN,de:DE};

var dynamic={
en:[
[/^(\d+) d pendiente$/,"$1 d overdue"],[/^En (\d+) días$/,"In $1 days"],[/^(\d+) día antes$/,"$1 day before"],[/^(\d+) días antes$/,"$1 days before"],
[/^(\d+) min antes$/,"$1 min before"],[/^(\d+) h antes$/,"$1 h before"],
[/^Próximos · (\d+)$/,"Upcoming · $1"],[/^Pasados · (\d+)$/,"Past · $1"],[/^Comprar · (\d+)$/,"Shopping · $1"],[/^Inventario · (\d+)$/,"Inventory · $1"],
[/^(\d+) tareas$/,"$1 tasks"],[/^(\d+) productos$/,"$1 products"],[/^(\d+) producto$/,"$1 product"],[/^(\d+) líneas$/,"$1 lines"],[/^(\d+) artículos más$/,"$1 more items"],
[/^Comprar: (.+)$/,"Buy: $1"],[/^Necesario para: (.+)$/,"Needed for: $1"],[/^Falta: (.+)$/,"Missing: $1"],[/^Pausada hasta (.+)$/,"Paused until $1"],[/^Responsable: (.+)$/,"Owner: $1"],
[/^Sincronizado (.+)$/,"Synced $1"],[/^Última: (.+)$/,"Latest: $1"],[/^Media (.+)$/,"Average $1"],[/^Último (.+)$/,"Latest $1"],[/^Ahorro ≈ (.+)$/,"Saving ≈ $1"],
[/^Ahorro aprox\. (.+)$/,"Approx. saving $1"],[/^Ahorro estimado · (.+)$/,"Estimated saving · $1"],[/^Conexión correcta · (.+)$/,"Connection successful · $1"],
[/^No se pudo cargar el resumen de Gastos: (.+)$/,"Could not load the Expenses summary: $1"],
[/^Actualizada la tarea "(.+)"$/,'Updated task "$1"'],[/^Creada la tarea "(.+)"$/,'Created task "$1"'],[/^Archivada "(.+)"$/,'Archived "$1"'],
[/^Eliminada definitivamente la tarea "(.+)"$/,'Permanently deleted task "$1"'],[/^Añadida a Hoy: "(.+)"$/,'Added to Today: "$1"'],[/^Quitada de Hoy: "(.+)"$/,'Removed from Today: "$1"'],
[/^Completada "(.+)" por (.+)$/,'Completed "$1" by $2'],[/^Deshecha la realización de "(.+)"$/,'Undid completion of "$1"'],[/^Movida de área "(.+)"$/,'Moved task to another area "$1"'],
[/^Movida "(.+)" a (.+)$/,'Moved "$1" to $2'],[/^Actualizada el área "(.+)"$/,'Updated area "$1"'],[/^Creada el área "(.+)"$/,'Created area "$1"'],
[/^Archivada el área "(.+)"$/,'Archived area "$1"'],[/^Reactivada el área "(.+)"$/,'Reactivated area "$1"'],[/^Eliminada definitivamente el área "(.+)"$/,'Permanently deleted area "$1"'],
[/^Actualizado el producto "(.+)"$/,'Updated product "$1"'],[/^Archivado el producto "(.+)"$/,'Archived product "$1"'],[/^Añadido al inventario "(.+)"$/,'Added to inventory "$1"'],
[/^Añadido a Comprar "(.+)"$/,'Added to Shopping "$1"'],[/^Repuesto desde Gastos: "(.+)"$/,'Restocked from Expenses: "$1"'],[/^Vinculado "(.+)" con Gastos: (.+)$/,'Linked "$1" with Expenses: $2'],
[/^Desvinculado "(.+)" de Gastos$/,'Unlinked "$1" from Expenses'],[/^Añadido el calendario externo "(.+)"$/,'Added external calendar "$1"'],[/^Actualizado el calendario externo "(.+)"$/,'Updated external calendar "$1"'],
[/^Actualizado el evento "(.+)"$/,'Updated event "$1"'],[/^Eliminado el evento "(.+)"$/,'Deleted event "$1"'],[/^(.+) completó "(.+)"$/,'$1 completed "$2"'],
[/^Eliminado el calendario externo "(.+)"$/,'Deleted external calendar "$1"'],[/^Eliminado el adjunto "(.+)"$/,'Deleted attachment "$1"'],[/^Eliminada la persona "(.+)"$/,'Deleted person "$1"'],
[/^Creada "Hacer la compra" · (\d+) producto\(s\)$/,'Created "Do the shopping" · $1 product(s)'],[/^Reactivada "Hacer la compra" · (\d+) producto\(s\)$/,'Reactivated "Do the shopping" · $1 product(s)'],
[/^Modo vacaciones hasta (.+)$/,"Vacation mode until $1"],[/^Ticket #(\d+)$/,"Receipt #$1"],[/^(\d+) producto(?:s)? · (.+)$/,"$1 product(s) · $2"]
],
de:[
[/^(\d+) d pendiente$/,"$1 T. überfällig"],[/^En (\d+) días$/,"In $1 Tagen"],[/^(\d+) día antes$/,"$1 Tag vorher"],[/^(\d+) días antes$/,"$1 Tage vorher"],
[/^(\d+) min antes$/,"$1 Min. vorher"],[/^(\d+) h antes$/,"$1 Std. vorher"],
[/^Próximos · (\d+)$/,"Bevorstehend · $1"],[/^Pasados · (\d+)$/,"Vergangen · $1"],[/^Comprar · (\d+)$/,"Einkauf · $1"],[/^Inventario · (\d+)$/,"Inventar · $1"],
[/^(\d+) tareas$/,"$1 Aufgaben"],[/^(\d+) productos$/,"$1 Produkte"],[/^(\d+) producto$/,"$1 Produkt"],[/^(\d+) líneas$/,"$1 Positionen"],[/^(\d+) artículos más$/,"$1 weitere Artikel"],
[/^Comprar: (.+)$/,"Kaufen: $1"],[/^Necesario para: (.+)$/,"Benötigt für: $1"],[/^Falta: (.+)$/,"Fehlt: $1"],[/^Pausada hasta (.+)$/,"Pausiert bis $1"],[/^Responsable: (.+)$/,"Verantwortlich: $1"],
[/^Sincronizado (.+)$/,"Synchronisiert $1"],[/^Última: (.+)$/,"Letzte: $1"],[/^Media (.+)$/,"Durchschnitt $1"],[/^Último (.+)$/,"Letzter $1"],[/^Ahorro ≈ (.+)$/,"Ersparnis ≈ $1"],
[/^Ahorro aprox\. (.+)$/,"Ca. Ersparnis $1"],[/^Ahorro estimado · (.+)$/,"Geschätzte Ersparnis · $1"],[/^Conexión correcta · (.+)$/,"Verbindung erfolgreich · $1"],
[/^No se pudo cargar el resumen de Gastos: (.+)$/,"Ausgabenübersicht konnte nicht geladen werden: $1"],
[/^Actualizada la tarea "(.+)"$/,'Aufgabe "$1" aktualisiert'],[/^Creada la tarea "(.+)"$/,'Aufgabe "$1" erstellt'],[/^Archivada "(.+)"$/,'"$1" archiviert'],
[/^Eliminada definitivamente la tarea "(.+)"$/,'Aufgabe "$1" endgültig gelöscht'],[/^Añadida a Hoy: "(.+)"$/,'Zu Heute hinzugefügt: "$1"'],[/^Quitada de Hoy: "(.+)"$/,'Aus Heute entfernt: "$1"'],
[/^Completada "(.+)" por (.+)$/,'"$1" von $2 erledigt'],[/^Deshecha la realización de "(.+)"$/,'Erledigung von "$1" rückgängig gemacht'],[/^Movida de área "(.+)"$/,'Aufgabe "$1" in anderen Bereich verschoben'],
[/^Movida "(.+)" a (.+)$/,'"$1" nach $2 verschoben'],[/^Actualizada el área "(.+)"$/,'Bereich "$1" aktualisiert'],[/^Creada el área "(.+)"$/,'Bereich "$1" erstellt'],
[/^Archivada el área "(.+)"$/,'Bereich "$1" archiviert'],[/^Reactivada el área "(.+)"$/,'Bereich "$1" reaktiviert'],[/^Eliminada definitivamente el área "(.+)"$/,'Bereich "$1" endgültig gelöscht'],
[/^Actualizado el producto "(.+)"$/,'Produkt "$1" aktualisiert'],[/^Archivado el producto "(.+)"$/,'Produkt "$1" archiviert'],[/^Añadido al inventario "(.+)"$/,'"$1" zum Inventar hinzugefügt'],
[/^Añadido a Comprar "(.+)"$/,'"$1" zum Einkauf hinzugefügt'],[/^Repuesto desde Gastos: "(.+)"$/,'Aus Ausgaben nachgefüllt: "$1"'],[/^Vinculado "(.+)" con Gastos: (.+)$/,'"$1" mit Ausgaben verknüpft: $2'],
[/^Desvinculado "(.+)" de Gastos$/,'"$1" von Ausgaben getrennt'],[/^Añadido el calendario externo "(.+)"$/,'Externer Kalender "$1" hinzugefügt'],[/^Actualizado el calendario externo "(.+)"$/,'Externer Kalender "$1" aktualisiert'],
[/^Actualizado el evento "(.+)"$/,'Termin "$1" aktualisiert'],[/^Eliminado el evento "(.+)"$/,'Termin "$1" gelöscht'],[/^(.+) completó "(.+)"$/,'$1 hat "$2" erledigt'],
[/^Eliminado el calendario externo "(.+)"$/,'Externer Kalender "$1" gelöscht'],[/^Eliminado el adjunto "(.+)"$/,'Anhang "$1" gelöscht'],[/^Eliminada la persona "(.+)"$/,'Person "$1" gelöscht'],
[/^Creada "Hacer la compra" · (\d+) producto\(s\)$/,'"Einkaufen gehen" erstellt · $1 Produkt(e)'],[/^Reactivada "Hacer la compra" · (\d+) producto\(s\)$/,'"Einkaufen gehen" reaktiviert · $1 Produkt(e)'],
[/^Modo vacaciones hasta (.+)$/,"Urlaubsmodus bis $1"],[/^Ticket #(\d+)$/,"Beleg #$1"],[/^(\d+) producto(?:s)? · (.+)$/,"$1 Produkt(e) · $2"]
]};


dynamic.en.push(
 [/^Cesta estimada: (.+)$/,"Estimated basket: $1"],
 [/^Cesta ≈ (.+)$/,"Basket ≈ $1"],
 [/^cesta aprox\. (.+)$/,"approx. basket $1"],
 [/^total aprox\. (.+)$/,"approx. total $1"],
 [/^ahorro estimado (.+)$/,"estimated saving $1"],
 [/^ahorro (.+)$/,"saving $1"],
 [/^Cálculo parcial: (\d+) de (\d+) productos tienen cantidad y precio comparables\.$/,"Partial estimate: $1 of $2 products have comparable quantity and price."],
 [/^cálculo parcial: (\d+) de (\d+) productos$/,"partial estimate: $1 of $2 products"]
);
dynamic.de.push(
 [/^Cesta estimada: (.+)$/,"Geschätzter Warenkorb: $1"],
 [/^Cesta ≈ (.+)$/,"Warenkorb ≈ $1"],
 [/^cesta aprox\. (.+)$/,"Warenkorb ca. $1"],
 [/^total aprox\. (.+)$/,"Gesamt ca. $1"],
 [/^ahorro estimado (.+)$/,"geschätzte Ersparnis $1"],
 [/^ahorro (.+)$/,"Ersparnis $1"],
 [/^Cálculo parcial: (\d+) de (\d+) productos tienen cantidad y precio comparables\.$/,"Teilschätzung: $1 von $2 Produkten haben vergleichbare Menge und Preis."],
 [/^cálculo parcial: (\d+) de (\d+) productos$/,"Teilschätzung: $1 von $2 Produkten"]
);

var alertExact={
en:{
"Pega primero el token que te dio BotFather.":"Paste the BotFather token first.",
"¿Eliminar el token guardado en Casa Tareas? También se olvidará el grupo conectado y habrá que detectarlo de nuevo.":"Delete the token saved in Casa Tareas? The connected group will also be forgotten and must be detected again.",
"¿Desconectar el chat de Telegram? Los eventos y recordatorios se conservarán.":"Disconnect the Telegram chat? Events and reminders will be preserved.",
"¿Terminar el modo vacaciones ahora?":"End vacation mode now?",
"¿Archivar esta tarea? El historial se conservará.":"Archive this task? Its history will be preserved.",
"¿Archivar este producto?":"Archive this product?",
"¿Eliminar este documento?":"Delete this document?",
"No se concedió permiso para notificaciones.":"Notification permission was not granted.",
"Avisos del navegador activados mientras Casa Tareas esté abierta.":"Browser notifications are enabled while Casa Tareas is open.",
"Las notificaciones del navegador requieren HTTPS o abrir la app desde localhost. Los avisos dentro de Casa Tareas seguirán funcionando.":"Browser notifications require HTTPS or opening the app from localhost. In-app alerts will continue to work."
},
de:{
"Pega primero el token que te dio BotFather.":"Füge zuerst den Token von BotFather ein.",
"¿Eliminar el token guardado en Casa Tareas? También se olvidará el grupo conectado y habrá que detectarlo de nuevo.":"Gespeicherten Casa-Tareas-Token löschen? Die verbundene Gruppe wird ebenfalls vergessen und muss erneut erkannt werden.",
"¿Desconectar el chat de Telegram? Los eventos y recordatorios se conservarán.":"Telegram-Chat trennen? Termine und Erinnerungen bleiben erhalten.",
"¿Terminar el modo vacaciones ahora?":"Urlaubsmodus jetzt beenden?",
"¿Archivar esta tarea? El historial se conservará.":"Diese Aufgabe archivieren? Der Verlauf bleibt erhalten.",
"¿Archivar este producto?":"Dieses Produkt archivieren?",
"¿Eliminar este documento?":"Dieses Dokument löschen?",
"No se concedió permiso para notificaciones.":"Benachrichtigungsberechtigung wurde nicht erteilt.",
"Avisos del navegador activados mientras Casa Tareas esté abierta.":"Browser-Benachrichtigungen sind aktiviert, solange Casa Tareas geöffnet ist.",
"Las notificaciones del navegador requieren HTTPS o abrir la app desde localhost. Los avisos dentro de Casa Tareas seguirán funcionando.":"Browser-Benachrichtigungen benötigen HTTPS oder localhost. Die Hinweise innerhalb von Casa Tareas funktionieren weiterhin."
}};

var alertPatterns={
en:[
[/^¿Eliminar permanentemente "(.+)"\?\n\nTambién se borrarán su historial y sus documentos adjuntos\. Esta acción no se puede deshacer\.$/,'Permanently delete "$1"?\n\nIts history and attachments will also be deleted. This cannot be undone.'],
[/^¿Eliminar el evento "(.+)"\?$/,'Delete event "$1"?'],[/^¿Eliminar la suscripción "(.+)"\? Los eventos importados desaparecerán de Casa Tareas, pero no se modifica el calendario original\.$/,'Delete subscription "$1"? Imported events will disappear from Casa Tareas, but the original calendar will not be changed.'],
[/^¿Eliminar a "(.+)"\?\n\nSu historial anterior se conservará, pero ya no aparecerá al completar tareas\.$/,'Delete "$1"?\n\nPrevious history will be preserved, but this person will no longer appear when completing tasks.'],
[/^¿Archivar el área "(.+)"\?\n\nLas tareas conservarán la referencia, pero dejarán de heredar su responsable hasta restaurarla o cambiar de área\.$/,'Archive area "$1"?\n\nTasks will keep the reference but will stop inheriting its owner until the area is restored or changed.'],
[/^No se pudo conectar con la API en (.+)\. Comprueba la conexión o el proxy de red\.$/,"Could not connect to the API at $1. Check the connection or network proxy."],
[/^La llamada (.+) devolvió HTML en lugar de datos JSON\. Un proxy o filtro de red puede estar interceptando la API\.$/,"The call to $1 returned HTML instead of JSON. A proxy or network filter may be intercepting the API."],
[/^La llamada (.+) devolvió una respuesta no válida\.$/,"The call to $1 returned an invalid response."]
],
de:[
[/^¿Eliminar permanentemente "(.+)"\?\n\nTambién se borrarán su historial y sus documentos adjuntos\. Esta acción no se puede deshacer\.$/,'"$1" endgültig löschen?\n\nVerlauf und Anhänge werden ebenfalls gelöscht. Dies kann nicht rückgängig gemacht werden.'],
[/^¿Eliminar el evento "(.+)"\?$/,'Termin "$1" löschen?'],[/^¿Eliminar la suscripción "(.+)"\? Los eventos importados desaparecerán de Casa Tareas, pero no se modifica el calendario original\.$/,'Abonnement "$1" löschen? Importierte Termine verschwinden aus Casa Tareas, der ursprüngliche Kalender wird nicht verändert.'],
[/^¿Eliminar a "(.+)"\?\n\nSu historial anterior se conservará, pero ya no aparecerá al completar tareas\.$/,'"$1" löschen?\n\nDer bisherige Verlauf bleibt erhalten, die Person erscheint aber nicht mehr beim Erledigen von Aufgaben.'],
[/^¿Archivar el área "(.+)"\?\n\nLas tareas conservarán la referencia, pero dejarán de heredar su responsable hasta restaurarla o cambiar de área\.$/,'Bereich "$1" archivieren?\n\nAufgaben behalten die Referenz, übernehmen aber keinen Verantwortlichen mehr, bis der Bereich wiederhergestellt oder geändert wird.'],
[/^No se pudo conectar con la API en (.+)\. Comprueba la conexión o el proxy de red\.$/,"Verbindung zur API unter $1 nicht möglich. Prüfe Verbindung oder Netzwerkproxy."],
[/^La llamada (.+) devolvió HTML en lugar de datos JSON\. Un proxy o filtro de red puede estar interceptando la API\.$/,"Der Aufruf $1 lieferte HTML statt JSON. Ein Proxy oder Netzwerkfilter könnte die API abfangen."],
[/^La llamada (.+) devolvió una respuesta no válida\.$/,"Der Aufruf $1 lieferte eine ungültige Antwort."]
]};

var backendPhrases={
en:[
["Actualizada la configuración de Casa Tareas","Casa Tareas settings updated"],["Actualizada la integración con Gastos de comida","Expenses integration updated"],
["Eliminada la configuración del bot de Telegram","Telegram bot configuration deleted"],["Telegram configurado","Telegram configured"],["La tarea ha vuelto a Hoy.","The task has returned to Today."],
["Base de Gastos vaciada; vínculos de inventario eliminados","Expenses database cleared; inventory links removed"],["La lista de compra vuelve a estar vacía.","The shopping list is empty again."],
['Lista vacía: resuelta "Hacer la compra"','Empty list: "Do the shopping" resolved'],["Orden de Hoy cambiado","Today order changed"],["Tarea completada","Task completed"],["Tarea archivada","Task archived"],
["Tarea pospuesta","Task postponed"],["Tarea movida de área","Task moved to another area"],["Persona eliminada","Person deleted"],["Persona restaurada","Person restored"],
["Área archivada","Area archived"],["Área restaurada","Area restored"],["Configuración guardada","Settings saved"],["Integración de Gastos guardada","Expenses integration saved"],
["Integración de Gastos desconectada","Expenses integration disconnected"],["Casa Tareas se ha reiniciado desde cero","Casa Tareas has been reset"],["Gastos se ha reiniciado desde cero","Expenses has been reset"],
["Producto añadido al Inventario","Product added to Inventory"],["Opción ocultada de las listas","Option hidden from lists"],["Ticket creado","Receipt created"],["Ticket actualizado","Receipt updated"],["Ticket eliminado","Receipt deleted"],
["Tarea no encontrada","Task not found"],["Producto no encontrado","Product not found"],["Área no encontrada","Area not found"],["Calendario externo no encontrado","External calendar not found"],
["Confirmación incorrecta","Incorrect confirmation"],["Confirmación no válida.","Invalid confirmation."],["Zona horaria no válida","Invalid time zone"],["Estado de stock no válido","Invalid stock status"],
["Recurrencia no válida","Invalid recurrence"],["Tipo de tarea no válido","Invalid task type"],["Responsable no válido o inactivo","Invalid or inactive owner"],["Persona no válida","Invalid person"],
["Fecha no válida","Invalid date"],["Fecha y hora del evento no válidas","Invalid event date and time"],["Recordatorio no válido","Invalid reminder"],["Modo de reanudación no válido","Invalid resume mode"],
["La lista de Hoy cambió; recarga e inténtalo de nuevo","The Today list changed; reload and try again"],["Esta acción ya no se puede deshacer","This action can no longer be undone"],
["Esta confirmación ya no está disponible","This confirmation is no longer available"],["La confirmación ha caducado","The confirmation has expired"],
["El archivo está vacío","The file is empty"],["El archivo ya no está disponible en disco","The file is no longer available on disk"],["Tipo de adjunto no válido","Invalid attachment type"],
["El nombre no puede estar vacío","The name cannot be empty"],["El nombre del producto no puede estar vacío","The product name cannot be empty"],["El nombre del área no puede estar vacío","The area name cannot be empty"],
["Ya existe un producto con ese nombre","A product with that name already exists"],["Ya existe un área con ese nombre","An area with that name already exists"],["Ya existe una persona con ese nombre","A person with that name already exists"],
["Gastos de comida todavía no está configurado","Food expenses is not configured yet"],["Gastos de comida devolvió una respuesta no válida","Food expenses returned an invalid response"],["Gastos de comida devolvió un formato inesperado","Food expenses returned an unexpected format"],
["La URL de Gastos de comida debe empezar por http:// o https://","The Food expenses URL must start with http:// or https://"],["La URL de Gastos de comida no debe incluir credenciales","The Food expenses URL must not include credentials"],
["Usa solo la URL base de Gastos de comida, sin parámetros ni fragmentos","Use only the Food expenses base URL, without parameters or fragments"],["Usa solo la URL base de Gastos de comida, sin una ruta adicional","Use only the Food expenses base URL, without an additional path"],
["La URL responde, pero no parece ser el servicio Gastos de comida","The URL responds, but it does not appear to be the Food expenses service"],
["Telegram todavía no está configurado","Telegram is not configured yet"],["Telegram rechazó la petición","Telegram rejected the request"],["Acción no reconocida","Unrecognized action"]
],
de:[
["Actualizada la configuración de Casa Tareas","Casa-Tareas-Einstellungen aktualisiert"],["Actualizada la integración con Gastos de comida","Ausgaben-Integration aktualisiert"],
["Eliminada la configuración del bot de Telegram","Telegram-Bot-Konfiguration gelöscht"],["Telegram configurado","Telegram konfiguriert"],["La tarea ha vuelto a Hoy.","Die Aufgabe ist zu Heute zurückgekehrt."],
["Base de Gastos vaciada; vínculos de inventario eliminados","Ausgabendatenbank geleert; Inventarverknüpfungen entfernt"],["La lista de compra vuelve a estar vacía.","Die Einkaufsliste ist wieder leer."],
['Lista vacía: resuelta "Hacer la compra"','Leere Liste: "Einkaufen gehen" erledigt'],["Orden de Hoy cambiado","Reihenfolge von Heute geändert"],["Tarea completada","Aufgabe erledigt"],["Tarea archivada","Aufgabe archiviert"],
["Tarea pospuesta","Aufgabe verschoben"],["Tarea movida de área","Aufgabe in anderen Bereich verschoben"],["Persona eliminada","Person gelöscht"],["Persona restaurada","Person wiederhergestellt"],
["Área archivada","Bereich archiviert"],["Área restaurada","Bereich wiederhergestellt"],["Configuración guardada","Einstellungen gespeichert"],["Integración de Gastos guardada","Ausgaben-Integration gespeichert"],
["Integración de Gastos desconectada","Ausgaben-Integration getrennt"],["Casa Tareas se ha reiniciado desde cero","Casa Tareas wurde zurückgesetzt"],["Gastos se ha reiniciado desde cero","Ausgaben wurden zurückgesetzt"],
["Producto añadido al Inventario","Produkt zum Inventar hinzugefügt"],["Opción ocultada de las listas","Option aus Listen ausgeblendet"],["Ticket creado","Beleg erstellt"],["Ticket actualizado","Beleg aktualisiert"],["Ticket eliminado","Beleg gelöscht"],
["Tarea no encontrada","Aufgabe nicht gefunden"],["Producto no encontrado","Produkt nicht gefunden"],["Área no encontrada","Bereich nicht gefunden"],["Calendario externo no encontrado","Externer Kalender nicht gefunden"],
["Confirmación incorrecta","Falsche Bestätigung"],["Confirmación no válida.","Ungültige Bestätigung."],["Zona horaria no válida","Ungültige Zeitzone"],["Estado de stock no válido","Ungültiger Lagerstatus"],
["Recurrencia no válida","Ungültige Wiederholung"],["Tipo de tarea no válido","Ungültiger Aufgabentyp"],["Responsable no válido o inactivo","Ungültiger oder inaktiver Verantwortlicher"],["Persona no válida","Ungültige Person"],
["Fecha no válida","Ungültiges Datum"],["Fecha y hora del evento no válidas","Ungültiges Datum/Uhrzeit des Termins"],["Recordatorio no válido","Ungültige Erinnerung"],["Modo de reanudación no válido","Ungültiger Fortsetzungsmodus"],
["La lista de Hoy cambió; recarga e inténtalo de nuevo","Die Heute-Liste hat sich geändert; neu laden und erneut versuchen"],["Esta acción ya no se puede deshacer","Diese Aktion kann nicht mehr rückgängig gemacht werden"],
["Esta confirmación ya no está disponible","Diese Bestätigung ist nicht mehr verfügbar"],["La confirmación ha caducado","Die Bestätigung ist abgelaufen"],
["El archivo está vacío","Die Datei ist leer"],["El archivo ya no está disponible en disco","Die Datei ist nicht mehr auf dem Datenträger verfügbar"],["Tipo de adjunto no válido","Ungültiger Anhangstyp"],
["El nombre no puede estar vacío","Der Name darf nicht leer sein"],["El nombre del producto no puede estar vacío","Der Produktname darf nicht leer sein"],["El nombre del área no puede estar vacío","Der Bereichsname darf nicht leer sein"],
["Ya existe un producto con ese nombre","Ein Produkt mit diesem Namen existiert bereits"],["Ya existe un área con ese nombre","Ein Bereich mit diesem Namen existiert bereits"],["Ya existe una persona con ese nombre","Eine Person mit diesem Namen existiert bereits"],
["Gastos de comida todavía no está configurado","Lebensmittelausgaben sind noch nicht konfiguriert"],["Gastos de comida devolvió una respuesta no válida","Lebensmittelausgaben lieferten eine ungültige Antwort"],["Gastos de comida devolvió un formato inesperado","Lebensmittelausgaben lieferten ein unerwartetes Format"],
["La URL de Gastos de comida debe empezar por http:// o https://","Die URL für Lebensmittelausgaben muss mit http:// oder https:// beginnen"],["La URL de Gastos de comida no debe incluir credenciales","Die URL für Lebensmittelausgaben darf keine Zugangsdaten enthalten"],
["Usa solo la URL base de Gastos de comida, sin parámetros ni fragmentos","Nur die Basis-URL der Lebensmittelausgaben ohne Parameter oder Fragmente verwenden"],["Usa solo la URL base de Gastos de comida, sin una ruta adicional","Nur die Basis-URL der Lebensmittelausgaben ohne zusätzlichen Pfad verwenden"],
["La URL responde, pero no parece ser el servicio Gastos de comida","Die URL antwortet, scheint aber nicht der Lebensmittelausgaben-Dienst zu sein"],
["Telegram todavía no está configurado","Telegram ist noch nicht konfiguriert"],["Telegram rechazó la petición","Telegram hat die Anfrage abgelehnt"],["Acción no reconocida","Unbekannte Aktion"]
]};

function translateDynamic(value,language){
 var list=dynamic[language]||[];
 for(var i=0;i<list.length;i++){
   if(list[i][0].test(value))return value.replace(list[i][0],list[i][1]);
 }
 return value;
}

function translateBackendPhrases(value,language){
 var list=backendPhrases[language]||[];
 var result=value;
 for(var i=0;i<list.length;i++){
   if(result.indexOf(list[i][0])>=0)result=result.split(list[i][0]).join(list[i][1]);
 }
 return result;
}

function translateKnownFragments(value,language){
 var dict=dictionaries[language]||{};
 var keys=[
  "Limpiar baño","Poner lavadora","Sacar basura","Aspirar salón","Cambiar sábanas","Limpiar frigorífico","Limpiar cristales","Limpiar horno",
  "Lavabo, ducha, espejo e inodoro","Ropa blanca","Contenedor general","Sofá, alfombras y zonas de paso","Dormitorio principal","Interior y estantes","Ventanas y espejos","Interior y bandejas",
  "Hacer la compra"
 ];
 var result=value;
 keys.forEach(function(key){
   if(dict[key]&&result.indexOf(key)>=0)result=result.split(key).join(dict[key]);
 });
 return result;
}

function translateCore(value,language){
 if(!value||language==="es")return value;
 var dict=dictionaries[language]||{};
 if(Object.prototype.hasOwnProperty.call(dict,value))return dict[value];

 var prefix=value.match(/^([^A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]*)(.+)$/);
 if(prefix&&prefix[1]&&Object.prototype.hasOwnProperty.call(dict,prefix[2])){
   return prefix[1]+dict[prefix[2]];
 }

 // Many cards render several independently translatable values in one text node.
 // Translate each middle-dot segment so strings such as
 // "Sin área · ⏱ Sin estimar" do not remain partly Spanish.
 if(value.indexOf(" · ")>=0){
   var parts=value.split(" · ");
   var changed=false;
   var translated=parts.map(function(part){
     var next=translateCore(part,language);
     if(next!==part)changed=true;
     return next;
   });
   if(changed)return translated.join(" · ");
 }

 var dynamicValue=translateDynamic(value,language);
 if(dynamicValue!==value)return translateKnownFragments(dynamicValue,language);
 if(prefix&&prefix[1]){
   var translatedRest=translateDynamic(prefix[2],language);
   if(translatedRest!==prefix[2])return prefix[1]+translateKnownFragments(translatedRest,language);
 }

 return translateKnownFragments(translateBackendPhrases(value,language),language);
}
function translateString(value,language){
 var raw=String(value==null?"":value);
 var m=raw.match(/^(\s*)([\s\S]*?)(\s*)$/);
 if(!m)return raw;
 return m[1]+translateCore(m[2],language)+m[3];
}

function translateDialog(value,language){
 if(language==="es")return String(value==null?"":value);
 var raw=String(value==null?"":value);
 var exact=(alertExact[language]||{})[raw];
 if(exact)return exact;
 var list=alertPatterns[language]||[];
 for(var i=0;i<list.length;i++){
   if(list[i][0].test(raw))return raw.replace(list[i][0],list[i][1]);
 }
 return translateCore(raw,language);
}

function translateTextNode(node){
 if(!textSource.has(node))textSource.set(node,node.nodeValue);
 var src=textSource.get(node);
 var next=translateString(src,currentLanguage);
 if(node.nodeValue!==next)node.nodeValue=next;
}

function translateElement(el){
 if(!el||el.nodeType!==1)return;
 var tag=el.tagName;
 if(tag==="SCRIPT"||tag==="STYLE"||tag==="CODE"||tag==="PRE")return;
 ["placeholder","title","aria-label"].forEach(function(attr){
   if(!el.hasAttribute(attr))return;
   var record=attrSource.get(el)||{};
   if(!Object.prototype.hasOwnProperty.call(record,attr))record[attr]=el.getAttribute(attr);
   attrSource.set(el,record);
   el.setAttribute(attr,translateString(record[attr],currentLanguage));
 });
 for(var n=el.firstChild;n;n=n.nextSibling){
   if(n.nodeType===3)translateTextNode(n);
   else if(n.nodeType===1)translateElement(n);
 }
}

function applyAppTranslations(root){
 document.documentElement.lang=currentLanguage;
 translateElement(root||document.body);
}

var nativeAlert=window.alert.bind(window);
var nativeConfirm=window.confirm.bind(window);
var nativePrompt=window.prompt?window.prompt.bind(window):null;
window.alert=function(message){return nativeAlert(translateDialog(message,currentLanguage));};
window.confirm=function(message){return nativeConfirm(translateDialog(message,currentLanguage));};
if(nativePrompt)window.prompt=function(message,defaultValue){return nativePrompt(translateDialog(message,currentLanguage),defaultValue);};

window.appLocale=function(){
 return currentLanguage==="de"?"de-CH":currentLanguage==="en"?"en-GB":"es-ES";
};
window.appTranslate=function(value){return translateDialog(value,currentLanguage);};
window.setAppLanguage=function(language){
 currentLanguage=supported[language]?language:"es";
 window.APP_LANGUAGE=currentLanguage;
 if(document.body)applyAppTranslations(document.body);
};
window.getAppLanguage=function(){return currentLanguage;};
window.applyAppTranslations=applyAppTranslations;

document.addEventListener("DOMContentLoaded",function(){
 var observer=new MutationObserver(function(mutations){
   mutations.forEach(function(m){
     if(m.type==="characterData"&&m.target.parentElement)translateTextNode(m.target);
     Array.prototype.forEach.call(m.addedNodes||[],function(n){
       if(n.nodeType===3)translateTextNode(n);
       else if(n.nodeType===1)translateElement(n);
     });
   });
 });
 observer.observe(document.body,{subtree:true,childList:true,characterData:true});
 applyAppTranslations(document.body);
});
})();
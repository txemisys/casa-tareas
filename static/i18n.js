(function(){
"use strict";

var currentLanguage="es";
var textSource=new WeakMap();
var attrSource=new WeakMap();
var supported={es:true,en:true,de:true};

var EN={
"Tablero":"Dashboard","Tareas":"Tasks","Agenda":"Calendar","Áreas":"Areas","Personas":"People","Gastos":"Expenses","Historial":"History","Configuración":"Settings",
"Deshacer":"Undo","Nueva tarea":"New task","Cargando Casa Tareas…":"Loading Casa Tareas…",
"Si este mensaje permanece, el navegador no ha podido ejecutar el JavaScript de la aplicación.":"If this message remains, the browser could not run the application's JavaScript.",
"Hoy":"Today","Mañana":"Tomorrow","Editar":"Edit","Eliminar":"Delete","Guardar":"Save","Cancelar":"Cancel","Restaurar":"Restore","Archivar":"Archive",
"Activa":"Active","Eliminada":"Deleted","Activo":"Active","Detenido":"Stopped","Sin área":"No area","Sin responsable":"No owner","Sin estimar":"Not estimated",
"Todas":"All","Sugeridas ahora":"Suggested now","Tareas recurrentes cerca de su ciclo. Nada entra en Hoy automáticamente.":"Recurring tasks close to their cycle. Nothing is added to Today automatically.",
"No hay tareas que necesiten atención ahora.":"No tasks need attention right now.","No hay personas configuradas.":"No people configured.",
"Personas":"People","Gestiona quién puede figurar como autor de una tarea.":"Manage who can be shown as the author of a task.","Nueva persona":"New person",
"Configuración":"Settings","Ajustes de Casa Tareas sin editar archivos del servidor.":"Casa Tareas settings without editing server files.",
"Configurado":"Configured","Sin configurar":"Not configured","Origen del token":"Token source","Grupo":"Group","Último contacto":"Last contact",
"Funcionamiento":"Operation","Zona horaria":"Time zone","Idioma":"Language","Español":"Spanish","Inglés":"English","Alemán":"German",
"Revisar recordatorios Telegram cada":"Check Telegram reminders every","Sincronizar calendarios cada":"Sync calendars every","Máximo por adjunto":"Maximum per attachment",
"segundos":"seconds","minutos":"minutes","Guardar ajustes":"Save settings",
"Estos cambios se aplican en caliente. El puerto HTTP sigue siendo una opción de Docker y no se cambia desde la aplicación.":"These changes apply immediately. The HTTP port remains a Docker option and is not changed from the application.",
"Gastos de comida":"Food expenses","Conecta Casa Tareas con el histórico de compras mediante la API interna.":"Connect Casa Tareas to purchase history through the internal API.",
"URL del servicio":"Service URL","Probar conexión":"Test connection","Desconectar":"Disconnect","Última prueba correcta":"Last successful test","Último error":"Last error",
"Diagnóstico":"Diagnostics","Versión":"Version","Calendarios externos":"External calendars","Documentos":"Documents","Datos persistentes":"Persistent data",
"Acceso":"Access","Zona peligrosa":"Danger zone","Borrar datos de Casa Tareas":"Delete Casa Tareas data","Borrar datos de Gastos":"Delete Expenses data",
"Inventario":"Inventory","Comprar":"Shopping","Nuevo producto":"New product","Producto":"Product","Categoría":"Category","Unidad":"Unit","Qué comprar":"What to buy","Estado":"Status",
"Producto correspondiente en Gastos":"Matching product in Expenses","Sin vincular":"Not linked","Hay":"In stock","Poco":"Low","Falta":"Out","Repuesto":"Restocked",
"Plan de compra por supermercado":"Shopping plan by supermarket","Plan de compra":"Shopping plan","Cargando recomendaciones…":"Loading recommendations…","Calculando supermercados…":"Calculating supermarkets…",
"Sin recomendación":"No recommendation","Abrir inventario":"Open inventory","Por comprar":"To buy","Últimos tickets":"Latest receipts","Ver todos":"View all",
"Evolución anual":"Yearly trend","Total mensual y desglose por usuario.":"Monthly total and breakdown by user.","Estado":"Status","Tickets":"Receipts","Productos":"Products","Líneas":"Lines",
"Resumen":"Summary","Análisis":"Analysis","Listas":"Lists","Nuevo ticket":"New receipt","Editar ticket":"Edit receipt","Supermercado":"Supermarket","Fecha":"Date","Artículo":"Item",
"Cantidad":"Quantity","Precio":"Price","Precio neto":"Net price","Descuento":"Discount","Usuario":"User","Total":"Total","Filtros":"Filters","Desde":"From","Hasta":"To",
"Buscar":"Search","Limpiar":"Clear","Resultados":"Results","Sin precio histórico":"No price history","Media":"Average","Último":"Latest",
"Precio medio":"Average price","Mejor precio histórico":"Best historical price","Supermercado recomendado":"Recommended supermarket","Supermercado habitual":"Usual supermarket",
"Comparativa por supermercado":"Comparison by supermarket","Compras":"Purchases","Última compra":"Last purchase","Gasto total":"Total spend",
"Calendarios externos":"External calendars","Añadir":"Add","Sincronizar":"Sync","Sincronizar todos":"Sync all","Todavía sin sincronizar":"Not synced yet",
"Enviar prueba":"Send test","Cambiar grupo":"Change group","Desconectar grupo":"Disconnect group","Detectar grupos":"Detect groups",
"Guardar y validar":"Save and validate","Sustituir":"Replace","Eliminar token guardado":"Delete saved token",
"Sin comunicación todavía":"No communication yet","Sin grupo seleccionado":"No group selected","No configurado":"Not configured","Gestionado por .env / entorno":"Managed by .env / environment","Guardado en Casa Tareas":"Saved in Casa Tareas",
"Historial":"History","Realizaciones y reparto de los últimos 30 días.":"Completions and distribution over the last 30 days.","Todavía no hay realizaciones.":"No completions yet.",
"Actividad reciente":"Recent activity","Desde tu última visita":"Since your last visit","Cambios realizados desde este navegador.":"Changes made from this browser.","Marcar como visto":"Mark as seen",
"Documentos":"Documents","Sin documentos adjuntos.":"No attached documents.","Subir documento":"Upload document",
"Agenda":"Calendar","Nuevo evento":"New event","Avisos del navegador":"Browser notifications","Próximos":"Upcoming","Pasados":"Past","Visto":"Seen",
"Todo el día":"All day","A la hora":"At the time","Calendario externo":"External calendar",
"No falta ningún producto.":"No products are missing.","Todavía no hay productos.":"No products yet.","Añadido manualmente a Comprar.":"Manually added to Shopping.",
"Automático":"Automatic","Manual":"Manual","vinculado":"linked","sin vincular":"not linked","Guardar":"Save","Cerrar":"Close"
};

var DE={
"Tablero":"Übersicht","Tareas":"Aufgaben","Agenda":"Kalender","Áreas":"Bereiche","Personas":"Personen","Gastos":"Ausgaben","Historial":"Verlauf","Configuración":"Einstellungen",
"Deshacer":"Rückgängig","Nueva tarea":"Neue Aufgabe","Cargando Casa Tareas…":"Casa Tareas wird geladen…",
"Si este mensaje permanece, el navegador no ha podido ejecutar el JavaScript de la aplicación.":"Wenn diese Meldung bleibt, konnte der Browser das JavaScript der Anwendung nicht ausführen.",
"Hoy":"Heute","Mañana":"Morgen","Editar":"Bearbeiten","Eliminar":"Löschen","Guardar":"Speichern","Cancelar":"Abbrechen","Restaurar":"Wiederherstellen","Archivar":"Archivieren",
"Activa":"Aktiv","Eliminada":"Gelöscht","Activo":"Aktiv","Detenido":"Gestoppt","Sin área":"Ohne Bereich","Sin responsable":"Ohne Verantwortlichen","Sin estimar":"Nicht geschätzt",
"Todas":"Alle","Sugeridas ahora":"Jetzt vorgeschlagen","Tareas recurrentes cerca de su ciclo. Nada entra en Hoy automáticamente.":"Wiederkehrende Aufgaben nahe an ihrem Zyklus. Nichts wird automatisch zu Heute hinzugefügt.",
"No hay tareas que necesiten atención ahora.":"Derzeit benötigen keine Aufgaben Aufmerksamkeit.","No hay personas configuradas.":"Keine Personen konfiguriert.",
"Gestiona quién puede figurar como autor de una tarea.":"Verwalte, wer als Autor einer Aufgabe erscheinen kann.","Nueva persona":"Neue Person",
"Ajustes de Casa Tareas sin editar archivos del servidor.":"Casa-Tareas-Einstellungen ohne Serverdateien zu bearbeiten.",
"Configurado":"Konfiguriert","Sin configurar":"Nicht konfiguriert","Origen del token":"Token-Quelle","Grupo":"Gruppe","Último contacto":"Letzter Kontakt",
"Funcionamiento":"Betrieb","Zona horaria":"Zeitzone","Idioma":"Sprache","Español":"Spanisch","Inglés":"Englisch","Alemán":"Deutsch",
"Revisar recordatorios Telegram cada":"Telegram-Erinnerungen prüfen alle","Sincronizar calendarios cada":"Kalender synchronisieren alle","Máximo por adjunto":"Maximal pro Anhang",
"segundos":"Sekunden","minutos":"Minuten","Guardar ajustes":"Einstellungen speichern",
"Estos cambios se aplican en caliente. El puerto HTTP sigue siendo una opción de Docker y no se cambia desde la aplicación.":"Diese Änderungen werden sofort übernommen. Der HTTP-Port bleibt eine Docker-Option und wird nicht in der Anwendung geändert.",
"Gastos de comida":"Lebensmittelausgaben","Conecta Casa Tareas con el histórico de compras mediante la API interna.":"Casa Tareas über die interne API mit der Einkaufshistorie verbinden.",
"URL del servicio":"Service-URL","Probar conexión":"Verbindung testen","Desconectar":"Trennen","Última prueba correcta":"Letzter erfolgreicher Test","Último error":"Letzter Fehler",
"Diagnóstico":"Diagnose","Versión":"Version","Calendarios externos":"Externe Kalender","Documentos":"Dokumente","Datos persistentes":"Persistente Daten",
"Acceso":"Zugriff","Zona peligrosa":"Gefahrenzone","Borrar datos de Casa Tareas":"Casa-Tareas-Daten löschen","Borrar datos de Gastos":"Ausgabendaten löschen",
"Inventario":"Inventar","Comprar":"Einkaufen","Nuevo producto":"Neues Produkt","Producto":"Produkt","Categoría":"Kategorie","Unidad":"Einheit","Qué comprar":"Was kaufen","Estado":"Status",
"Producto correspondiente en Gastos":"Passendes Produkt in Ausgaben","Sin vincular":"Nicht verknüpft","Hay":"Vorhanden","Poco":"Wenig","Falta":"Fehlt","Repuesto":"Nachgefüllt",
"Plan de compra por supermercado":"Einkaufsplan nach Supermarkt","Plan de compra":"Einkaufsplan","Cargando recomendaciones…":"Empfehlungen werden geladen…","Calculando supermercados…":"Supermärkte werden berechnet…",
"Sin recomendación":"Keine Empfehlung","Abrir inventario":"Inventar öffnen","Por comprar":"Zu kaufen","Últimos tickets":"Letzte Belege","Ver todos":"Alle anzeigen",
"Evolución anual":"Jahresentwicklung","Total mensual y desglose por usuario.":"Monatssumme und Aufschlüsselung nach Benutzer.","Tickets":"Belege","Productos":"Produkte","Líneas":"Positionen",
"Resumen":"Übersicht","Análisis":"Analyse","Listas":"Listen","Nuevo ticket":"Neuer Beleg","Editar ticket":"Beleg bearbeiten","Supermercado":"Supermarkt","Fecha":"Datum","Artículo":"Artikel",
"Cantidad":"Menge","Precio":"Preis","Precio neto":"Nettopreis","Descuento":"Rabatt","Usuario":"Benutzer","Total":"Summe","Filtros":"Filter","Desde":"Von","Hasta":"Bis",
"Buscar":"Suchen","Limpiar":"Zurücksetzen","Resultados":"Ergebnisse","Sin precio histórico":"Keine Preishistorie","Media":"Durchschnitt","Último":"Letzter",
"Precio medio":"Durchschnittspreis","Mejor precio histórico":"Historisch bester Preis","Supermercado recomendado":"Empfohlener Supermarkt","Supermercado habitual":"Üblicher Supermarkt",
"Comparativa por supermercado":"Vergleich nach Supermarkt","Compras":"Einkäufe","Última compra":"Letzter Einkauf","Gasto total":"Gesamtausgaben",
"Añadir":"Hinzufügen","Sincronizar":"Synchronisieren","Sincronizar todos":"Alle synchronisieren","Todavía sin sincronizar":"Noch nicht synchronisiert",
"Enviar prueba":"Test senden","Cambiar grupo":"Gruppe wechseln","Desconectar grupo":"Gruppe trennen","Detectar grupos":"Gruppen erkennen",
"Guardar y validar":"Speichern und prüfen","Sustituir":"Ersetzen","Eliminar token guardado":"Gespeicherten Token löschen",
"Sin comunicación todavía":"Noch keine Kommunikation","Sin grupo seleccionado":"Keine Gruppe ausgewählt","No configurado":"Nicht konfiguriert","Gestionado por .env / entorno":"Über .env / Umgebung verwaltet","Guardado en Casa Tareas":"In Casa Tareas gespeichert",
"Realizaciones y reparto de los últimos 30 días.":"Erledigungen und Verteilung der letzten 30 Tage.","Todavía no hay realizaciones.":"Noch keine Erledigungen.",
"Actividad reciente":"Letzte Aktivität","Desde tu última visita":"Seit deinem letzten Besuch","Cambios realizados desde este navegador.":"Änderungen aus diesem Browser.","Marcar como visto":"Als gesehen markieren",
"Sin documentos adjuntos.":"Keine angehängten Dokumente.","Subir documento":"Dokument hochladen",
"Nuevo evento":"Neuer Termin","Avisos del navegador":"Browser-Benachrichtigungen","Próximos":"Bevorstehend","Pasados":"Vergangen","Visto":"Gesehen",
"Todo el día":"Ganztägig","A la hora":"Zum Zeitpunkt","Calendario externo":"Externer Kalender",
"No falta ningún producto.":"Keine Produkte fehlen.","Todavía no hay productos.":"Noch keine Produkte.","Añadido manualmente a Comprar.":"Manuell zur Einkaufsliste hinzugefügt.",
"Automático":"Automatisch","Manual":"Manuell","vinculado":"verknüpft","sin vincular":"nicht verknüpft","Cerrar":"Schließen"
};

var dictionaries={en:EN,de:DE};

var patterns={
en:[
[/^(\d+) d pendiente$/,"$1 d overdue"],[/^En (\d+) días$/,"In $1 days"],[/^(\d+) tareas · 30 días$/,"$1 tasks · 30 days"],
[/^(\d+) producto$/,"$1 product"],[/^(\d+) productos$/,"$1 products"],[/^(\d+) artículos más$/,"$1 more items"],
[/^Comprar: (.+)$/,"Buy: $1"],[/^Necesario para: (.+)$/,"Needed for: $1"],[/^Falta: (.+)$/,"Missing: $1"],
[/^Pausada hasta (.+)$/,"Paused until $1"],[/^Responsable: (.+)$/,"Owner: $1"],[/^Sincronizado (.+)$/,"Synced $1"],
[/^Ahorro aprox\. (.+)$/,"Approx. saving $1"],[/^Ahorro estimado · (.+)$/,"Estimated saving · $1"],[/^Media (.+)$/,"Average $1"],[/^Último (.+)$/,"Latest $1"]
],
de:[
[/^(\d+) d pendiente$/,"$1 T. überfällig"],[/^En (\d+) días$/,"In $1 Tagen"],[/^(\d+) tareas · 30 días$/,"$1 Aufgaben · 30 Tage"],
[/^(\d+) producto$/,"$1 Produkt"],[/^(\d+) productos$/,"$1 Produkte"],[/^(\d+) artículos más$/,"$1 weitere Artikel"],
[/^Comprar: (.+)$/,"Kaufen: $1"],[/^Necesario para: (.+)$/,"Benötigt für: $1"],[/^Falta: (.+)$/,"Fehlt: $1"],
[/^Pausada hasta (.+)$/,"Pausiert bis $1"],[/^Responsable: (.+)$/,"Verantwortlich: $1"],[/^Sincronizado (.+)$/,"Synchronisiert $1"],
[/^Ahorro aprox\. (.+)$/,"Ca. Ersparnis $1"],[/^Ahorro estimado · (.+)$/,"Geschätzte Ersparnis · $1"],[/^Media (.+)$/,"Durchschnitt $1"],[/^Último (.+)$/,"Letzter $1"]
]};

function translateCore(value,language){
 if(!value||language==="es")return value;
 var dict=dictionaries[language]||{};
 if(Object.prototype.hasOwnProperty.call(dict,value))return dict[value];
 var prefixed=value.match(/^([^A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]*)(.+)$/);
 if(prefixed&&prefixed[1]&&Object.prototype.hasOwnProperty.call(dict,prefixed[2])){
   return prefixed[1]+dict[prefixed[2]];
 }
 var list=patterns[language]||[];
 for(var i=0;i<list.length;i++){
   if(list[i][0].test(value))return value.replace(list[i][0],list[i][1]);
   if(prefixed&&prefixed[1]&&list[i][0].test(prefixed[2])){
     return prefixed[1]+prefixed[2].replace(list[i][0],list[i][1]);
   }
 }
 return value;
}

function translateString(value,language){
 var m=String(value).match(/^(\s*)([\s\S]*?)(\s*)$/);
 if(!m)return value;
 return m[1]+translateCore(m[2],language)+m[3];
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

window.appLocale=function(){
 return currentLanguage==="de"?"de-CH":currentLanguage==="en"?"en-GB":"es-ES";
};

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
var gastosSection="summary";
var gastosDashboard=null;
var gastosTickets=[];
var gastosProducts=[];
var gastosProductQuery="";
var gastosFilters={article:"",user:"",supermarket:"",start_date:"",end_date:"",chart_year:new Date().getFullYear()};

function gastosMoney(value){return new Intl.NumberFormat("es-ES",{style:"currency",currency:"EUR"}).format(Number(value||0))}
function gastosNumber(value,digits){return new Intl.NumberFormat("es-ES",{maximumFractionDigits:digits==null?2:digits}).format(Number(value||0))}
function gastosDate(value){if(!value)return"";var d=new Date(value+"T12:00:00");return new Intl.DateTimeFormat("es-ES",{day:"2-digit",month:"short",year:"numeric"}).format(d)}
function gastosIntegrationReady(){return !!(state.settings&&state.settings.integrations&&state.settings.integrations.gastos_comida&&state.settings.integrations.gastos_comida.configured)}
function gastosSubnav(){var entries=[["summary","Resumen"],["tickets","Tickets"],["analysis","Análisis"],["products","Productos"],["lookups","Listas"]];return '<div class="gastos-subnav">'+entries.map(function(x){return'<button class="'+(gastosSection===x[0]?"active":"")+'" onclick="gastosGo(\''+x[0]+'\')">'+x[1]+"</button>"}).join("")+"</div>"}
function gastosQuery(){var p=new URLSearchParams();["article","user","supermarket","start_date","end_date"].forEach(function(k){if(gastosFilters[k])p.set(k,gastosFilters[k])});if(gastosFilters.chart_year)p.set("chart_year",String(gastosFilters.chart_year));var q=p.toString();return q?"?"+q:""}

async function renderGastos(){
  var main=document.getElementById("main");
  main.innerHTML='<div class="pagehead"><div><h1>🛒 Gastos</h1><div class="subtitle">Compras, tickets, análisis y productos con la misma experiencia de Casa Tareas.</div></div><button class="primary" onclick="openGastosTicket()">+ Nuevo ticket</button></div><div id="gastosRoot" class="gastos-shell"><div class="gastos-loading">Cargando gastos…</div></div>';
  if(!gastosIntegrationReady()){
    document.getElementById("gastosRoot").innerHTML='<div class="gastos-error"><strong>Gastos de comida no está configurado.</strong><br>Configura la integración en Configuración y vuelve a esta sección.<div class="settings-actions" style="margin-top:10px"><button class="primary" onclick="go(\'settings\')">Abrir Configuración</button></div></div>';
    return;
  }
  try{
    await loadGastosDashboard();
  }catch(e){
    var root=document.getElementById("gastosRoot");
    if(root)root.innerHTML='<div class="gastos-error"><strong>No se pudo cargar Gastos.</strong><br>'+esc(e.message)+'<div class="settings-actions" style="margin-top:10px"><button class="primary" onclick="renderGastos()">Reintentar</button><button class="ghost" onclick="go(\'settings\')">Configuración</button></div></div>';
  }
}
async function loadGastosDashboard(){
  gastosDashboard=await api("/api/gastos/dashboard"+gastosQuery());
  renderGastosContent();
}
async function gastosGo(section){
  gastosSection=section;
  var root=document.getElementById("gastosRoot");
  if(root)root.innerHTML=gastosSubnav()+'<div class="gastos-loading">Cargando…</div>';
  try{
    if(!gastosDashboard)await loadGastosDashboard();
    if(section==="tickets"&&!gastosTickets.length)await loadGastosTickets();
    if(section==="products"&&!gastosProducts.length)await loadGastosProducts();
    renderGastosContent();
  }catch(e){
    if(root)root.innerHTML=gastosSubnav()+'<div class="gastos-error">'+esc(e.message)+'</div>';
  }
}
function renderGastosContent(){
  var root=document.getElementById("gastosRoot");if(!root||!gastosDashboard)return;
  var body="";
  if(gastosSection==="summary")body=renderGastosSummary();
  if(gastosSection==="tickets")body=renderGastosTickets();
  if(gastosSection==="analysis")body=renderGastosAnalysis();
  if(gastosSection==="products")body=renderGastosProducts();
  if(gastosSection==="lookups")body=renderGastosLookups();
  root.innerHTML=gastosSubnav()+body;
}
function renderGastosMetrics(){
  var metrics=gastosDashboard.metrics||[];
  return '<div class="gastos-metrics">'+metrics.map(function(m){var users=(m.user_values||[]).map(function(u){return'<span>'+esc(u.user_name)+' · '+esc(gastosMoney(u.value))+'</span>'}).join("");return'<article class="gastos-metric"><div class="gastos-metric-label">'+esc(m.label)+'</div><div class="gastos-metric-value">'+esc(gastosMoney(m.value))+'</div>'+(users?'<div class="gastos-user-values">'+users+'</div>':"")+'</article>'}).join("")+"</div>";
}
function gastosTicketCard(ticket,compact){
  var items=(ticket.items||[]);
  var shown=compact?items.slice(0,3):items;
  var itemHtml=shown.map(function(i){return'<div>'+esc(i.article)+' · '+gastosNumber(i.quantity,2)+' · '+esc(i.user_name||"")+' · <strong>'+esc(gastosMoney(i.total))+'</strong></div>'}).join("");
  if(compact&&items.length>3)itemHtml+='<div class="muted">+'+(items.length-3)+' artículos más</div>';
  return '<article class="gastos-ticket"><div class="gastos-ticket-top"><div><div class="gastos-ticket-title">'+esc(ticket.supermarket)+'</div><div class="gastos-ticket-meta">'+esc(gastosDate(ticket.date))+' · '+items.length+' líneas</div></div><div class="gastos-ticket-total">'+esc(gastosMoney(ticket.total))+'</div></div><div class="gastos-ticket-items">'+itemHtml+'</div><div class="gastos-ticket-actions"><button class="ghost" onclick="openGastosTicket('+ticket.id+')">Editar</button><button class="danger" onclick="deleteGastosTicket('+ticket.id+')">Eliminar</button></div></article>';
}
function renderGastosSummary(){
  var d=gastosDashboard,f=d.filters||{},recent=d.recent_tickets||[],counts=d.counts||{},shopping=state.shopping_list||[];
  if(shopping.length&&typeof loadShoppingPlan==="function")loadShoppingPlan(false);
  var planGroups=(shoppingPlan&&shoppingPlan.groups)||[];
  var totalSaving=Number((shoppingPlan&&shoppingPlan.estimated_saving_unit_total)||0);
  var shoppingBody="";
  if(!shopping.length){
    shoppingBody='<div class="gastos-empty">La lista de compra está vacía.</div>';
  }else if(planGroups.length){
    var savingBanner=totalSaving>0?'<div class="gastos-ticket"><div class="gastos-ticket-title">💶 Ahorro estimado · '+esc(gastosMoney(totalSaving))+'/u.</div><div class="gastos-ticket-meta">Comparación contra el precio medio del supermercado habitual para los productos con histórico comparable. No representa todavía el total real de la cesta.</div></div>':"";
    shoppingBody=savingBanner+'<div class="gastos-ticket-list">'+planGroups.map(function(group){
      var groupSaving=Number(group.estimated_saving_unit_total||0);
      return '<article class="gastos-ticket"><div class="gastos-ticket-top"><div><div class="gastos-ticket-title">🛒 '+esc(group.supermarket)+'</div><div class="gastos-ticket-meta">'+group.count+' producto'+(group.count===1?"":"s")+(group.priced_count?' · aprox. '+esc(gastosMoney(group.estimated_unit_total))+' base/u.':'')+(groupSaving>0?' · ahorro aprox. '+esc(gastosMoney(groupSaving))+'/u.':'')+'</div></div></div><div class="gastos-ticket-items">'+group.items.map(function(item){
        var rec=item.recommended_supermarket,last=item.last_purchase,saving=Number(item.estimated_saving_unit||0);
        return '<div class="gastos-ticket-item"><div><strong>'+esc(item.name)+'</strong><div class="muted">'+esc(item.purchase_quantity||item.category||"")+(item.gastos_product_id?' · vinculado':' · sin vincular')+(saving>0?' · ahorra aprox. '+esc(gastosMoney(saving))+'/u.':'')+'</div></div><div class="muted">'+(rec&&rec.average_unit_price!=null?'Media '+esc(gastosMoney(rec.average_unit_price))+'/u.':(last&&last.unit_price!=null?'Último '+esc(gastosMoney(last.unit_price))+'/u.':'Sin precio histórico'))+'</div></div>';
      }).join("")+'</div></article>';
    }).join("")+'</div>';
  }else{
    shoppingBody='<div class="gastos-ticket-list">'+shopping.map(function(item){return'<article class="gastos-ticket"><div class="gastos-ticket-top"><div><div class="gastos-ticket-title">'+esc(item.name)+'</div><div class="gastos-ticket-meta">'+esc(item.purchase_quantity||item.category||"")+(item.gastos_linked?' · vinculado con Gastos':' · sin vincular')+'</div></div><span class="status '+(item.gastos_linked?'':'off')+'">'+(item.gastos_linked?'Automático':'Manual')+'</span></div></article>'}).join("")+'</div>';
  }
  var shoppingPanel='<section class="gastos-panel"><div class="gastos-panel-head"><div><h2>🧺 Por comprar</h2><p>Productos de Casa Tareas agrupados por supermercado recomendado cuando hay histórico suficiente.</p></div><button class="secondary" onclick="taskSection=\'inventory\';go(\'tasks\')">Abrir inventario</button></div>'+shoppingBody+'</section>';
  return renderGastosMetrics()+'<div class="gastos-grid"><section class="gastos-panel"><div class="gastos-panel-head"><div><h2>Evolución anual</h2><p>Total mensual y desglose por usuario.</p></div><select onchange="gastosChangeYear(this.value)">'+(d.years||[]).map(function(y){return'<option value="'+y+'" '+(Number(f.chart_year)===Number(y)?"selected":"")+'>'+y+'</option>'}).join("")+'</select></div>'+gastosChart(f.chart_labels||[],f.chart_datasets||[])+'</section><section class="gastos-panel"><div class="gastos-panel-head"><div><h2>Estado</h2><p>Datos disponibles en Gastos.</p></div></div><div class="gastos-product-stats"><div class="gastos-product-stat"><span>Tickets</span><strong>'+Number(counts.tickets||0)+'</strong></div><div class="gastos-product-stat"><span>Productos</span><strong>'+Number(counts.products||0)+'</strong></div><div class="gastos-product-stat"><span>Líneas</span><strong>'+Number(counts.items||0)+'</strong></div><div class="gastos-product-stat"><span>Por comprar</span><strong>'+shopping.length+'</strong></div></div></section></div>'+shoppingPanel+'<section class="gastos-panel"><div class="gastos-panel-head"><div><h2>Últimos tickets</h2><p>Las compras más recientes.</p></div><button class="secondary" onclick="gastosGo(\'tickets\')">Ver todos</button></div><div class="gastos-ticket-list">'+(recent.length?recent.map(function(t){return gastosTicketCard(t,true)}).join(""):'<div class="gastos-empty">Todavía no hay tickets.</div>')+"</div></section>";
}
function gastosChangeYear(value){gastosFilters.chart_year=Number(value)||new Date().getFullYear();loadGastosDashboard().catch(function(e){alert(e.message)})}
function gastosChart(labels,datasets){
  if(!datasets||!datasets.length)return'<div class="gastos-empty">No hay datos para la gráfica.</div>';
  var colors=["#246bfe","#21a56b","#d68b2c","#8a62d3","#d45768","#2c9bad","#7b8798"];
  var all=[];datasets.forEach(function(ds){(ds.data||[]).forEach(function(v){all.push(Number(v||0))})});
  var max=Math.max.apply(null,all.concat([1]));var top=Math.ceil(max/10)*10||10;
  var W=760,H=260,left=48,right=18,topPad=18,bottom=34,plotW=W-left-right,plotH=H-topPad-bottom;
  var svg='<svg class="gastos-chart" viewBox="0 0 '+W+' '+H+'" role="img" aria-label="Gráfica anual de gastos">';
  for(var g=0;g<=4;g++){var y=topPad+(plotH*g/4);var val=top*(1-g/4);svg+='<line class="gastos-chart-grid" x1="'+left+'" y1="'+y+'" x2="'+(W-right)+'" y2="'+y+'"></line><text class="gastos-chart-axis" x="4" y="'+(y+3)+'">'+esc(gastosNumber(val,0))+' €</text>'}
  labels.forEach(function(l,i){var x=left+(plotW*(i/(Math.max(labels.length-1,1))));svg+='<text class="gastos-chart-axis" text-anchor="middle" x="'+x+'" y="'+(H-8)+'">'+esc(l)+'</text>'});
  datasets.forEach(function(ds,di){var pts=(ds.data||[]).map(function(v,i){var x=left+(plotW*(i/(Math.max(labels.length-1,1))));var y=topPad+plotH-(Number(v||0)/top*plotH);return[x,y]});var color=colors[di%colors.length];svg+='<polyline class="gastos-chart-line" stroke="'+color+'" points="'+pts.map(function(p){return p[0]+","+p[1]}).join(" ")+'"></polyline>';pts.forEach(function(p){svg+='<circle class="gastos-chart-dot" fill="'+color+'" cx="'+p[0]+'" cy="'+p[1]+'" r="4"></circle>'})});
  svg+="</svg>";
  var legend='<div class="gastos-chart-legend">'+datasets.map(function(ds,i){return'<span class="gastos-chart-key"><i style="background:'+colors[i%colors.length]+'"></i>'+esc(ds.label||"Serie")+'</span>'}).join("")+"</div>";
  return'<div class="gastos-chart-wrap">'+svg+"</div>"+legend;
}
async function loadGastosTickets(){var r=await api("/api/gastos/tickets?limit=500");gastosTickets=r.items||[]}
function renderGastosTickets(){
  var list=gastosTickets||[];
  return '<section class="gastos-panel"><div class="gastos-panel-head"><div><h2>Tickets</h2><p>Alta, edición y eliminación de compras completas.</p></div><button class="primary" onclick="openGastosTicket()">+ Nuevo ticket</button></div><div class="gastos-ticket-list">'+(list.length?list.map(function(t){return gastosTicketCard(t,false)}).join(""):'<div class="gastos-empty">No hay tickets.</div>')+"</div></section>";
}
function gastosDatalist(id,values){return'<datalist id="'+id+'">'+(values||[]).map(function(v){return'<option value="'+esc(v)+'"></option>'}).join("")+"</datalist>"}
async function openGastosTicket(id){
  try{
    var ticket=null;
    if(id){ticket=(gastosTickets||[]).find(function(t){return t.id===id})||(gastosDashboard.recent_tickets||[]).find(function(t){return t.id===id});if(!ticket)ticket=await api("/api/gastos/tickets/"+id)}
    var look=(gastosDashboard&&gastosDashboard.lookups)||{articles:[],users:[],supermarkets:[]};
    var html='<div class="modalhead"><div><h2>'+(ticket?"Editar ticket":"Nuevo ticket")+'</h2><div class="muted">Precio neto tiene prioridad; si está vacío se aplican descuento o porcentaje.</div></div><button class="ghost" onclick="gastosCloseModal()">×</button></div><form id="gastosTicketForm" class="gastos-ticket-form" onsubmit="return false"><div class="gastos-ticket-basic"><div class="field"><label>Fecha</label><input name="purchase_date" type="date" required value="'+esc(ticket?ticket.date:localDateValue(0))+'"></div><div class="field"><label>Supermercado</label><input name="supermarket" list="gastosSupermarkets" required value="'+esc(ticket?ticket.supermarket:"")+'" placeholder="Supermercado"></div></div>'+gastosDatalist("gastosSupermarkets",look.supermarkets)+gastosDatalist("gastosArticles",look.articles)+gastosDatalist("gastosUsers",look.users)+'<div class="gastos-panel-head"><div><h3>Artículos</h3><p>Todos los campos de la aplicación original siguen disponibles.</p></div><button class="secondary" type="button" onclick="gastosAddItemRow()">+ Artículo</button></div><div id="gastosItems" class="gastos-items"></div><div class="gastos-ticket-summary"><span>Total ticket</span><strong id="gastosTicketTotal">0,00 €</strong></div></form><div class="modalfoot">'+(ticket?'<button class="danger" onclick="deleteGastosTicket('+ticket.id+',true)">Eliminar</button>':"")+'<button class="ghost" onclick="gastosCloseModal()">Cancelar</button><button class="primary" onclick="saveGastosTicket('+(ticket?ticket.id:"null")+')">Guardar</button></div>';
    showModal(html);document.getElementById("modal").classList.add("gastos-ticket-modal");
    var items=ticket&&ticket.items&&ticket.items.length?ticket.items:[null];items.forEach(function(i){gastosAddItemRow(i)});
  }catch(e){alert(e.message)}
}
function gastosCloseModal(){var m=document.getElementById("modal");if(m)m.classList.remove("gastos-ticket-modal");closeModal()}
function gastosInputValue(v){return v==null?"":String(v)}
function gastosAddItemRow(item){
  var box=document.getElementById("gastosItems");if(!box)return;
  var row=document.createElement("div");row.className="gastos-item-row";
  row.innerHTML='<div class="field article"><label>Artículo</label><input name="article" list="gastosArticles" required value="'+esc(item?item.article:"")+'"></div><div class="field"><label>Cantidad</label><input name="quantity" type="number" min="0" step="0.01" value="'+esc(item?gastosInputValue(item.quantity):"1")+'"></div><div class="field"><label>PVP</label><input name="price" type="number" min="0" step="0.01" value="'+esc(item?gastosInputValue(item.price):"0")+'"></div><div class="field"><label>Precio neto</label><input name="net_price" type="number" min="0" step="0.01" value="'+esc(item?gastosInputValue(item.net_price):"")+'" placeholder="Opcional"></div><div class="field"><label>Descuento €</label><input name="discount" type="number" min="0" step="0.01" value="'+esc(item?gastosInputValue(item.discount):"")+'" placeholder="0"></div><div class="field"><label>Descuento %</label><input name="discount_percent" type="number" min="0" step="0.01" value="'+esc(item?gastosInputValue(item.discount_percent):"")+'" placeholder="0"></div><div class="field user"><label>Usuario</label><input name="user_name" list="gastosUsers" required value="'+esc(item?item.user_name:"")+'"></div><div><label class="muted">Total</label><div class="gastos-line-total">0,00 €</div></div><button type="button" class="danger remove" onclick="gastosRemoveItemRow(this)">Quitar</button>';
  row.querySelectorAll("input").forEach(function(input){input.addEventListener("input",gastosRefreshTicketTotals);input.addEventListener("change",gastosRefreshTicketTotals)});
  box.appendChild(row);gastosRefreshTicketTotals();
}
function gastosRemoveItemRow(button){var rows=document.querySelectorAll("#gastosItems .gastos-item-row");if(rows.length<=1)return;button.closest(".gastos-item-row").remove();gastosRefreshTicketTotals()}
function gastosRowTotal(row){var q=Number(row.querySelector('[name="quantity"]').value||0),price=Number(row.querySelector('[name="price"]').value||0);var netRaw=row.querySelector('[name="net_price"]').value,discount=Number(row.querySelector('[name="discount"]').value||0),percent=Number(row.querySelector('[name="discount_percent"]').value||0);var unit=price;if(netRaw!=="")unit=Number(netRaw||0);else if(discount>0)unit=Math.max(price-discount,0);else if(percent>0)unit=Math.max(price*(1-percent/100),0);return Math.max(q,0)*Math.max(unit,0)}
function gastosRefreshTicketTotals(){var total=0;document.querySelectorAll("#gastosItems .gastos-item-row").forEach(function(row){var n=gastosRowTotal(row);total+=n;var target=row.querySelector(".gastos-line-total");if(target)target.textContent=gastosMoney(n)});var all=document.getElementById("gastosTicketTotal");if(all)all.textContent=gastosMoney(total)}
async function saveGastosTicket(id){
  var form=document.getElementById("gastosTicketForm");if(!form)return;
  var items=Array.from(document.querySelectorAll("#gastosItems .gastos-item-row")).map(function(row){return{article:row.querySelector('[name="article"]').value,quantity:row.querySelector('[name="quantity"]').value,price:row.querySelector('[name="price"]').value,net_price:row.querySelector('[name="net_price"]').value,discount:row.querySelector('[name="discount"]').value,discount_percent:row.querySelector('[name="discount_percent"]').value,user_name:row.querySelector('[name="user_name"]').value}}).filter(function(i){return i.article.trim()});
  var payload={purchase_date:form.querySelector('[name="purchase_date"]').value,supermarket:form.querySelector('[name="supermarket"]').value,items:items};
  try{
    var result=await api(id?"/api/gastos/tickets/"+id:"/api/gastos/tickets",{method:id?"PUT":"POST",body:JSON.stringify(payload)});
    gastosCloseModal();gastosDashboard=null;gastosTickets=[];
    state=await api("/api/state");
    await loadGastosDashboard();await loadGastosTickets();gastosSection="tickets";renderGastosContent();
    var restocked=result.inventory_restocked||[];
    showUndo((id?"Ticket actualizado":"Ticket creado")+(restocked.length?" · "+restocked.length+" producto"+(restocked.length===1?"":"s")+" repuesto"+(restocked.length===1?"":"s")+" en Inventario":""),null)
  }catch(e){alert(e.message)}
}
async function deleteGastosTicket(id,fromModal){if(!confirm("¿Eliminar este ticket? Esta acción elimina sus líneas de compra."))return;try{await api("/api/gastos/tickets/"+id,{method:"DELETE"});if(fromModal)gastosCloseModal();gastosDashboard=null;gastosTickets=[];await loadGastosDashboard();if(gastosSection==="tickets")await loadGastosTickets();renderGastosContent();showUndo("Ticket eliminado",null)}catch(e){alert(e.message)}}
function gastosSelect(name,values,current,allLabel){return'<select name="'+name+'"><option value="">'+esc(allLabel||"Todos")+'</option>'+(values||[]).map(function(v){return'<option value="'+esc(v)+'" '+(v===current?"selected":"")+'>'+esc(v)+'</option>'}).join("")+"</select>"}
function renderGastosAnalysis(){
  var d=gastosDashboard,f=d.filters||{},look=d.lookups||{},rows=f.filtered_results||[];
  var filters='<form id="gastosFilters" class="gastos-filters" onsubmit="applyGastosFilters();return false"><div class="field"><label>Artículo</label>'+gastosSelect("article",look.articles,gastosFilters.article,"Todos")+'</div><div class="field"><label>Usuario</label>'+gastosSelect("user",look.users,gastosFilters.user,"Todos")+'</div><div class="field"><label>Supermercado</label>'+gastosSelect("supermarket",look.supermarkets,gastosFilters.supermarket,"Todos")+'</div><div class="field"><label>Fecha inicio</label><input type="date" name="start_date" value="'+esc(gastosFilters.start_date)+'"></div><div class="field"><label>Fecha fin</label><input type="date" name="end_date" value="'+esc(gastosFilters.end_date)+'"></div><div class="field"><label>Año gráfica</label><select name="chart_year">'+(d.years||[]).map(function(y){return'<option value="'+y+'" '+(Number(gastosFilters.chart_year)===Number(y)?"selected":"")+'>'+y+'</option>'}).join("")+'</select></div></form>';
  var table='<div class="gastos-table-wrap"><table class="gastos-table"><thead><tr><th>Fecha</th><th>Supermercado</th><th>Artículo</th><th>Cantidad</th><th>Total</th><th>Usuario</th></tr></thead><tbody>'+(rows.length?rows.map(function(r){return'<tr><td>'+esc(gastosDate(r.date))+'</td><td>'+esc(r.supermarket)+'</td><td>'+esc(r.article)+'</td><td>'+gastosNumber(r.quantity,2)+'</td><td>'+esc(gastosMoney(r.total))+'</td><td>'+esc(r.user_name)+'</td></tr>'}).join(""):'<tr><td colspan="6">'+(f.has_detail_filters?"Sin resultados para los filtros seleccionados.":"Selecciona algún filtro para ver el listado detallado.")+'</td></tr>')+'</tbody>'+(rows.length?'<tfoot><tr><th colspan="4">Total</th><th>'+esc(gastosMoney(f.filtered_results_total))+'</th><th></th></tr></tfoot>':"")+"</table></div>";
  return '<section class="gastos-panel"><div class="gastos-panel-head"><div><h2>Consultas y filtros</h2><p>Filtra por artículo, usuario, supermercado y fechas.</p></div></div>'+filters+'<div class="settings-actions" style="margin-top:12px"><button class="primary" onclick="applyGastosFilters()">Aplicar filtros</button><button class="ghost" onclick="clearGastosFilters()">Limpiar</button></div></section><div class="gastos-results"><div class="gastos-result"><span>Total entre fechas</span><strong>'+esc(gastosMoney(f.totals_between_dates))+'</strong></div><div class="gastos-result"><span>Total entre fechas por usuario</span><strong>'+(f.totals_between_dates_by_user==null?"—":esc(gastosMoney(f.totals_between_dates_by_user)))+'</strong></div></div><section class="gastos-panel"><div class="gastos-panel-head"><div><h2>'+esc(f.filtered_results_title||"Resultados")+'</h2><p>'+(rows.length?rows.length+" líneas encontradas":"Detalle de compras")+'</p></div></div>'+table+'</section><section class="gastos-panel"><div class="gastos-panel-head"><div><h2>Gráfica anual</h2><p>Gasto mensual del año seleccionado y desglose por usuario.</p></div></div>'+gastosChart(f.chart_labels||[],f.chart_datasets||[])+"</section>";
}
async function applyGastosFilters(){var f=document.getElementById("gastosFilters");if(!f)return;var fd=new FormData(f);["article","user","supermarket","start_date","end_date"].forEach(function(k){gastosFilters[k]=String(fd.get(k)||"")});gastosFilters.chart_year=Number(fd.get("chart_year"))||new Date().getFullYear();try{await loadGastosDashboard()}catch(e){alert(e.message)}}
async function clearGastosFilters(){gastosFilters={article:"",user:"",supermarket:"",start_date:"",end_date:"",chart_year:new Date().getFullYear()};try{await loadGastosDashboard()}catch(e){alert(e.message)}}
async function loadGastosProducts(){var q=gastosProductQuery?"&q="+encodeURIComponent(gastosProductQuery):"";var r=await api("/api/gastos/products?limit=500"+q);gastosProducts=r.items||[]}
function renderGastosProducts(){
  var list=gastosProducts||[];
  return '<section class="gastos-panel"><div class="gastos-panel-head"><div><h2>Productos</h2><p>Catálogo estable construido a partir de las compras históricas.</p></div></div><div class="gastos-toolbar"><input id="gastosProductSearch" class="search" placeholder="Buscar producto…" value="'+esc(gastosProductQuery)+'" onkeydown="if(event.key===\'Enter\')searchGastosProducts()"><button class="secondary" onclick="searchGastosProducts()">Buscar</button>'+(gastosProductQuery?'<button class="ghost" onclick="clearGastosProductSearch()">Limpiar</button>':"")+'</div><div class="gastos-products" style="margin-top:13px">'+(list.length?list.map(function(p){var last=p.last_purchase,inv=(state.inventory||[]).find(function(i){return Number(i.gastos_product_id)===Number(p.id)});return'<article class="gastos-product"><div onclick="openGastosProduct('+p.id+')" style="cursor:pointer"><strong>'+esc(p.name)+'</strong><div class="gastos-product-meta">'+Number(p.purchase_count||0)+' compras'+(inv?' · 🧴 '+esc(inv.name):'')+'</div>'+(last?'<div class="gastos-product-last">Última: '+esc(gastosDate(last.date))+' · '+esc(last.supermarket)+' · '+esc(gastosMoney(last.line_total))+'</div>':"")+'</div><div class="gastos-ticket-actions">'+(inv?'<button class="ghost" onclick="event.stopPropagation();taskSection=\'inventory\';go(\'tasks\')">Ver en inventario</button>':'<button class="secondary" onclick="event.stopPropagation();addGastosProductToInventory('+p.id+')">+ Inventario</button>')+'</div></article>'}).join(""):'<div class="gastos-empty">No hay productos que coincidan.</div>')+"</div></section>";
}
async function addGastosProductToInventory(productId){
  var product=(gastosProducts||[]).find(function(p){return Number(p.id)===Number(productId)});var name=product?product.name:"Producto";
  try{
    var result=await api("/api/inventory",{method:"POST",body:JSON.stringify({name:name,category:"Alimentación",area_id:null,unit:"",purchase_quantity:"",stock_status:"ok",shopping_requested:false,notes:"Importado desde Gastos",gastos_product_id:Number(productId)})});
    state=await api("/api/state");
    renderGastosContent();
    showUndo("Producto añadido al Inventario",null);
  }catch(e){alert(e.message)}
}
async function searchGastosProducts(){var input=document.getElementById("gastosProductSearch");gastosProductQuery=input?input.value.trim():"";try{await loadGastosProducts();renderGastosContent()}catch(e){alert(e.message)}}
async function clearGastosProductSearch(){gastosProductQuery="";var input=document.getElementById("gastosProductSearch");if(input)input.value="";try{await loadGastosProducts();renderGastosContent()}catch(e){alert(e.message)}}
async function openGastosProduct(id){
  try{
    var s=await api("/api/gastos/products/"+id+"/stats"),last=s.last_purchase,rec=s.recommended_supermarket,habit=s.habitual_supermarket,shops=s.supermarket_stats||[];
    var trend=s.price_change_percent==null?"—":((s.price_change_percent>0?"+":"")+gastosNumber(s.price_change_percent,1)+"%");
    var html='<div class="modalhead"><div><h2>'+esc(s.name)+'</h2><div class="muted">Histórico de precio y supermercados.</div></div><button class="ghost" onclick="closeModal()">×</button></div>'+
      '<div class="gastos-product-stats">'+
        '<div class="gastos-product-stat"><span>Compras</span><strong>'+Number(s.purchase_count||0)+'</strong></div>'+
        '<div class="gastos-product-stat"><span>Precio unitario medio</span><strong>'+(s.average_unit_price==null?"—":esc(gastosMoney(s.average_unit_price)))+'</strong></div>'+
        '<div class="gastos-product-stat"><span>Mejor precio histórico</span><strong>'+(s.lowest_unit_price==null?"—":esc(gastosMoney(s.lowest_unit_price)))+'</strong></div>'+
        '<div class="gastos-product-stat"><span>Último cambio</span><strong>'+esc(trend)+'</strong></div>'+
      '</div>'+
      '<div class="gastos-grid" style="margin-top:13px">'+
        '<section class="gastos-panel"><strong>💡 Supermercado recomendado</strong><div class="muted" style="margin-top:5px">'+(rec?esc(rec.supermarket)+' · media '+esc(gastosMoney(rec.average_unit_price))+' / unidad':'Sin datos suficientes')+'</div></section>'+
        '<section class="gastos-panel"><strong>🛒 Supermercado habitual</strong><div class="muted" style="margin-top:5px">'+(habit?esc(habit.supermarket)+' · '+Number(habit.purchase_count||0)+' compras':'Sin datos suficientes')+'</div></section>'+
      '</div>'+
      (last?'<section class="gastos-panel" style="margin-top:13px"><strong>Última compra</strong><div class="muted" style="margin-top:5px">'+esc(gastosDate(last.date))+' · '+esc(last.supermarket)+' · '+gastosNumber(last.quantity,3)+' uds · '+esc(gastosMoney(last.line_total))+(last.unit_price==null?"":' · '+esc(gastosMoney(last.unit_price))+' / unidad')+'</div></section>':"")+
      (shops.length?'<section class="gastos-panel" style="margin-top:13px"><div class="gastos-panel-head"><div><h3>Comparativa por supermercado</h3><p>Media histórica por unidad y última compra registrada.</p></div></div><div class="gastos-table-wrap"><table class="gastos-table"><thead><tr><th>Supermercado</th><th>Compras</th><th>Media/u.</th><th>Último/u.</th><th>Última fecha</th></tr></thead><tbody>'+shops.map(function(x){return'<tr><td>'+esc(x.supermarket)+'</td><td>'+Number(x.purchase_count||0)+'</td><td>'+(x.average_unit_price==null?"—":esc(gastosMoney(x.average_unit_price)))+'</td><td>'+(x.last_unit_price==null?"—":esc(gastosMoney(x.last_unit_price)))+'</td><td>'+esc(x.last_date?gastosDate(x.last_date):"—")+'</td></tr>'}).join("")+'</tbody></table></div></section>':"")+
      '<div class="modalfoot"><button class="primary" onclick="closeModal()">Cerrar</button></div>';
    showModal(html)
  }catch(e){alert(e.message)}
}
function renderGastosLookups(){
  var l=gastosDashboard.lookups||{};
  function card(category,title,values){return'<div class="gastos-lookup"><div><strong>'+esc(title)+'</strong><div class="muted">Oculta errores de los desplegables sin borrar el histórico.</div></div><select id="lookup-'+category+'"><option value="">Selecciona…</option>'+(values||[]).map(function(v){return'<option value="'+esc(v)+'">'+esc(v)+'</option>'}).join("")+'</select><button class="danger" onclick="deleteGastosLookup(\''+category+'\')">Quitar de listas</button></div>'}
  return '<section class="gastos-panel"><div class="gastos-panel-head"><div><h2>Limpiar desplegables</h2><p>Equivale a la función de limpieza de la aplicación Gastos original.</p></div></div><div class="gastos-lookup-grid">'+card("article","Artículos",l.articles)+card("user","Usuarios",l.users)+card("supermarket","Supermercados",l.supermarkets)+"</div></section>";
}
async function deleteGastosLookup(category){var el=document.getElementById("lookup-"+category),value=el?el.value:"";if(!value)return;if(!confirm('¿Ocultar "'+value+'" de los desplegables? El histórico no se borrará.'))return;try{await api("/api/gastos/lookups/"+category+"?value="+encodeURIComponent(value),{method:"DELETE"});gastosDashboard=null;await loadGastosDashboard();renderGastosContent();showUndo("Opción ocultada de las listas",null)}catch(e){alert(e.message)}}

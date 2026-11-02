'use strict';
// Mapa de centrales y red de transporte (MapLibre + OpenFreeMap; datos de /api/red). Todo el texto se inserta con textContent.
(function(){
const $=id=>document.getElementById(id);
const el=(t,c,x,k)=>{const e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;(k||[]).forEach(n=>n&&e.appendChild(n));return e};
const G={nuclear:['Nuclear','#7c3aed'],hidraulica:['Hidráulica','#1b6fe0'],termica:['Térmica','#4b5563'],eolica:['Eólica','#0fb5a5'],solar:['Solar','#f59e0b'],otras:['Otras','#84cc16']};
const COORD={'La Palma':[-17.85,28.68],'La Gomera':[-17.2,28.1],'El Hierro':[-18,27.75],'Tenerife':[-16.6,28.29],'Gran Canaria':[-15.6,27.96],'Lanzarote':[-13.6,29.04],
 'Fuerteventura':[-14,28.35],'Canarias':[-15.9,28.3],'Mallorca':[2.98,39.62],'Ibiza':[1.43,38.97],'Menorca':[4.1,39.95],'Baleares':[2.9,39.55],'Ceuta':[-5.32,35.89],
 'Melilla':[-2.94,35.29],'Madrid':[-3.7,40.42],'Barcelona':[2.17,41.39],'Valencia':[-0.38,39.47],'Andalucía':[-5.99,37.39],'Galicia':[-8.54,42.88],'Península':[-3.7,40]};
const VIEW={pen:{c:[-3.7,39.9],z:5.2,t:'Península'},can:{c:[-15.9,28.3],z:6.6,t:'Canarias'},bal:{c:[2.9,39.6],z:7.2,t:'Baleares'}};
let M=null,READY=false,DATA=null,ALERTS=[],MARKERS=[],ON={nuclear:1,hidraulica:1,termica:1,eolica:1,solar:1,otras:1,l400:1,l220:1,subs:1,alerts:1},POP=null;
const mw=v=>v==null?'—':v>=1000?(v/1000).toLocaleString('es-ES',{maximumFractionDigits:1})+' GW':Math.round(v).toLocaleString('es-ES')+' MW';

function build(){
  const sec=$('mapa');if(!sec||sec.dataset.b)return;sec.dataset.b='1';
  const chips=el('div','mchips'),views=el('div','mviews');
  Object.keys(G).forEach(k=>{const b=el('button','chip on',null,[el('i'),el('span',null,G[k][0]),el('em',null,'')]);b.firstChild.style.background=G[k][1];b.dataset.k=k;b.type='button';
    b.onclick=()=>{ON[k]=ON[k]?0:1;b.classList.toggle('on',!!ON[k]);apply()};chips.appendChild(b)});
  [['l400','Líneas 400 kV','#d6182a'],['l220','Líneas 220 kV','#f08a24'],['subs','Subestaciones','#111827'],['alerts','Alertas de apagón','#d6182a']].forEach(([k,t,c])=>{
    const b=el('button','chip on',null,[el('i'),el('span',null,t)]);b.firstChild.style.background=c;b.dataset.k=k;b.type='button';
    b.onclick=()=>{ON[k]=ON[k]?0:1;b.classList.toggle('on',!!ON[k]);apply()};chips.appendChild(b)});
  Object.keys(VIEW).forEach(k=>{const b=el('button','vw',VIEW[k].t);b.type='button';b.onclick=()=>M&&M.flyTo({center:VIEW[k].c,zoom:VIEW[k].z,speed:1.4});views.appendChild(b)});
  sec.append(el('h2',null,'Mapa de centrales y red eléctrica'),views,el('div','mwrap',null,[el('div','mbox'),el('div','mmsg')]),chips,el('div','note mnote'),el('div','note mattr'));
  $('mapa').querySelector('.mattr').textContent='Mapa © OpenFreeMap · © OpenMapTiles · Datos © colaboradores de OpenStreetMap (ODbL). Informativo: no es el inventario oficial de Red Eléctrica.';
  if(typeof maplibregl==='undefined'){msg('Mapa no disponible (no se pudo cargar la librería).');return}
  try{
    M=new maplibregl.Map({container:sec.querySelector('.mbox'),style:'https://tiles.openfreemap.org/styles/positron',center:VIEW.pen.c,zoom:VIEW.pen.z,minZoom:3.5,maxZoom:14,attributionControl:false,renderWorldCopies:false});
    M.addControl(new maplibregl.NavigationControl({showCompass:false}),'top-right');
    M.on('load',()=>{READY=true;initLayers();apply();msg('')});
    M.on('error',e=>{if(!READY&&e&&e.error&&/style|fetch|Failed|NetworkError|40[34]/i.test(String(e.error.message||e.error)))msg('Mapa base no disponible ahora mismo.')});
  }catch(e){msg('Mapa no disponible.')}
}
function msg(t){const m=document.querySelector('#mapa .mmsg');if(m){m.textContent=t||'';m.style.display=t?'block':'none'}}

function plantsGeo(){const f=[];(DATA&&DATA.plants||[]).forEach((p,i)=>{
  const r=Math.max(4,Math.min(17,3.4+Math.sqrt(p.mw||25)*.3))+(p.g==='nuclear'?3:0);
  f.push({type:'Feature',id:i,geometry:{type:'Point',coordinates:[p.c[1],p.c[0]]},properties:{i,g:p.g,r,off:p.off?1:0,n:(p.n||'').replace(/^Central nuclear (de |d')?/i,'')}})});
  return {type:'FeatureCollection',features:f}}
function linesGeo(kv){return {type:'FeatureCollection',features:(DATA&&DATA.lines||[]).filter(l=>kv===400?l.kv>=380:l.kv<380).map(l=>({type:'Feature',geometry:{type:'LineString',coordinates:l.p.map(q=>[q[1],q[0]])},properties:{kv:l.kv}}))}}
function subsGeo(){return {type:'FeatureCollection',features:(DATA&&DATA.subs||[]).map((s,i)=>({type:'Feature',geometry:{type:'Point',coordinates:[s.c[1],s.c[0]]},properties:{i,kv:s.kv,n:s.n}}))}}

function initLayers(){
  const empty={type:'FeatureCollection',features:[]};
  M.addSource('l220',{type:'geojson',data:empty});M.addSource('l400',{type:'geojson',data:empty});M.addSource('subs',{type:'geojson',data:empty});M.addSource('plants',{type:'geojson',data:empty});
  const w=(a,b)=>['interpolate',['linear'],['zoom'],4,a,10,b];
  M.addLayer({id:'l220',type:'line',source:'l220',layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':'#f08a24','line-width':w(.7,2),'line-opacity':.85}});
  M.addLayer({id:'l400',type:'line',source:'l400',layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':'#d6182a','line-width':w(1.1,3),'line-opacity':.9}});
  M.addLayer({id:'subs',type:'circle',source:'subs',minzoom:5.5,paint:{'circle-radius':w(2,5),'circle-color':'#111827','circle-stroke-color':'#fff','circle-stroke-width':1}});
  const col=['match',['get','g'],'nuclear',G.nuclear[1],'hidraulica',G.hidraulica[1],'termica',G.termica[1],'eolica',G.eolica[1],'solar',G.solar[1],G.otras[1]];
  M.addLayer({id:'plants',type:'circle',source:'plants',paint:{'circle-radius':['get','r'],'circle-color':col,'circle-opacity':['case',['==',['get','off'],1],.35,.88],
    'circle-stroke-color':['case',['==',['get','g'],'nuclear'],'#facc15','#fff'],'circle-stroke-width':['case',['==',['get','g'],'nuclear'],3,1.2]}});
  M.addLayer({id:'plants-lbl',type:'symbol',source:'plants',filter:['==',['get','g'],'nuclear'],layout:{'text-field':['get','n'],'text-font':['Noto Sans Bold'],'text-size':12,'text-offset':[0,1.6],'text-anchor':'top','text-optional':true},
    paint:{'text-color':'#4c1d95','text-halo-color':'#fff','text-halo-width':1.6}});
  M.on('click','plants',e=>{const f=e.features&&e.features[0];if(f)popPlant(DATA.plants[f.properties.i],e.lngLat)});
  M.on('click','subs',e=>{const f=e.features&&e.features[0];if(!f)return;const s=DATA.subs[f.properties.i];pop(e.lngLat,[el('b',null,s.n||'Subestación'),el('div',null,'Subestación de '+s.kv+' kV')])});
  ['l400','l220'].forEach(id=>M.on('click',id,e=>{if(M.queryRenderedFeatures(e.point,{layers:['plants','subs']}).length)return;const f=e.features[0];pop(e.lngLat,[el('b',null,'Línea de '+f.properties.kv+' kV'),el('div','note','Red de transporte (OpenStreetMap)')])}));
  ['plants','subs','l400','l220'].forEach(id=>{M.on('mouseenter',id,()=>M.getCanvas().style.cursor='pointer');M.on('mouseleave',id,()=>M.getCanvas().style.cursor='')});
  setData();
}
function pop(ll,kids){if(POP)POP.remove();POP=new maplibregl.Popup({maxWidth:'280px',closeButton:true}).setLngLat(ll).setDOMContent(el('div','mp',null,kids)).addTo(M)}
function popPlant(p,ll){if(!p)return;const k=[el('b',null,p.n||'Central sin nombre'),el('div',null,(G[p.g]||G.otras)[0]+(p.s&&p.s!==p.g&&p.s!=='nuclear'?' · '+p.s:'')+(p.off?' · fuera de servicio':'')),
  el('div',null,'Potencia: '+(p.mw?mw(p.mw):'no indicada en OpenStreetMap'))];
  if(p.op)k.push(el('div',null,'Titular: '+p.op));if(p.y)k.push(el('div',null,'Desde: '+p.y));if(p.nota)k.push(el('div','note',p.nota));pop(ll,k)}

function setData(){if(!READY||!DATA)return;
  M.getSource('plants').setData(plantsGeo());M.getSource('l400').setData(linesGeo(400));M.getSource('l220').setData(linesGeo(220));M.getSource('subs').setData(subsGeo());
  const cnt={},sum={};(DATA.plants||[]).forEach(p=>{cnt[p.g]=(cnt[p.g]||0)+1;if(p.mw&&!p.off)sum[p.g]=(sum[p.g]||0)+p.mw});
  document.querySelectorAll('#mapa .chip').forEach(b=>{const k=b.dataset.k;if(G[k]){const e=b.querySelector('em');e.textContent=cnt[k]?cnt[k]+(sum[k]?' · '+mw(sum[k]):''):''}});
  const st=DATA.status||{},n=DATA.counts||{};
  let t='';
  const sumy=n.plants+' centrales · '+n.lines+' tramos de línea · '+n.subs+' subestaciones. Eólica y solar: solo instalaciones de 20 MW o más con potencia indicada; la potencia suma lo que figura en OpenStreetMap, no es la instalada oficial.';
  if(!(n.lines>0))t=st.state==='error'?'Líneas y resto de centrales no disponibles: '+(st.error||'OpenStreetMap no responde')+'. Se muestran solo las nucleares.':
    'Cargando líneas y centrales de OpenStreetMap'+(st.tiles_total?' ('+st.tiles_done+'/'+st.tiles_total+' zonas)':'')+'… Mientras tanto se ven las nucleares.';
  else t=sumy+(st.state==='descargando'?' Actualizando desde OpenStreetMap ('+st.tiles_done+'/'+st.tiles_total+')…':'');
  const m=document.querySelector('#mapa .mnote');if(m)m.textContent=t;apply()}

function apply(){if(!READY)return;
  const gs=Object.keys(G).filter(k=>ON[k]);M.setFilter('plants',['in',['get','g'],['literal',gs]]);
    const vis=(id,on)=>M.getLayer(id)&&M.setLayoutProperty(id,'visibility',on?'visible':'none');vis('plants-lbl',ON.nuclear);vis('l400',ON.l400);vis('l220',ON.l220);vis('subs',ON.subs);
  MARKERS.forEach(m=>m.getElement().style.display=ON.alerts?'':'none')}

function alertMarkers(list){
  MARKERS.forEach(m=>m.remove());MARKERS=[];if(!M||!READY)return;
  (list||[]).filter(a=>a.type==='energia'&&COORD[a.place]).forEach(a=>{
    const d=el('div','amk',null,[el('span','pu'),el('span','dot','⚡')]);d.title=a.title;
    const mk=new maplibregl.Marker({element:d}).setLngLat(COORD[a.place]).addTo(M);
    d.onclick=ev=>{ev.stopPropagation();pop(COORD[a.place],[el('b',null,a.title),el('div',null,a.detail||''),el('div','note','Detectada en prensa; sin confirmar por el operador eléctrico.')])};
    MARKERS.push(mk)});
  apply()}
window.mapaAlerts=l=>{ALERTS=l;if(READY)alertMarkers(l)};

let tm=null;
async function poll(){try{const r=await fetch('/api/red',{cache:'no-store'});if(!r.ok)throw 0;DATA=await r.json();setData()}catch(e){}
  const st=DATA&&DATA.status||{},hasL=DATA&&DATA.counts&&DATA.counts.lines>0,wait=st.state==='error'?1800000:!hasL?15000:st.state==='descargando'?90000:1800000;clearTimeout(tm);tm=setTimeout(poll,wait)}
function start(){build();poll();const t=setInterval(()=>{if(READY){clearInterval(t);alertMarkers(window.__alerts||ALERTS)}},500)}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
})();

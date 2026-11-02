'use strict';
/* Extras de Red-Sentinel: avisos meteorológicos, suscripción, consejos por horas, historial y metodología, instalación como app. */
const TZ={timeZone:'Europe/Madrid'};
const hhmm=ms=>new Date(ms).toLocaleTimeString('es-ES',{...TZ,hour:'2-digit',minute:'2-digit'});
const ddmm=ms=>new Date(ms).toLocaleDateString('es-ES',{...TZ,day:'2-digit',month:'2-digit'});
const LVL={rojo:['Rojo','#d6182a'],naranja:['Naranja','#e8651c'],amarillo:['Amarillo','#e0a100']};

function renderMeteo(m){const b=$('meteo');if(!m||!m.counts){b.replaceChildren(h('div','note','Sin avisos todavía.'));return}
  const c=m.counts,tiles=h('div','stats',null,['rojo','naranja','amarillo'].map(k=>{const t=tile('Avisos '+k+'s',String(c[k]||0),k==='amarillo'?'':'activos o en las próximas 24 h');t.firstChild.nextSibling.style.color=(c[k]?LVL[k][1]:'');return t}));
  const rows=(m.top||[]).map(i=>h('div','mrow',null,[h('span','mlv',LVL[i.level][0]),h('b',null,i.type),h('span',null,i.area),
    h('small',null,(i.active?'activo hasta ':'desde ')+(i.active?ddmm(i.expires*1000)+' '+hhmm(i.expires*1000):ddmm(i.onset*1000)+' '+hhmm(i.onset*1000)))]));rows.forEach((r,k)=>{r.firstChild.style.background=LVL[m.top[k].level][1]});
  const y=Object.entries(m.yellow_by_type||{}).sort((a,b)=>b[1]-a[1]).map(([t,n])=>h('span','rc',t+' · '+n));
  b.replaceChildren(tiles,...(rows.length?[h('div','mlist',null,rows)]:[h('div','empty','✓ Sin avisos naranja ni rojo en las próximas 24 h.')]),
    y.length?h('div','note','Avisos amarillos: '):null,y.length?h('div','rchips',null,y):null,
    h('div','note','Contexto de riesgo, no una alerta de apagón: viento, tormentas, nieve, calor o incendios son lo que más líneas tumba. Fuente: AEMET vía MeteoAlarm.org (CC BY 4.0). El aviso oficial es el de AEMET.'));}
async function loadMeteo(){try{renderMeteo(await j('/api/meteo'))}catch(e){}}

let DEFERRED=null;window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();DEFERRED=e;const x=document.getElementById('instbtn');if(x)x.style.display=''});
function renderSubs(cfg){const b=$('subs');if(!cfg){return}
  const btn=(txt,href,cls)=>{const a=h('a','btn'+(cls?' '+cls:''),txt);a.href=href;a.target='_blank';a.rel='noopener noreferrer';return a};
  const cards=[];
  if(cfg.telegram)cards.push(h('div','sc',null,[h('b',null,'Telegram'),h('small',null,'Canal oficial de Red-Sentinel: solo publica el servidor. La opción más fiable.'),btn('Unirme al canal',cfg.telegram,'pri')]));
  cards.push(h('div','sc',null,[h('b',null,'Móvil o navegador (ntfy)'),h('small',null,'Gratis y sin registro. Abre el canal en la app ntfy (iOS/Android) o actívalo en el navegador. Es un canal público.'),btn('Abrir canal ntfy',cfg.ntfy.url,cfg.telegram?'':'pri')]));
  cards.push(h('div','sc',null,[h('b',null,'Lector RSS / Atom'),h('small',null,'Para lectores de noticias, Slack, Zapier o tu propia automatización.'),btn('Feed de alertas',cfg.atom)]));
  const inst=h('button','btn','Instalar como app');inst.id='instbtn';inst.type='button';inst.style.display=DEFERRED?'':'none';inst.onclick=async()=>{if(DEFERRED){DEFERRED.prompt();DEFERRED=null;inst.style.display='none'}};
  cards.push(h('div','sc',null,[h('b',null,'App en tu pantalla de inicio'),h('small',null,'Instálala como app (PWA). En iPhone: Compartir → «Añadir a pantalla de inicio».'),inst]));
  b.replaceChildren(h('div','scs',null,cards),h('div','note','Recibirás un aviso cuando salte una regla de caída (ámbar o roja). Informativo, no oficial; no sustituye los avisos de Red Eléctrica ni de Protección Civil.'))}
async function loadCfg(){try{renderSubs(await j('/api/config'))}catch(e){}}

/* Consejos por horas: coste de usar un electrodoméstico en la mejor y la peor franja del día (PVPC, solo término de energía) */
const APPS=[['Lavadora',1.0,2],['Lavavajillas',1.2,2],['Secadora',2.5,1],['Horno',2.0,1],['Cargar coche eléctrico',30,6]];
const eur=v=>Math.max(0,v).toLocaleString('es-ES',{minimumFractionDigits:2,maximumFractionDigits:2})+' €';
function renderTips(){const b=document.getElementById('tips');if(!b)return;const p=window.PDATA||(typeof PDATA!=='undefined'?PDATA:null);
  if(!p||!p.days){b.replaceChildren(h('div','note','Sin precios todavía.'));return}
  const days=p.days.filter(d=>d.pvpc&&d.pvpc.length),d=days[Math.min(typeof PSEL!=='undefined'?PSEL:0,days.length-1)];
  if(!d){b.replaceChildren(h('div','note','Sin precios por horas todavía.'));return}
  const pv=d.pvpc.map(x=>x[1]),today=days[0]===d,from=today?Math.min(new Date().getHours(),pv.length-1):0,rows=[];
  APPS.forEach(([n,kwh,dur])=>{let best=null,worst=null;for(let s=from;s+dur<=pv.length;s++){const sum=pv.slice(s,s+dur).reduce((a,x)=>a+x,0)/dur*kwh/1000;if(!best||sum<best.c)best={s,c:sum};if(!worst||sum>worst.c)worst={s,c:sum}}
    if(!best)return;const hr=s=>String(s).padStart(2,'0')+':00',rg=x=>hr(x.s)+'–'+hr(Math.min(24,x.s+dur));
    rows.push(h('div','trow',null,[h('b',null,n),h('small',null,kwh.toLocaleString('es-ES')+' kWh · '+dur+' h'),h('span','tg',null,[tx('Mejor: '),h('b',null,rg(best)),tx(' · '+eur(best.c))]),h('span','tb',null,[tx('Peor: '+rg(worst)+' · '+eur(worst.c))]),h('span','ts','Ahorras '+eur(worst.c-best.c))]))});
  const ranked=pv.map((v,i)=>[i,v]).slice(from).sort((a,b)=>a[1]-b[1]),cheap=ranked[0],dear=ranked[ranked.length-1];
  b.replaceChildren(h('div','stats',null,cheap?[tile('Hora más barata',String(cheap[0]).padStart(2,'0')+':00',cheap[1].toLocaleString('es-ES')+' €/MWh'),tile('Hora más cara',String(dear[0]).padStart(2,'0')+':00',dear[1].toLocaleString('es-ES')+' €/MWh')]:[]),
    h('div','tlist',null,rows),h('div','note','Estimación con el PVPC (tarifa regulada) por horas'+(today?', desde ahora':'')+': solo el término de energía, sin peajes, cargos ni impuestos. El consumo de cada aparato es orientativo. Fuente: REData.'));}
{const _dp=window.drawPrice;window.drawPrice=function(){_dp();renderTips()}}

/* Historial de alertas y metodología */
function renderHistAl(hs){const b=$('histal');if(!hs||!hs.realtime){b.replaceChildren(h('div','note','Sin historial todavía.'));return}
  const ep=hs.realtime.episodes,hits=hs.daily.hits,real=hits.filter(x=>!x.holiday),byRule={};ep.forEach(e=>byRule[e.rule]=(byRule[e.rule]||0)+1);
  const tiles=h('div','stats',null,[tile('Lecturas analizadas hoy',fmt(hs.realtime.readings),hs.realtime.since?'desde las '+hs.realtime.since:''),tile('Episodios hoy',String(ep.length),ep.length?Object.entries(byRule).map(([k,n])=>k+' ×'+n).join(' · '):'ninguna regla saltó'),
    tile('Días con caída diaria',String(real.length),'en '+hs.daily.days+' días, sin contar festivos'),tile('Reglas vigiladas',String(hs.rules.length),'ninguna confirma un apagón por sí sola')]);
  const L=(t)=>h('div','hcol',null,t);
  const epRows=ep.length?ep.map(e=>h('div','hrow'+(e.sev==='muy alta'?' red':''),null,[h('b',null,e.start.slice(11,16)+(e.end!==e.start?'–'+e.end.slice(11,16):'')),h('span','rc'+(e.sev==='muy alta'?' red':''),e.rule),h('span',null,e.title)])):[h('div','empty','✓ Sin episodios hoy.')];
  const dRows=hits.length?hits.slice(0,14).map(x=>h('div','hrow'+(x.sev==='muy alta'?' red':''),null,[h('b',null,dm(x.date)),h('span','rc',x.zone),h('span',null,x.dev.toString().replace('.',',')+' % frente a su día de la semana'+(x.holiday?' · festivo (esperable)':''))])):[h('div','empty','✓ Ningún día con caída diaria relevante.')];
  const meth=h('details',null,null,[h('summary',null,'Metodología: cómo se calculan las reglas'),
    h('div','mth',null,[h('table',null,null,[h('thead',null,null,[h('tr',null,null,['Regla','Qué mide','Ámbar','Roja'].map(t=>h('th',null,t)))]),h('tbody',null,null,hs.rules.map(r=>h('tr',null,null,[h('td',null,r.id),h('td',null,r.name+' · '+r.scope),h('td',null,r.amber),h('td',null,r.red)])))]),
      h('ul',null,null,['Los datos son los públicos de Red Eléctrica (REData): demanda cada 5 min, su previsión, demanda diaria por sistema y generación diaria por tecnología.',
        'Las lecturas de los últimos 25 min son provisionales (Red Eléctrica las corrige al alza a los pocos minutos), por eso las reglas y el índice usan solo lecturas consolidadas y avisan con ese retraso.',
        'La variación se normaliza «a 15 min» y las caídas a plena mañana (rampas de +3 % cada 15 min) no cuentan. La oscilación es la media del valor absoluto de la segunda diferencia en la última hora frente a la mediana habitual del día.',
        'Las reglas diarias comparan con la mediana de los 3 mismos días de la semana previos y con la media de los días recientes (deben caer frente a ambas, para no confundir una bajada estacional) y no saltan en festivos nacionales. Con datos diarios no se puede situar la hora ni la causa.',
        'Calibradas con lecturas reales: caídas de hasta −2 % cada 15 min son normales; con las lecturas horarias del 28-A el índice no habría avisado antes del colapso (detecta, no anticipa).',
        'No existen datos públicos en tiempo real por central, subestación o línea, ni de frecuencia, tensión o inercia. Una regla que salta es una señal para mirar, no la confirmación de un apagón.']
        .map(t=>h('li',null,t)))])]);
  b.replaceChildren(tiles,h('div','hcols',null,[L([h('h3',null,'Hoy · tiempo real (península)'),...epRows]),L([h('h3',null,'Últimos días · demanda diaria por sistema'),...dRows])]),meth,h('div','note',hs.note))}
async function loadHist(){try{renderHistAl(await j('/api/historial'))}catch(e){}}

loadMeteo();setInterval(loadMeteo,600000);loadCfg();loadHist();setInterval(loadHist,300000);
window.addEventListener('load',()=>{try{renderTips()}catch(e){}});
if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});

// Modo día / noche (la preferencia se guarda en este navegador; por defecto, noche)
(function () {
  const b = document.getElementById('thm'), root = document.documentElement;
  if (!b) return;
  const paint = () => {
    const dark = root.dataset.theme === 'dark';
    b.textContent = dark ? '☀️ Modo día' : '🌙 Modo noche';
    b.setAttribute('aria-pressed', String(dark));
    const m = document.querySelector('meta[name=theme-color]');
    if (m) m.content = dark ? '#05060a' : '#c4121f';
  };
  b.onclick = () => {
    const n = root.dataset.theme === 'dark' ? 'light' : 'dark';
    root.dataset.theme = n;
    try { localStorage.setItem('rs-theme', n); } catch (e) {}
    paint();
    if (window.mapaTheme) window.mapaTheme();
  };
  paint();
})();

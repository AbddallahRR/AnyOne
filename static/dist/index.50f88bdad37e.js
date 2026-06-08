(function(){if(window.location.pathname.startsWith('/reader/'))return;if(!document.getElementById('qi-styles')){const style=document.createElement('style');style.id='qi-styles';style.textContent=`
      #qi-indicator {
        position: fixed;
        top: var(--qi-top, 14px);
        right: 14px;
        background: rgba(10,10,15,0.88);
        border: 1px solid rgba(255,255,255,0.12);
        color: var(--text, #e8e8f0);
        border-radius: 10px;
        padding: 6px 12px;
        font-size: 12px;
        font-family: var(--ff-body, sans-serif);
        z-index: 10000;
        cursor: pointer;
        backdrop-filter: blur(12px);
        box-shadow: 0 4px 20px rgba(0,0,0,0.4);
        display: none;
        align-items: center;
        gap: 8px;
        max-width: 220px;
        opacity: 0;
        transform: translateY(-8px);
        transition: opacity 0.22s ease, transform 0.22s ease;
      }
      #qi-indicator.visible {
        display: flex;
        opacity: 1;
        transform: translateY(0);
      }
      #qi-indicator i {
        color: var(--accent, #c46bff);
        font-size: 13px;
        flex-shrink: 0;
      }
      #qi-label {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        flex: 1;
        min-width: 0;
      }
      #qi-count {
        background: rgba(196,107,255,0.2);
        color: var(--accent, #c46bff);
        border-radius: 5px;
        padding: 1px 6px;
        font-size: 11px;
        font-weight: 600;
        flex-shrink: 0;
      }

      /* ── Popup ── */
      #qi-popup {
        position: fixed;
        top: var(--qi-popup-top, 58px);
        right: 14px;
        background: rgba(10,10,15,0.95);
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 14px;
        padding: 14px;
        min-width: 280px;
        max-width: 360px;
        max-height: 420px;
        overflow-y: auto;
        z-index: 9999;
        backdrop-filter: blur(16px);
        box-shadow: 0 8px 32px rgba(0,0,0,0.5);
        font-size: 12px;
        font-family: var(--ff-body, sans-serif);
        color: var(--text, #e8e8f0);
        display: none;
        flex-direction: column;
        gap: 10px;
        opacity: 0;
        transform: translateY(-8px) scale(0.97);
        transition: opacity 0.2s ease, transform 0.2s ease;
      }
      #qi-popup.open {
        opacity: 1;
        transform: translateY(0) scale(1);
      }
      .qi-section-title {
        font-size: 11px;
        font-weight: 600;
        color: var(--muted, #7a7a8a);
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-bottom: 6px;
      }
      .qi-job {
        background: var(--raised, #18181f);
        border: 1px solid rgba(255,255,255,0.07);
        border-radius: 9px;
        padding: 8px 10px;
        display: flex;
        flex-direction: column;
        gap: 5px;
      }
      .qi-job-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
      }
      .qi-job-title {
        font-weight: 500;
        font-size: 12px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        flex: 1;
        min-width: 0;
      }
      .qi-job-status {
        font-size: 10px;
        padding: 2px 7px;
        border-radius: 5px;
        flex-shrink: 0;
        font-weight: 500;
      }
      .qi-status-downloading {
        background: rgba(196,107,255,0.15);
        color: var(--accent, #c46bff);
      }
      .qi-status-pending {
        background: rgba(255,255,255,0.07);
        color: var(--muted, #7a7a8a);
      }
      .qi-status-failed {
        background: rgba(248,113,113,0.15);
        color: #f87171;
      }
      .qi-progress-bar {
        height: 2px;
        background: rgba(255,255,255,0.07);
        border-radius: 2px;
        overflow: hidden;
      }
      .qi-progress-fill {
        height: 100%;
        background: linear-gradient(90deg, var(--accent, #c46bff), #ff6b9d);
        border-radius: 2px;
        transition: width 0.4s ease;
      }
      .qi-progress-text {
        font-size: 10px;
        color: var(--muted, #7a7a8a);
        display: flex;
        justify-content: space-between;
      }
      .qi-error-text {
        font-size: 11px;
        color: #f87171;
        background: rgba(248,113,113,0.08);
        border: 1px solid rgba(248,113,113,0.2);
        border-radius: 6px;
        padding: 5px 8px;
        line-height: 1.4;
        word-break: break-word;
      }
      .qi-empty {
        text-align: center;
        color: var(--muted, #7a7a8a);
        padding: 16px;
        font-size: 12px;
      }
      .qi-popup-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding-bottom: 8px;
        border-bottom: 1px solid rgba(255,255,255,0.07);
        margin-bottom: 2px;
      }
      .qi-popup-title {
        font-family: var(--ff-head, sans-serif);
        font-size: 13px;
        font-weight: 700;
        color: var(--text, #e8e8f0);
      }
      .qi-close {
        width: 24px; height: 24px;
        border-radius: 6px;
        border: 1px solid rgba(255,255,255,0.08);
        background: transparent;
        color: var(--muted, #7a7a8a);
        font-size: 14px;
        cursor: pointer;
        display: flex; align-items: center; justify-content: center;
        transition: background 0.15s, color 0.15s, transform 0.15s;
      }
      .qi-close:hover { background: rgba(255,255,255,0.07); color: var(--text); transform: rotate(90deg); }

      @media (max-width: 640px) {
        #qi-indicator { right: 10px; }
        #qi-popup { right: 10px; left: 10px; max-width: none; }
      }
    `;document.head.appendChild(style);}
function positionUnderNav(){const nav=document.querySelector('.app-nav')||document.querySelector('nav');if(!nav)return;const navBottom=nav.getBoundingClientRect().bottom;const offset=navBottom+10;document.documentElement.style.setProperty('--qi-top',offset+'px');document.documentElement.style.setProperty('--qi-popup-top',(offset+44)+'px');}
positionUnderNav();if(window.ResizeObserver){const nav=document.querySelector('.app-nav')||document.querySelector('nav');if(nav)new ResizeObserver(positionUnderNav).observe(nav);}
let indicator=document.getElementById('qi-indicator');if(!indicator){indicator=document.createElement('div');indicator.id='qi-indicator';indicator.innerHTML=`
      <i class="fas fa-arrow-down"></i>
      <span id="qi-label">Descargando…</span>
      <span id="qi-count" style="display:none;"></span>`;document.body.appendChild(indicator);}
let popup=document.getElementById('qi-popup');if(!popup){popup=document.createElement('div');popup.id='qi-popup';popup.innerHTML=`
      <div class="qi-popup-header">
        <span class="qi-popup-title">Cola de descarga</span>
        <button class="qi-close" id="qi-close-btn">×</button>
      </div>
      <div id="qi-list"></div>`;document.body.appendChild(popup);}
let pollingTimer=null;let forceUntil=0;let popupOpen=false;function showIndicator(){indicator.style.display='flex';requestAnimationFrame(()=>requestAnimationFrame(()=>indicator.classList.add('visible')));}
function hideIndicator(){indicator.classList.remove('visible');setTimeout(()=>{indicator.style.display='none';},250);}
function openPopup(){popupOpen=true;popup.style.display='flex';requestAnimationFrame(()=>requestAnimationFrame(()=>popup.classList.add('open')));}
function closePopup(){popupOpen=false;popup.classList.remove('open');setTimeout(()=>{popup.style.display='none';},220);}
function truncate(str,max=28){return str&&str.length>max?str.slice(0,max-1)+'…':(str||'');}
function buildJobHtml(job){const isDownloading=job.status==='downloading';const isFailed=job.status==='failed';const pct=job.progress||0;const cap=job.current_chapter||0;const total=job.total_chapters||'?';let statusBadge='';if(isDownloading)statusBadge=`<span class="qi-job-status qi-status-downloading">Descargando</span>`;else if(isFailed)statusBadge=`<span class="qi-job-status qi-status-failed">Error</span>`;else statusBadge=`<span class="qi-job-status qi-status-pending">En cola</span>`;let progressHtml='';if(isDownloading){progressHtml=`
        <div class="qi-progress-bar">
          <div class="qi-progress-fill" style="width:${pct}%"></div>
        </div>
        <div class="qi-progress-text">
          <span>Cap. ${cap}/${total}</span>
          <span>${pct}%</span>
        </div>`;}
let errorHtml='';if(isFailed&&job.error){errorHtml=`<div class="qi-error-text"><i class="fas fa-exclamation-triangle" style="margin-right:5px;"></i>${job.error}</div>`;}
return`
      <div class="qi-job">
        <div class="qi-job-header">
          <span class="qi-job-title" title="${(job.title || '').replace(/"/g,'&quot;')}">${job.title || '—'}</span>
          ${statusBadge}
        </div>
        ${progressHtml}
        ${errorHtml}
      </div>`;}
async function fetchQueueStatus(){try{const res=await fetch('/api/queue/status');const data=await res.json();const active=data.active||[];const pending=(data.queue||[]).filter(j=>j.status==='pending');const failed=(data.queue||[]).filter(j=>j.status==='failed');const hasActivity=active.length>0||pending.length>0;const label=document.getElementById('qi-label');const countBadge=document.getElementById('qi-count');if(active.length>0){const best=active.reduce((a,b)=>(a.progress>b.progress?a:b),active[0]);if(label)label.textContent=truncate(best.title);if(countBadge){countBadge.style.display=active.length>1?'inline':'none';countBadge.textContent=`+${active.length - 1}`;}
showIndicator();}else if(pending.length>0){if(label)label.textContent=`En cola: ${pending.length}`;if(countBadge)countBadge.style.display='none';showIndicator();}else if(failed.length>0&&Date.now()<forceUntil){if(label)label.textContent=`${failed.length} error${failed.length > 1 ? 'es' : ''}`;if(countBadge)countBadge.style.display='none';showIndicator();}else if(!hasActivity&&Date.now()>=forceUntil){hideIndicator();}
const listDiv=document.getElementById('qi-list');if(listDiv){let html='';if(active.length){html+=`<div class="qi-section-title">Descargando ahora</div>`;html+=active.map(buildJobHtml).join('');}
if(pending.length){html+=`<div class="qi-section-title" style="margin-top:${active.length ? 10 : 0}px;">En cola</div>`;html+=pending.map(buildJobHtml).join('');}
if(failed.length){html+=`<div class="qi-section-title" style="margin-top:${active.length || pending.length ? 10 : 0}px; color:#f87171;">Errores recientes</div>`;html+=failed.map(buildJobHtml).join('');}
if(!active.length&&!pending.length&&!failed.length){html=`<div class="qi-empty"><i class="fas fa-check-circle" style="margin-right:6px; color:#4ade80;"></i>Sin actividad</div>`;}
listDiv.innerHTML=html;}
if(hasActivity){forceUntil=Date.now()+5000;scheduleNext(2000);}else if(Date.now()<forceUntil){scheduleNext(2000);}else{clearPolling();}}catch(err){console.error('queue-indicator:',err);scheduleNext(5000);}}
function scheduleNext(ms){clearPolling();pollingTimer=setTimeout(fetchQueueStatus,ms);}
function clearPolling(){if(pollingTimer){clearTimeout(pollingTimer);pollingTimer=null;}}
indicator.addEventListener('click',e=>{e.stopPropagation();if(popupOpen)closePopup();else{fetchQueueStatus().then(openPopup);}});document.getElementById('qi-close-btn')?.addEventListener('click',closePopup);document.addEventListener('click',e=>{if(popupOpen&&!indicator.contains(e.target)&&!popup.contains(e.target))
closePopup();});document.addEventListener('keydown',e=>{if(e.key==='Escape'&&popupOpen)closePopup();});window.showDownloadIndicator=function(){forceUntil=Date.now()+10000;showIndicator();clearPolling();fetchQueueStatus();};fetchQueueStatus();})();(function(){'use strict';let currentType='library';let _libraryItems=[];let _libraryStatuses={};let _libraryFilter='all';let _libraryQuery='';let _libraryLoaded=false;const animePanel=document.getElementById('anime-panel');const mangaPanel=document.getElementById('manga-panel');const libraryPanel=document.getElementById('library-panel');const tabAnime=document.getElementById('tab-anime');const tabManga=document.getElementById('tab-manga');const tabLibrary=document.getElementById('tab-library');const animeSearchBtn=document.getElementById('anime-search-btn');const mangaSearchBtn=document.getElementById('manga-search-btn');const animeRefreshBtn=document.getElementById('anime-refresh-btn');const mangaRefreshBtn=document.getElementById('manga-refresh-btn');const animeSearchInput=document.getElementById('anime-search-input');const mangaSearchInput=document.getElementById('manga-search-input');const TAB_MAP=[{btn:tabAnime,panel:animePanel,type:'anime'},{btn:tabManga,panel:mangaPanel,type:'manga'},{btn:tabLibrary,panel:libraryPanel,type:'library'},];function setActiveTab(type){if(currentType===type&&type!=='library')return;currentType=type;TAB_MAP.forEach(({btn,panel,type:t})=>{const active=t===type;btn.classList.toggle('active',active);panel.classList.toggle('hidden',!active);if(active){panel.style.animation='none';requestAnimationFrame(()=>{panel.style.animation='';});}});if(type==='library'&&!_libraryLoaded){_libraryLoaded=true;loadLibrary();}}
TAB_MAP.forEach(({btn,type})=>{btn.addEventListener('click',()=>setActiveTab(type));});const PLACEHOLDER='data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" '
+'width="2" height="3"%3E%3C/svg%3E';const loadObserver=new IntersectionObserver((entries)=>{entries.forEach(entry=>{if(!entry.isIntersecting)return;const img=entry.target;const real=img.dataset.src;if(real&&img.src!==real){img.src=real;img.addEventListener('load',()=>{releaseObserver.observe(img);},{once:true});}
loadObserver.unobserve(img);});},{rootMargin:'200px 0px 200px 0px',threshold:0});const releaseObserver=new IntersectionObserver((entries)=>{entries.forEach(entry=>{if(entry.isIntersecting)return;const img=entry.target;if(img.complete&&img.naturalWidth>0){img.src=PLACEHOLDER;loadObserver.observe(img);releaseObserver.unobserve(img);}});},{rootMargin:'0px 0px 800px 0px',threshold:0});function observeCovers(container){container.querySelectorAll('img.cover-lazy').forEach(img=>{loadObserver.observe(img);});}
function buildMediaCard({id,title,cover,source,type,badge,extra}){const safeTitle=(title||'').replace(/"/g,'&quot;').replace(/</g,'&lt;');const dataSrc=cover||'';let chipClass='chip-source';if(badge){if(badge.class==='badge-anime')chipClass='chip-anime';if(badge.class==='badge-manga')chipClass='chip-manga';}
const typeChipHtml=badge?`<span class="chip ${chipClass} type-chip">${badge.label}</span>`:'';return`
      <div class="media-card-wrapper">
        <div class="media-card"
          data-id="${id}"
          data-title="${safeTitle}"
          data-source="${source || ''}"
          data-type="${type || ''}">
          <!-- Image area -->
          <div class="card-image">
            <img class="cover-lazy"
                 src="${PLACEHOLDER}"
                 data-src="${dataSrc}"
                 alt="${safeTitle}"
                 style="background:var(--surface);">
            ${typeChipHtml}
          </div>
          <!-- Text area below image -->
          <div class="card-body">
            <p class="card-title">${safeTitle}</p>
            ${extra || ''}
          </div>
        </div>
      </div>`;}
async function search(refresh=false){if(currentType==='library')return;const type=currentType;const source=document.getElementById(`${type}-source`).value;const query=type==='anime'?animeSearchInput.value.trim():mangaSearchInput.value.trim();if(!query)return;const container=document.getElementById(`${type}-results`);if(source==='all'){searchAllStream(type,query,container);return;}
container.innerHTML=`
      <div class="empty-state">
        <div class="loading-spinner"></div>
        <p>Buscando…</p>
      </div>`;try{let url=`/api/search?type=${type}&source=${source}&q=${encodeURIComponent(query)}`;if(refresh)url+='&refresh=1';const res=await fetch(url);if(!res.ok)throw new Error(`HTTP ${res.status}`);renderSearchResults(await res.json(),type,source);}catch(err){container.innerHTML=`
        <div class="empty-state">
          <i class="fas fa-exclamation-circle" style="color:var(--accent2);"></i>
          <p>Error al buscar: ${err.message}</p>
        </div>`;}}
function searchAllStream(type,query,container){container.innerHTML=`
      <div class="empty-state" id="stream-loading">
        <div class="loading-spinner"></div>
        <p>Buscando en todas las fuentes…</p>
      </div>`;const seen=new Set();const es=new EventSource(`/api/search-all-stream?type=${type}&q=${encodeURIComponent(query)}`);if(!container.dataset.streamBound){container.dataset.streamBound='1';container.addEventListener('click',e=>{const downloadBtn=e.target.closest('.download-btn');const card=e.target.closest('.media-card');if(!card)return;if(downloadBtn){e.stopPropagation();const{id,title,source:src,type:typ}=card.dataset;downloadSeries(typ,src,id,title);return;}
const{id,source:src,type:typ}=card.dataset;window.location.href=`/serie/${typ}/${src}/${id}`;});}
function showEmpty(){container.innerHTML=`
        <div class="empty-state">
          <i class="fas fa-search"></i>
          <p>Sin resultados para esa búsqueda.</p>
        </div>`;}
function showError(msg){container.innerHTML=`
        <div class="empty-state">
          <i class="fas fa-exclamation-circle" style="color:var(--accent2);"></i>
          <p>${msg}</p>
        </div>`;}
es.addEventListener('results',e=>{const data=JSON.parse(e.data);const items=data.results;if(!items.length)return;const newItems=[];for(const item of items){const key=`${item.source}:${item.id}`;if(!seen.has(key)){seen.add(key);newItems.push(item);}}
if(!newItems.length)return;const loadingEl=document.getElementById('stream-loading');if(loadingEl)loadingEl.remove();const html=newItems.map(item=>buildMediaCard({id:item.id,title:item.title,cover:item.cover,source:item.source,type,badge:{class:'badge-source',label:item.source},extra:`<div class="card-chips">
                     <span class="chip chip-source" style="font-size:10px; height:22px; padding:0 8px;">${item.source}</span>
                   </div>
                   <div class="card-actions">
                      <button class="download-btn card-dl-btn">
                      <i class="fas fa-download"></i> Descargar todo
                      </button>
                   </div>`,})).join('');container.insertAdjacentHTML('beforeend',html);observeCovers(container);if(window.animateCards)window.animateCards(`#${type}-results`);});es.addEventListener('done',()=>{es.close();if(seen.size===0)showEmpty();});es.addEventListener('error',()=>{if(es.readyState===EventSource.CLOSED){if(seen.size===0)showError('Error al conectar con el servidor.');}});}
function renderSearchResults(items,type,source){const container=document.getElementById(`${type}-results`);if(!items.length){container.innerHTML=`
        <div class="empty-state">
          <i class="fas fa-search"></i>
          <p>Sin resultados para esa búsqueda.</p>
        </div>`;return;}
container.innerHTML=items.map(item=>{const itemSource=item.source||source;return buildMediaCard({id:item.id,title:item.title,cover:item.cover,source:itemSource,type,badge:{class:'badge-source',label:itemSource},extra:`<div class="card-chips">
                   <span class="chip chip-source" style="font-size:10px; height:22px; padding:0 8px;">${itemSource}</span>
                 </div>
                  <div class="card-actions">
                    <button class="download-btn card-dl-btn">
                    <i class="fas fa-download"></i> Descargar todo
                    </button>
                  </div>`,});}).join('');observeCovers(container);if(window.animateCards)window.animateCards(`#${type}-results`);container.addEventListener('click',e=>{const downloadBtn=e.target.closest('.download-btn');const card=e.target.closest('.media-card');if(!card)return;if(downloadBtn){e.stopPropagation();const{id,title,source:src,type:typ}=card.dataset;downloadSeries(typ,src,id,title);return;}
const{id,source:src,type:typ}=card.dataset;window.location.href=`/serie/${typ}/${src}/${id}`;},{once:false});}
async function downloadSeries(type,source,contentId,title){try{const res=await fetch('/api/download',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type,source,content_id:contentId,title,exclude_watched:true}),});const data=await res.json();if(!res.ok){showNotification(`Error: ${data.error}`,'error');}else{showNotification('Descarga encolada','success');if(window.showDownloadIndicator)window.showDownloadIndicator();}}catch(err){showNotification(`Error al encolar: ${err.message}`,'error');}}
const STATUS_META={watching:{label:'Mirando',color:'var(--accent)',border:'rgba(196,107,255,0.4)',bg:'rgba(196,107,255,0.12)',icon:'fa-eye'},completed:{label:'Visto',color:'#4ade80',border:'rgba(74,222,128,0.4)',bg:'rgba(74,222,128,0.12)',icon:'fa-check-circle'},pending:{label:'Pendiente',color:'#fbbf24',border:'rgba(251,191,36,0.4)',bg:'rgba(251,191,36,0.12)',icon:'fa-clock'},none:{label:'',color:'',border:'',bg:'',icon:''},};const STATUS_ORDER={watching:0,completed:1,pending:2,none:3};async function loadLibrary(){const container=document.getElementById('library-results');if(!container)return;container.innerHTML=`
      <div class="empty-state">
        <div class="loading-spinner"></div>
        <p>Cargando biblioteca…</p>
      </div>`;try{const[itemsRes,statusRes]=await Promise.all([fetch('/api/library'),fetch('/api/library/status'),]);if(!itemsRes.ok)throw new Error(`HTTP ${itemsRes.status}`);_libraryItems=await itemsRes.json();_libraryStatuses=statusRes.ok?await statusRes.json():{};_initLibraryControls();applyLibraryView();fetchUpdatesBadge();}catch(err){container.innerHTML=`
        <div class="empty-state">
          <i class="fas fa-exclamation-circle" style="color:var(--accent2);"></i>
          <p>Error al cargar biblioteca: ${err.message}</p>
        </div>`;}}
async function fetchUpdatesBadge(){try{const res=await fetch('/api/library/updates');const data=await res.json();const total=data.total||0;const oldBadge=tabLibrary.querySelector('.update-badge-global');if(oldBadge)oldBadge.remove();if(total>0){const badge=document.createElement('span');badge.className='update-badge-global';badge.textContent=total>99?'99+':total;badge.title=`${total} serie${total !== 1 ? 's' : ''} con capítulos nuevos`;Object.assign(badge.style,{position:'absolute',top:'-5px',right:'-6px',background:'var(--accent2, #f59e0b)',color:'#000',fontSize:'9px',fontWeight:'700',borderRadius:'999px',padding:'1px 5px',lineHeight:'1.5',pointerEvents:'none',zIndex:'5',});tabLibrary.style.position='relative';tabLibrary.appendChild(badge);}}catch(err){console.warn('fetchUpdatesBadge:',err);}}
function _initLibraryControls(){const searchInput=document.getElementById('library-search-input');if(searchInput){let debounceTimer;searchInput.addEventListener('input',()=>{clearTimeout(debounceTimer);debounceTimer=setTimeout(()=>{_libraryQuery=searchInput.value.toLowerCase();applyLibraryView();},150);});}
const filtersBar=document.getElementById('library-status-filters');if(filtersBar){filtersBar.addEventListener('click',e=>{const btn=e.target.closest('.lib-filter');if(!btn)return;_libraryFilter=btn.dataset.filter;filtersBar.querySelectorAll('.lib-filter').forEach(b=>b.classList.remove('active'));btn.classList.add('active');applyLibraryView();});}}
let _renderedCards=new Map();function applyLibraryView(){const container=document.getElementById('library-results');if(!container)return;let filtered=_libraryItems.filter(item=>{const status=_libraryStatuses[`local:${item.id}`]||'none';return _libraryFilter==='all'||status===_libraryFilter;});if(_libraryQuery){filtered=filtered.filter(item=>(item.title||'').toLowerCase().includes(_libraryQuery)||(item.id||'').toLowerCase().includes(_libraryQuery));}
filtered.sort((a,b)=>{const sa=STATUS_ORDER[_libraryStatuses[`local:${a.id}`]||'none'];const sb=STATUS_ORDER[_libraryStatuses[`local:${b.id}`]||'none'];return sa!==sb?sa-sb:(a.title||'').localeCompare(b.title||'');});const countEl=document.getElementById('library-count');if(countEl)countEl.textContent=`${filtered.length} serie${filtered.length !== 1 ? 's' : ''}`;if(!filtered.length){container.innerHTML=_libraryItems.length?`<div class="empty-state" style="grid-column:1/-1;">
             <i class="fas fa-filter"></i>
             <p>Ninguna serie coincide con el filtro.</p>
           </div>`:`<div class="empty-state" style="grid-column:1/-1;">
             <i class="fas fa-folder-open"></i>
             <p>Tu biblioteca está vacía. Usa la búsqueda para descargar series.</p>
           </div>`;_renderedCards.clear();return;}
const nextIds=new Set(filtered.map(i=>i.id));const prevIds=new Set(_renderedCards.keys());for(const id of prevIds){if(!nextIds.has(id)){_renderedCards.get(id).remove();_renderedCards.delete(id);}}
const frag=document.createDocumentFragment();filtered.forEach(item=>{if(!_renderedCards.has(item.id)){const wrapper=_buildLibraryCard(item);_renderedCards.set(item.id,wrapper);frag.appendChild(wrapper);}});if(frag.childElementCount>0){Array.from(container.children).forEach(child=>{if(!child.classList.contains('media-card-wrapper'))child.remove();});container.appendChild(frag);observeCovers(container);if(window.animateCards)window.animateCards('#library-results');}
filtered.forEach(item=>{const node=_renderedCards.get(item.id);if(node&&node.parentNode===container){container.appendChild(node);}});}
function _buildLibraryCard(item){const ref=`local:${item.id}`;const status=_libraryStatuses[ref]||'none';const meta=STATUS_META[status];const resumeChapter=item.progress_chapter&&item.progress_chapter!=='0'?item.progress_chapter:(item.last_chapter||'1');const isAnime=item.type==='anime';const typeClass=isAnime?'chip-anime':'chip-manga';const typeLabel=isAnime?'Anime':'Manga';const statusChipClass=status!=='none'?`chip-${status}`:'';const statusChipHtml=meta.label?`<span class="chip-sep"></span>
         <span class="chip ${statusChipClass}" style="font-size:10px; height:22px; padding:0 8px;">
           <i class="fas ${meta.icon}" style="font-size:9px; margin-right:3px;"></i>${meta.label}
         </span>`:'';const statusBtn=`
      <button class="status-tag-btn" data-ref="${ref}" title="Cambiar etiqueta"
        style="background:${meta.bg || 'rgba(255,255,255,0.05)'}; border-color:${meta.border || 'var(--border)'}; color:${meta.color || 'var(--muted)'};">
        <i class="fas ${meta.icon || 'fa-tag'}"></i>
      </button>`;const html=buildMediaCard({id:item.id||'',title:item.title,cover:item.cover,source:'local',type:item.type||'',badge:{class:`badge-${item.type}`,label:typeLabel},extra:`<div class="card-chips card-chips-nowrap">
                  <span class="chip ${typeClass} chip-sm">${typeLabel}</span>
                  ${statusChipHtml}
                </div>
                <div class="card-actions-row">
                  <button class="resume-btn" data-last-chapter="${resumeChapter}">
                    <i class="fas fa-play" style="font-size:9px;"></i> Cap. ${resumeChapter}
                  </button>
                  ${statusBtn}
                </div>`,});const div=document.createElement('div');div.innerHTML=html;const wrapper=div.firstElementChild;const card=wrapper.querySelector('.media-card');card.addEventListener('click',e=>{if(e.target.closest('.resume-btn, .status-tag-btn'))return;const{type,id}=card.dataset;if(type&&id)window.location.href=`/serie/${type}/local/${id}`;});wrapper.querySelector('.resume-btn')?.addEventListener('click',e=>{e.stopPropagation();const{type,id}=card.dataset;const ch=e.currentTarget.dataset.lastChapter;if(type&&id&&ch)window.location.href=`/reader/${type}/local/${id}/${ch}`;});wrapper.querySelector('.status-tag-btn')?.addEventListener('click',e=>{e.stopPropagation();openStatusPopup(e.currentTarget,ref);});return wrapper;}
let _statusPopup=null;let _popupCloseHandler=null;const STATUS_OPTIONS=[{value:'watching',label:'Mirando',icon:'fa-eye',color:'var(--accent)',border:'rgba(196,107,255,0.35)',bg:'rgba(196,107,255,0.1)'},{value:'completed',label:'Visto',icon:'fa-check-circle',color:'#4ade80',border:'rgba(74,222,128,0.35)',bg:'rgba(74,222,128,0.1)'},{value:'pending',label:'Pendiente',icon:'fa-clock',color:'#fbbf24',border:'rgba(251,191,36,0.35)',bg:'rgba(251,191,36,0.1)'},{value:'none',label:'Sin etiqueta',icon:'fa-tag',color:'var(--muted)',border:'var(--border)',bg:'transparent'},];function openStatusPopup(anchorBtn,ref){closeStatusPopup();const current=_libraryStatuses[ref]||'none';const popup=document.createElement('div');popup.id='status-popup';Object.assign(popup.style,{position:'fixed',zIndex:'10002',background:'rgba(10,10,15,0.97)',border:'1px solid rgba(255,255,255,0.12)',borderRadius:'12px',padding:'6px',display:'flex',flexDirection:'column',gap:'3px',backdropFilter:'blur(16px)',boxShadow:'0 8px 32px rgba(0,0,0,0.5)',minWidth:'160px',opacity:'0',transform:'scale(0.95) translateY(-4px)',transition:'opacity 0.15s ease, transform 0.15s ease',});STATUS_OPTIONS.forEach(opt=>{const row=document.createElement('button');const isActive=opt.value===current;Object.assign(row.style,{display:'flex',alignItems:'center',gap:'9px',padding:'7px 10px',borderRadius:'8px',border:isActive?`1px solid ${opt.border}`:'1px solid transparent',background:isActive?opt.bg:'transparent',color:isActive?opt.color:'var(--muted)',fontSize:'13px',fontFamily:'var(--ff-body)',cursor:'pointer',textAlign:'left',width:'100%',transition:'background 0.12s, color 0.12s',});row.innerHTML=`
        <i class="fas ${opt.icon}" style="font-size:11px; width:14px; text-align:center; flex-shrink:0;"></i>
        <span>${opt.label}</span>
        ${isActive ? '<i class="fas fa-check" style="margin-left:auto; font-size:10px; opacity:0.7;"></i>' : ''}`;row.addEventListener('mouseenter',()=>{row.style.background=opt.bg||'rgba(255,255,255,0.05)';row.style.color=opt.color||'var(--text)';});row.addEventListener('mouseleave',()=>{if(opt.value!==current){row.style.background='transparent';row.style.color='var(--muted)';}});row.addEventListener('click',async e=>{e.stopPropagation();closeStatusPopup();if(opt.value===current)return;try{const res=await fetch('/api/library/status',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content_ref:ref,status:opt.value}),});if(res.ok){_libraryStatuses[ref]=opt.value;showNotification(opt.value==='none'?'Etiqueta eliminada':`Marcado como ${opt.label}`,'success',2000);const id=ref.replace('local:','');const oldNode=_renderedCards.get(id);if(oldNode)oldNode.remove();_renderedCards.delete(id);applyLibraryView();}else{showNotification('Error al guardar etiqueta','error');}}catch(err){showNotification(`Error: ${err.message}`,'error');}});popup.appendChild(row);});document.body.appendChild(popup);_statusPopup=popup;const rect=anchorBtn.getBoundingClientRect();const pw=160;const ph=4*38;let top=rect.bottom+6;let left=rect.left;if(left+pw>window.innerWidth-8)left=window.innerWidth-pw-8;if(top+ph>window.innerHeight-8)top=rect.top-ph-6;if(left<8)left=8;popup.style.top=`${top}px`;popup.style.left=`${left}px`;requestAnimationFrame(()=>requestAnimationFrame(()=>{popup.style.opacity='1';popup.style.transform='scale(1) translateY(0)';}));_popupCloseHandler=e=>{if(!popup.contains(e.target)&&e.target!==anchorBtn)closeStatusPopup();};setTimeout(()=>{document.addEventListener('click',_popupCloseHandler);document.addEventListener('keydown',_escCloseHandler);},0);}
function _escCloseHandler(e){if(e.key==='Escape')closeStatusPopup();}
function closeStatusPopup(){if(!_statusPopup)return;const popup=_statusPopup;_statusPopup=null;popup.style.opacity='0';popup.style.transform='scale(0.95) translateY(-4px)';setTimeout(()=>popup.remove(),150);document.removeEventListener('click',_popupCloseHandler);document.removeEventListener('keydown',_escCloseHandler);}
window.showNotification=function(message,type='info',duration=3500){let container=document.getElementById('toast-container');if(!container){container=document.createElement('div');container.id='toast-container';Object.assign(container.style,{position:'fixed',bottom:'24px',right:'24px',zIndex:'10001',display:'flex',flexDirection:'column',gap:'8px',pointerEvents:'none',maxWidth:'320px',});document.body.appendChild(container);}
const colors={success:{bg:'rgba(74,222,128,0.15)',border:'rgba(74,222,128,0.3)',icon:'✓'},error:{bg:'rgba(248,113,113,0.15)',border:'rgba(248,113,113,0.3)',icon:'✕'},info:{bg:'rgba(196,107,255,0.12)',border:'rgba(196,107,255,0.25)',icon:'ℹ'},};const c=colors[type]||colors.info;const toast=document.createElement('div');Object.assign(toast.style,{background:c.bg,border:`1px solid ${c.border}`,backdropFilter:'blur(12px)',color:'var(--text)',padding:'10px 14px',borderRadius:'10px',fontSize:'13px',fontFamily:'var(--ff-body)',pointerEvents:'auto',boxShadow:'0 4px 20px rgba(0,0,0,0.3)',opacity:'0',transform:'translateX(20px)',transition:'opacity 0.22s ease, transform 0.22s ease',display:'flex',alignItems:'center',gap:'8px',});toast.innerHTML=`<span style="flex-shrink:0; opacity:0.8;">${c.icon}</span><span>${message}</span>`;container.appendChild(toast);requestAnimationFrame(()=>requestAnimationFrame(()=>{toast.style.opacity='1';toast.style.transform='translateX(0)';}));setTimeout(()=>{toast.style.opacity='0';toast.style.transform='translateX(20px)';setTimeout(()=>toast.remove(),250);},duration);};async function populateSourceDropdowns(){try{const res=await fetch('/api/settings/sources');if(!res.ok)return;const sources=await res.json();const animeSelect=document.getElementById('anime-source');const mangaSelect=document.getElementById('manga-source');animeSelect.innerHTML='';mangaSelect.innerHTML='';sources.forEach(src=>{if(!src.enabled)return;const opt=document.createElement('option');opt.value=src.name;opt.textContent=src.label;if(src.type==='anime'){animeSelect.appendChild(opt);}else{mangaSelect.appendChild(opt);}});const allOpt=document.createElement('option');allOpt.value='all';allOpt.textContent='Todas las fuentes';mangaSelect.insertBefore(allOpt,mangaSelect.firstChild);}catch(err){console.warn('Error cargando fuentes:',err);}}
animeSearchBtn?.addEventListener('click',()=>search(false));mangaSearchBtn?.addEventListener('click',()=>search(false));animeRefreshBtn?.addEventListener('click',()=>search(true));mangaRefreshBtn?.addEventListener('click',()=>search(true));animeSearchInput?.addEventListener('keypress',e=>{if(e.key==='Enter')search(false);});mangaSearchInput?.addEventListener('keypress',e=>{if(e.key==='Enter')search(false);});setActiveTab('library');populateSourceDropdowns();})();
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
closePopup();});document.addEventListener('keydown',e=>{if(e.key==='Escape'&&popupOpen)closePopup();});window.showDownloadIndicator=function(){forceUntil=Date.now()+10000;showIndicator();clearPolling();fetchQueueStatus();};fetchQueueStatus();})();(function(){'use strict';if(!window.serieData){console.error('serie.js: window.serieData no definido');return;}
const{type,source,id}=window.serieData;const isLocal=source==='local';const STREAMABLE_SOURCES={anime:['jkanime'],manga:['nartag','manhwaweb','ikigai']};const canStream=!isLocal&&STREAMABLE_SOURCES[type]?.includes(source);let chapters=[];let sortAsc=true;let originalSource=null;let originalId=null;const coverImg=document.getElementById('serie-cover');const titleEl=document.getElementById('serie-title');const synopsisEl=document.getElementById('serie-synopsis');const downloadAllBtn=document.getElementById('download-all-btn');const continueBtn=document.getElementById('continue-btn');const deleteWatchedBtn=document.getElementById('delete-watched-btn');const currentChapterSpan=document.getElementById('current-chapter');const progressPercentSpan=document.getElementById('progress-percent');const progressBarFill=document.getElementById('progress-bar-fill');const chaptersContainer=document.getElementById('chapters-list');const sortBtn=document.getElementById('sort-btn');const chaptersCount=document.getElementById('chapters-count');const badgeEl=document.getElementById('serie-type-badge');const checkUpdatesBtn=document.getElementById('check-updates-btn');function notify(msg,t='info'){if(window.showNotification)window.showNotification(msg,t);else console.log(`[${t}] ${msg}`);}
async function loadSerieDetails(){try{const url=isLocal?`/api/content/local/${type}/${id}`:`/api/content/${type}/${source}/${id}`;const res=await fetch(url);if(!res.ok)throw new Error(`HTTP ${res.status}`);const data=await res.json();titleEl.textContent=data.title||'Sin título';synopsisEl.textContent=data.synopsis||'Sin descripción disponible.';if(data.cover){coverImg.dataset.src=data.cover;coverImg.src=data.cover;}
if(isLocal&&data.source){originalSource=data.source;originalId=data.remote_id||null;}
if(badgeEl){badgeEl.textContent=type==='anime'?'Anime':'Manga';badgeEl.className=`card-badge ${type === 'anime' ? 'badge-anime' : 'badge-manga'}`;}}catch(err){console.error('loadSerieDetails:',err);titleEl.textContent='Error al cargar';synopsisEl.textContent='No se pudieron obtener los detalles.';}}
async function loadChapters(){chaptersContainer.innerHTML=`
      <div style="grid-column:1/-1; display:flex; align-items:center; justify-content:center;
                  gap:12px; padding:48px 20px; color:var(--muted);">
        <div class="loading-spinner"></div>
        <span style="font-size:14px;">Cargando capítulos…</span>
      </div>`;try{let remote=[];let localSet=new Set();let watchedSet=new Set();if(isLocal){const[chapRes,watchRes]=await Promise.all([fetch(`/api/chapters/local/${type}/${id}`),fetch(`/api/watched/local:${id}`),]);remote=chapRes.ok?await chapRes.json():[];remote=remote.map(ch=>({...ch,is_downloaded:true}));if(watchRes.ok){const data=await watchRes.json();watchedSet=new Set((data.watched||[]).map(Number));}}else{const[remoteRes,localRes]=await Promise.all([fetch(`/api/chapters/${type}/${source}/${id}`),fetch(`/api/chapters/local/${type}/${id}`),]);remote=remoteRes.ok?await remoteRes.json():[];const localChaps=localRes.ok?await localRes.json():[];localSet=new Set(localChaps.map(ch=>String(ch.number)));remote=remote.map(ch=>({...ch,is_downloaded:localSet.has(String(ch.number))}));}
chapters=remote.map(ch=>({...ch,is_watched:watchedSet.has(Number(ch.number)),}));renderChapters();}catch(err){console.error('loadChapters:',err);chaptersContainer.innerHTML=`
        <div class="empty-state" style="grid-column:1/-1;">
          <i class="fas fa-exclamation-circle" style="color:var(--accent2);"></i>
          <p>Error al cargar capítulos: ${err.message}</p>
        </div>`;}}
const BATCH_SIZE=30;let _sorted=[];let _rendered=0;let _sentinel=null;let _observer=null;function _teardownObserver(){if(_observer){_observer.disconnect();_observer=null;}
if(_sentinel){_sentinel.remove();_sentinel=null;}}
function _appendBatch(){const end=Math.min(_rendered+BATCH_SIZE,_sorted.length);const frag=document.createDocumentFragment();for(let i=_rendered;i<end;i++){const temp=document.createElement('div');temp.innerHTML=buildPillHtml(_sorted[i]);frag.appendChild(temp.firstElementChild);}
_teardownObserver();chaptersContainer.appendChild(frag);_rendered=end;if(_rendered<_sorted.length){_sentinel=document.createElement('div');_sentinel.style.cssText='grid-column:1/-1; height:1px; pointer-events:none;';chaptersContainer.appendChild(_sentinel);_observer=new IntersectionObserver(entries=>{if(entries[0].isIntersecting)_appendBatch();},{rootMargin:'200px'});_observer.observe(_sentinel);}
if(window.animateCards)window.animateCards('#chapters-list','.chapter-pill');}
function renderChapters(){_teardownObserver();if(!chapters.length){chaptersContainer.innerHTML=`
        <div class="empty-state" style="grid-column:1/-1;">
          <i class="fas fa-inbox"></i>
          <p>No se encontraron capítulos.</p>
        </div>`;return;}
if(chaptersCount)chaptersCount.textContent=`${chapters.length} capítulos`;_sorted=sortAsc?[...chapters]:[...chapters].reverse();_rendered=0;chaptersContainer.innerHTML='';bindChapterEvents();_appendBatch();}
function buildPillHtml(ch){const{number,id:chId,is_downloaded,is_watched}=ch;const watchedDot=is_watched?`<span class="watched-dot"></span>`:'';const actionBtn=is_downloaded?`<button class="play-chapter-btn chapter-action-btn" data-chapter="${number}" title="Reproducir">
           <i class="fas fa-play"></i>
         </button>`:canStream?`<button class="stream-chapter-btn chapter-action-btn" data-chapter="${number}" title="Reproducir en streaming">
             <i class="fas fa-play"></i>
           </button>
           <button class="download-chapter-btn chapter-action-btn" data-chapter="${number}" data-chapter-id="${chId}" title="Descargar">
             <i class="fas fa-download"></i>
           </button>`:`<button class="download-chapter-btn chapter-action-btn" data-chapter="${number}" data-chapter-id="${chId}" title="Descargar">
             <i class="fas fa-download"></i>
           </button>`;const localBtns=isLocal?`
      <button class="watched-toggle-btn chapter-action-btn ${is_watched ? 'is-watched' : ''}"
              data-chapter="${number}" title="${is_watched ? 'Quitar visto' : 'Marcar visto'}">
        <i class="fas fa-check"></i>
      </button>
      <button class="delete-chapter-btn chapter-action-btn" data-chapter="${number}" title="Eliminar">
        <i class="fas fa-trash-alt"></i>
      </button>`:'';return`
      <div class="chapter-pill ${is_downloaded ? 'downloaded' : ''} ${is_watched ? 'watched' : ''}"
           data-chapter="${number}">
        <div class="pill-label">
          <span class="pill-num ${is_watched ? 'muted' : ''}">Cap. ${number}</span>
          ${watchedDot}
        </div>
        <div class="pill-actions">
          ${actionBtn}
          ${localBtns}
        </div>
      </div>`;}
let _delegationBound=false;function bindChapterEvents(){if(_delegationBound)return;_delegationBound=true;chaptersContainer.addEventListener('click',e=>{const btn=e.target.closest('.chapter-action-btn');if(!btn)return;e.stopPropagation();const{chapter,chapterId}=btn.dataset;if(btn.classList.contains('play-chapter-btn')||btn.classList.contains('stream-chapter-btn')){window.location.href=`/reader/${type}/${source}/${id}/${chapter}`;}else if(btn.classList.contains('download-chapter-btn')){downloadSingleChapter(chapter,chapterId);}else if(btn.classList.contains('watched-toggle-btn')){toggleWatched(chapter);}else if(btn.classList.contains('delete-chapter-btn')){showConfirm(`¿Eliminar el capítulo ${chapter}? Esta acción no se puede deshacer.`,()=>deleteChapter(chapter));}});}
function patchPillInDOM(chapterNum){const ch=chapters.find(c=>String(c.number)===String(chapterNum));if(!ch)return;const pill=chaptersContainer.querySelector(`.chapter-pill[data-chapter="${chapterNum}"]`);if(!pill)return;const temp=document.createElement('div');temp.innerHTML=buildPillHtml(ch);const newPill=temp.firstElementChild;pill.replaceWith(newPill);}
function showConfirm(message,onConfirm){const modalTitle=document.getElementById('modal-title');const modalBody=document.getElementById('modal-body');if(!modalTitle||!modalBody){if(window.confirm(message))onConfirm();return;}
modalTitle.textContent='Confirmar acción';modalBody.innerHTML=`
      <div style="display:flex; flex-direction:column; gap:20px;">
        <p style="color:var(--text); font-size:14px; line-height:1.6;">${message}</p>
        <div style="display:flex; gap:10px; justify-content:flex-end;">
          <button id="confirm-cancel" class="btn-ghost">Cancelar</button>
          <button id="confirm-ok" class="btn-primary" style="background:#f87171;">
            <i class="fas fa-trash-alt"></i> Eliminar
          </button>
        </div>
      </div>`;if(window.openModal)window.openModal();document.getElementById('confirm-cancel').addEventListener('click',()=>{if(window.closeModal)window.closeModal();});document.getElementById('confirm-ok').addEventListener('click',()=>{if(window.closeModal)window.closeModal();onConfirm();});}
async function toggleWatched(chapterNum){try{const res=await fetch('/api/watched/toggle',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content_ref:`local:${id}`,chapter:chapterNum}),});const data=await res.json();if(res.ok){const wasWatched=data.status==='watched';const ch=chapters.find(c=>String(c.number)===String(chapterNum));if(ch)ch.is_watched=wasWatched;patchPillInDOM(chapterNum);updateProgress();notify(`Cap. ${chapterNum} marcado como ${wasWatched ? 'visto' : 'no visto'}`,'success');}else{notify(`Error: ${data.error}`,'error');}}catch(err){notify(`Error: ${err.message}`,'error');}}
async function deleteChapter(chapterNum){try{const res=await fetch('/api/delete-chapter',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content_ref:`local:${id}`,type,chapter:chapterNum}),});const data=await res.json();if(res.ok){notify(`Capítulo ${chapterNum} eliminado`,'success');chapters=chapters.filter(c=>String(c.number)!==String(chapterNum));chaptersContainer.querySelector(`.chapter-pill[data-chapter="${chapterNum}"]`)?.remove();if(chaptersCount)chaptersCount.textContent=`${chapters.length} capítulos`;await loadProgress();}else{notify(`Error: ${data.error}`,'error');}}catch(err){notify(`Error: ${err.message}`,'error');}}
async function downloadSingleChapter(chapterNum,chapterId){if(isLocal){notify('Este contenido ya está descargado localmente.','info');return;}
try{const res=await fetch('/api/download/chapter',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type,source,content_id:id,chapter_id:chapterId,title:titleEl.textContent,}),});const data=await res.json();if(res.ok){notify(`Cap. ${chapterNum} encolado para descarga`,'success');if(window.showDownloadIndicator)window.showDownloadIndicator();}else{notify(`Error: ${data.error}`,'error');}}catch(err){notify(`Error: ${err.message}`,'error');}}
async function downloadFullSeries(){if(isLocal){notify('Esta serie ya está descargada localmente.','info');return;}
try{const res=await fetch('/api/download',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type,source,content_id:id,title:titleEl.textContent}),});const data=await res.json();if(res.ok){notify(`Descarga de serie completa encolada (ID: ${data.job_id})`,'success');if(window.showDownloadIndicator)window.showDownloadIndicator();}else{notify(`Error: ${data.error}`,'error');}}catch(err){notify(`Error: ${err.message}`,'error');}}
async function checkForUpdates(){if(!isLocal)return;checkUpdatesBtn.disabled=true;const icon=checkUpdatesBtn.querySelector('i');if(icon){icon.className='fas fa-spinner fa-spin';}
checkUpdatesBtn.querySelector('.btn-label').textContent='Buscando…';try{const refSource=originalSource||source;const refId=originalId||id;const contentRef=`${refSource}:${refId}`;const res=await fetch(`/api/library/check-updates/${contentRef}`,{method:'POST',});const data=await res.json();if(!res.ok||data.error){notify(`Error al buscar actualizaciones: ${data.error || res.status}`,'error');return;}
const newChaps=data.new_chapters||[];const newChapIds=data.new_chapter_ids||[];if(newChaps.length===0){notify('✓ Serie al día, no hay episodios nuevos','success');}else{const label=newChaps.length===1?`1 capítulo nuevo (cap. ${newChaps[0]})`:`${newChaps.length} capítulos nuevos (${newChaps[0]}–${newChaps[newChaps.length - 1]})`;notify(`🆕 ${label} — descargando…`,'info');_showUpdateBadge(newChaps.length);await downloadNewChapters(refSource,refId,newChapIds);}
checkUpdatesBtn.title=`Última comprobación: ${new Date().toLocaleTimeString()}`;}catch(err){notify(`Error: ${err.message}`,'error');}finally{_restoreCheckBtn(false);}}
async function downloadNewChapters(refSource,refId,chapterIds){if(!chapterIds.length)return;_restoreCheckBtn(true);const icon=checkUpdatesBtn.querySelector('i');if(icon)icon.className='fas fa-spinner fa-spin';checkUpdatesBtn.querySelector('.btn-label').textContent='Descargando…';try{const res=await fetch('/api/download/chapters',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type:type,source:refSource,content_id:refId,title:titleEl.textContent,chapter_ids:chapterIds,}),});const data=await res.json();if(res.ok){notify(`${data.message}`,'success');if(window.showDownloadIndicator)window.showDownloadIndicator();_showUpdateBadge(0);}else{notify(`Error al descargar: ${data.error}`,'error');}}catch(err){notify(`Error al descargar: ${err.message}`,'error');}}
function _restoreCheckBtn(skipIconRestore){checkUpdatesBtn.disabled=false;if(!skipIconRestore){const icon=checkUpdatesBtn.querySelector('i');if(icon)icon.className='fas fa-sync-alt';}
checkUpdatesBtn.querySelector('.btn-label').textContent='Actualizar';}
function _showUpdateBadge(count){checkUpdatesBtn.querySelector('.update-badge')?.remove();if(count<=0)return;const badge=document.createElement('span');badge.className='update-badge';badge.textContent=count;badge.style.cssText=`
      position: absolute;
      top: -6px; right: -6px;
      background: var(--accent2, #f59e0b);
      color: #000;
      font-size: 10px;
      font-weight: 700;
      border-radius: 999px;
      padding: 1px 5px;
      line-height: 1.4;
      pointer-events: none;
    `;checkUpdatesBtn.style.position='relative';checkUpdatesBtn.appendChild(badge);}
async function loadProgress(){try{const url=isLocal?`/api/progress/local/${type}/${id}`:`/api/progress/${type}/${source}/${id}`;const res=await fetch(url);const prog=await res.json();if(currentChapterSpan)currentChapterSpan.textContent=prog.chapter;_progressData=prog;await _renderProgress(prog);}catch(err){console.error('loadProgress:',err);}}
let _progressData=null;async function updateProgress(){if(!_progressData)return;await _renderProgress(_progressData);}
async function _renderProgress(prog){if(currentChapterSpan)currentChapterSpan.textContent=prog.chapter;if(type==='anime'){const savedTime=parseInt(prog.progress)||0;if(isLocal){try{const durRes=await fetch(`/api/video-duration/anime/${id}/${prog.chapter}`);if(durRes.ok){const{duration}=await durRes.json();if(duration>0){const pct=Math.round((savedTime/duration)*100);if(progressPercentSpan)progressPercentSpan.textContent=`${pct}%`;if(progressBarFill)progressBarFill.style.width=`${pct}%`;return;}}}catch(e){console.warn(e);}}
const mins=Math.floor(savedTime/60);const secs=savedTime%60;if(progressPercentSpan)
progressPercentSpan.textContent=`${mins}:${secs.toString().padStart(2, '0')}`;}else{const savedIndex=parseInt(prog.progress)||0;if(isLocal){const total=await getTotalImagesInChapter(prog.chapter);if(total>1){const pct=Math.min(100,Math.round((savedIndex/(total-1))*100));if(progressPercentSpan)progressPercentSpan.textContent=`${pct}%`;if(progressBarFill)progressBarFill.style.width=`${pct}%`;}else if(total===1){if(progressPercentSpan)progressPercentSpan.textContent='100%';if(progressBarFill)progressBarFill.style.width='100%';}else{if(progressPercentSpan)progressPercentSpan.textContent='?%';}}else{if(progressPercentSpan)progressPercentSpan.textContent='—';}}}
async function getTotalImagesInChapter(chapterNum){try{const res=await fetch(`/api/play/local/manga/${id}/${chapterNum}`);if(!res.ok)return 0;const paths=await res.json();return paths.length;}catch{return 0;}}
async function init(){await Promise.all([loadSerieDetails(),loadChapters(),]);await loadProgress();if(isLocal&&originalSource){const contentRef=`${originalSource}:${originalId}`;fetch('/api/library/acknowledge-updates',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content_ref:contentRef}),}).catch(()=>{});}
if(isLocal){if(downloadAllBtn)downloadAllBtn.style.display='none';if(continueBtn)continueBtn.style.display='inline-flex';if(deleteWatchedBtn)deleteWatchedBtn.style.display='inline-flex';if(checkUpdatesBtn){if(originalSource){checkUpdatesBtn.style.display='inline-flex';checkUpdatesBtn.addEventListener('click',checkForUpdates);}else{checkUpdatesBtn.style.display='none';}}}else{if(downloadAllBtn)downloadAllBtn.style.display='inline-flex';if(continueBtn)continueBtn.style.display='none';if(deleteWatchedBtn)deleteWatchedBtn.style.display='none';const progressSection=document.getElementById('progress-section');if(progressSection)progressSection.style.display='none';}
continueBtn?.addEventListener('click',()=>{let last=currentChapterSpan?.textContent;if(!last||last==='—')last='1';window.location.href=`/reader/${type}/local/${id}/${last}`;});downloadAllBtn?.addEventListener('click',downloadFullSeries);deleteWatchedBtn?.addEventListener('click',()=>{showConfirm('¿Eliminar todos los capítulos vistos (excepto el último)? Esta acción no se puede deshacer.',async()=>{try{const res=await fetch('/api/delete-watched',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content_ref:`local:${id}`,type}),});const data=await res.json();if(res.ok){const n=data.deleted?.length??0;notify(`Se eliminaron ${n} capítulo${n !== 1 ? 's' : ''}`,'success');const deletedNums=new Set((data.deleted||[]).map(String));chapters=chapters.filter(c=>!deletedNums.has(String(c.number)));deletedNums.forEach(num=>{chaptersContainer.querySelector(`.chapter-pill[data-chapter="${num}"]`)?.remove();});if(chaptersCount)chaptersCount.textContent=`${chapters.length} capítulos`;await loadProgress();}else{notify(`Error: ${data.error || 'Error desconocido'}`,'error');}}catch(err){notify(`Error: ${err.message}`,'error');}});});sortBtn?.addEventListener('click',()=>{sortAsc=!sortAsc;sortBtn.classList.toggle('sorted',!sortAsc);_teardownObserver();renderChapters();});}
init();})();
(function(){'use strict';const{type,source,content_id,current_chapter}=window.readerData;let chaptersList=[];let currentChapterIndex=-1;let currentChapterNum=current_chapter;let progressInterval=null;const mediaContainer=document.getElementById('media-content');const chapterWrapper=document.getElementById('chapter-wrapper');const prevBtn=document.getElementById('prev-btn');const nextBtn=document.getElementById('next-btn');const fullscreenBtn=document.getElementById('fullscreen-btn');const controlsDiv=document.getElementById('controls');const chapterLabelNum=document.getElementById('current-chapter-num');const backBtn=document.getElementById('back-to-serie');const UI_ELS=[controlsDiv,fullscreenBtn,backBtn].filter(Boolean);function showUI(){UI_ELS.forEach(el=>el.classList.add('show'));}
function hideUI(){UI_ELS.forEach(el=>el.classList.remove('show'));}
function updateChapterLabel(){if(chapterLabelNum)chapterLabelNum.textContent=currentChapterNum;if(prevBtn)prevBtn.disabled=currentChapterIndex<=0;if(nextBtn)nextBtn.disabled=currentChapterIndex>=chaptersList.length-1;if(window.animateChapterLabel)window.animateChapterLabel();}
async function markCurrentAsWatched(){const ref=source==='local'?`local:${content_id}`:`${source}:${content_id}`;try{await fetch('/api/watched',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content_ref:ref,chapter:currentChapterNum}),});}catch(e){console.warn('markCurrentAsWatched:',e);showNotification('Error al marcar como visto','error');}}
async function loadChaptersList(){try{const url=source==='local'?`/api/chapters/local/${type}/${content_id}`:`/api/chapters/${type}/${source}/${content_id}`;const res=await fetch(url);if(!res.ok)throw new Error('No se pudo obtener la lista de capítulos');chaptersList=await res.json();currentChapterIndex=chaptersList.findIndex(ch=>String(ch.number)===String(current_chapter));if(currentChapterIndex===-1&&chaptersList.length)currentChapterIndex=0;if(currentChapterIndex>=0)currentChapterNum=chaptersList[currentChapterIndex].number;updateChapterLabel();loadCurrentChapter();}catch(err){console.error(err);if(chapterWrapper)chapterWrapper.innerHTML=`<div style="color:var(--accent2); text-align:center; padding:20px;">
           Error al cargar capítulos: ${err.message}
         </div>`;}}
function loadCurrentChapter(){if(progressInterval){clearInterval(progressInterval);progressInterval=null;}
const doLoad=()=>{if(chapterWrapper)chapterWrapper.innerHTML=`
        <div style="display:flex; align-items:center; justify-content:center;
                    width:100%; height:100%;">
          <div class="loading-spinner"></div>
        </div>`;if(type==='anime')loadAnimeChapter();else loadMangaChapter();};if(window.chapterTransition)window.chapterTransition(doLoad);else doLoad();showUI();}
function prevChapter(){if(currentChapterIndex<=0)return;currentChapterIndex--;currentChapterNum=chaptersList[currentChapterIndex].number;updateChapterLabel();loadCurrentChapter();}
function nextChapter(){if(currentChapterIndex>=chaptersList.length-1)return;markCurrentAsWatched();currentChapterIndex++;currentChapterNum=chaptersList[currentChapterIndex].number;updateChapterLabel();loadCurrentChapter();}
function currentChapterId(){return chaptersList[currentChapterIndex]?.id||currentChapterNum;}
async function loadAnimeChapter(){try{const chapterArg=source==='local'?currentChapterNum:currentChapterId();const videoUrl=source==='local'?`/api/play/local/anime/${content_id}/${chapterArg}`:`/api/play/remote/anime/${source}/${content_id}/${chapterArg}`;let savedTime=0;let duration=0;let hasMarked=false;const fetches=[fetch(`/api/progress/${type}/${source}/${content_id}`).then(r=>r.ok?r.json():null).catch(()=>null),];if(source==='local'){fetches.push(fetch(`/api/video-duration/anime/${content_id}/${currentChapterNum}`).then(r=>r.ok?r.json():null).catch(()=>null));}
const[prog,durData]=await Promise.all(fetches);if(prog&&String(prog.chapter)===String(currentChapterNum)&&prog.progress)
savedTime=parseInt(prog.progress);if(durData?.duration>0)duration=durData.duration;if(chapterWrapper)chapterWrapper.innerHTML=`
      <video id="anime-video" controls autoplay
             style="width:100%; height:100%; object-fit:contain;">
        <source src="${videoUrl}" type="video/mp4">
      </video>`;const video=document.getElementById('anime-video');if(!video)return;if(savedTime>0)
video.addEventListener('loadedmetadata',()=>{video.currentTime=savedTime;},{once:true});let intervalActive=false;function startInterval(){if(intervalActive)return;intervalActive=true;progressInterval=setInterval(()=>{if(document.hidden||video.paused)return;const t=Math.floor(video.currentTime);fetch(`/api/progress/${type}/${source}/${content_id}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({chapter:currentChapterNum,progress:t}),}).catch(console.error);if(!hasMarked&&duration>0&&t>=duration*0.99){hasMarked=true;markCurrentAsWatched();}},15000);}
function stopInterval(){if(progressInterval){clearInterval(progressInterval);progressInterval=null;}
intervalActive=false;}
video.addEventListener('play',startInterval);video.addEventListener('pause',stopInterval);document.addEventListener('visibilitychange',()=>{if(document.hidden)stopInterval();else if(!video.paused)startInterval();},{once:false});video.addEventListener('ended',()=>{stopInterval();if(!hasMarked){hasMarked=true;markCurrentAsWatched();}
if(currentChapterIndex<chaptersList.length-1)nextChapter();});}catch(err){console.error(err);if(chapterWrapper)chapterWrapper.innerHTML=`<div style="color:var(--accent2); text-align:center; padding:20px;">
           Error al cargar capítulo: ${err.message}
         </div>`;}}
async function loadMangaChapter(){try{const isRemote=source!=='local';const chapterArg=isRemote?currentChapterId():currentChapterNum;const imgUrl=isRemote?`/api/play/remote/manga/${source}/${content_id}/${chapterArg}`:`/api/play/local/manga/${content_id}/${chapterArg}`;const imgRes=await fetch(imgUrl);if(!imgRes.ok)throw new Error('No se pudieron cargar las imágenes');const rawData=await imgRes.json();if(!rawData.length){if(chapterWrapper)chapterWrapper.innerHTML=`<div style="color:var(--muted); text-align:center; padding:20px;">
             No hay imágenes en este capítulo.
           </div>`;return;}
const imageUrls=isRemote?rawData:rawData.map(p=>`/api/manga/images/${p}`);const total=imageUrls.length;const WINDOW=2;const IMG_HEIGHT=1200;const pageHeights=new Array(total).fill(IMG_HEIGHT);let currentPage=0;let hasMarked=false;let saveTimeout=null;let rafId=null;const prefixSums=new Array(total+1).fill(0);function rebuildSums(fromIdx=0){const start=fromIdx===0?0:fromIdx;prefixSums[start]=start===0?0:prefixSums[start];for(let i=start;i<total;i++){prefixSums[i+1]=prefixSums[i]+pageHeights[i];}}
rebuildSums(0);function offsetBefore(i){return prefixSums[i];}
function getVisibleIndex(){const scrollMid=viewerDiv.scrollTop+viewerDiv.clientHeight/2;let lo=0,hi=total-1;while(lo<hi){const mid=(lo+hi)>>1;const midEnd=prefixSums[mid+1];if(midEnd<scrollMid)lo=mid+1;else hi=mid;}
return lo;}
if(chapterWrapper)chapterWrapper.innerHTML=`
        <div id="manga-viewer"
             style="width:100%; height:100%; overflow-y:auto; overflow-x:hidden;
                    background:#000; font-size:0; line-height:0;">
          ${imageUrls.map((_, i) =>
            `<div class="manga-slot"data-index="${i}"
style="width:100%;height:${IMG_HEIGHT}px;background:#0a0a0f;font-size:0;line-height:0;"></div>`
          ).join('')}
        </div>`;const viewerDiv=document.getElementById('manga-viewer');if(!viewerDiv)return;const slots=Array.from(viewerDiv.querySelectorAll('.manga-slot'));function mountImage(i){const slot=slots[i];if(slot.dataset.mounted==='1')return;slot.dataset.mounted='1';const img=document.createElement('img');img.src=imageUrls[i];img.style.cssText='width:100%; height:auto; display:block;';let settled=false;const decodeTimeout=setTimeout(()=>{if(!settled){settled=true;slot.dataset.mounted='0';}},12000);img.decode().then(()=>{settled=true;clearTimeout(decodeTimeout);if(slot.dataset.mounted!=='1')return;const MIN_PX=80;if(img.naturalWidth<MIN_PX||img.naturalHeight<MIN_PX){slot.style.height='0';slot.style.overflow='hidden';slot.dataset.mounted='0';if(pageHeights[i]!==0){pageHeights[i]=0;rebuildSums(i);}
return;}
slot.style.height='';slot.innerHTML='';const slotW=slot.offsetWidth||viewerDiv.clientWidth||800;const naturalW=img.naturalWidth;const IS_DESKTOP=window.innerWidth>=768;const fitNatural=IS_DESKTOP&&naturalW>0&&naturalW<slotW;if(fitNatural){img.style.cssText=`width:${naturalW}px; height:auto; display:block; margin:0 auto;`;}else{img.style.cssText='width:100%; height:auto; display:block;';}
slot.appendChild(img);const rendered=naturalW>0?Math.round(img.naturalHeight*(fitNatural?1:slotW/naturalW)):img.offsetHeight;if(rendered>0&&rendered!==pageHeights[i]){pageHeights[i]=rendered;rebuildSums(i);}}).catch(()=>{settled=true;clearTimeout(decodeTimeout);slot.dataset.mounted='0';});}
function unmountImage(i){const slot=slots[i];if(slot.dataset.mounted==='0')return;slot.style.height=pageHeights[i]+'px';slot.innerHTML='';slot.dataset.mounted='0';}
let prevLo=-1,prevHi=-1;let _prefetchTimers=[];function _clearPrefetch(){_prefetchTimers.forEach(t=>clearTimeout(t));_prefetchTimers=[];}
function _prefetchNextBatch(centerIdx,count=3){_clearPrefetch();const start=Math.min(centerIdx+WINDOW+1,total);const end=Math.min(start+count,total);for(let i=start;i<end;i++){const timer=setTimeout(()=>{const img=new Image();img.src=imageUrls[i];},i*200);_prefetchTimers.push(timer);}}
function updateWindow(centerIdx){const lo=Math.max(0,centerIdx-WINDOW);const hi=Math.min(total-1,centerIdx+WINDOW);if(lo===prevLo&&hi===prevHi)return;const oldLo=prevLo<0?lo:prevLo;const oldHi=prevHi<0?hi:prevHi;for(let i=oldLo;i<lo;i++)unmountImage(i);for(let i=hi+1;i<=oldHi;i++)unmountImage(i);const newLo=prevLo<0?lo:Math.min(lo,oldLo);const newHi=prevHi<0?hi:Math.max(hi,oldHi);for(let i=newLo;i<=newHi;i++){if(i>=lo&&i<=hi)mountImage(i);}
prevLo=lo;prevHi=hi;_prefetchNextBatch(centerIdx);}
function onScroll(){if(rafId)return;rafId=requestAnimationFrame(()=>{rafId=null;const idx=getVisibleIndex();if(idx!==currentPage){currentPage=idx;updateWindow(idx);}
clearTimeout(saveTimeout);saveTimeout=setTimeout(()=>{fetch(`/api/progress/manga/${source}/${content_id}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({chapter:currentChapterNum,progress:idx}),}).catch(console.error);},500);if(!hasMarked){const pct=(viewerDiv.scrollTop+viewerDiv.clientHeight)/viewerDiv.scrollHeight;if(pct>=0.90){hasMarked=true;markCurrentAsWatched();}}});}
viewerDiv.addEventListener('scroll',onScroll,{passive:true});window.addEventListener('beforeunload',()=>{clearTimeout(saveTimeout);fetch(`/api/progress/manga/${source}/${content_id}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({chapter:currentChapterNum,progress:currentPage}),}).catch(()=>{});});let savedIndex=0;try{const progUrl=isRemote?`/api/progress/manga/${source}/${content_id}`:`/api/progress/local/manga/${content_id}`;const res=await fetch(progUrl);const prog=await res.json();if(String(prog.chapter)===String(currentChapterNum)&&prog.progress){const idx=parseInt(prog.progress);if(!isNaN(idx)&&idx<total)savedIndex=idx;}}catch(e){console.warn(e);}
currentPage=savedIndex;updateWindow(savedIndex);viewerDiv.scrollTop=offsetBefore(savedIndex);}catch(err){console.error(err);if(chapterWrapper)chapterWrapper.innerHTML=`<div style="color:var(--accent2); text-align:center; padding:20px;">
           Error: ${err.message}
         </div>`;}}
async function init(){await loadChaptersList();prevBtn?.addEventListener('click',prevChapter);nextBtn?.addEventListener('click',nextChapter);backBtn?.addEventListener('click',()=>{window.location.href=`/serie/${type}/${source}/${content_id}`;});window.addEventListener('beforeunload',()=>{if(progressInterval)clearInterval(progressInterval);});showUI();}
init();})();
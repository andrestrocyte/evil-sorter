const $=id=>document.getElementById(id);
const state={catalog:null,run:null,componentIndex:0,trace:null,chunkStart:0,chartViews:{whole:null,chunk:null},fov:{scale:1,x:0,y:0,drag:false},busy:0};
const colors={F_dff:'#8129df',C:'#2c9eb4',S:'#df6a43'};

async function api(url,options={}){busy(1);try{const r=await fetch(url,options);const data=await r.json();if(!r.ok)throw new Error(data.error||r.statusText);return data}finally{busy(-1)}}
function busy(delta){state.busy+=delta;$('loading').classList.toggle('hidden',state.busy<=0)}
function toast(text){const el=$('toast');el.textContent=text;el.classList.add('show');clearTimeout(el.t);el.t=setTimeout(()=>el.classList.remove('show'),1800)}
function fmtTime(s){s=Math.max(0,Math.round(s));return `${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`}
function metric(v,d=2){return v==null?'—':Number(v).toFixed(d)}

async function init(){
  state.catalog=await api('/api/catalog');
  const groups=Object.keys(state.catalog.groups);fill($('groupSelect'),groups,g=>g,g=>g);$('excludedNote').textContent=`Excluded by registry: ${state.catalog.excluded_mice.join(', ')||'none'}`;
  $('groupSelect').onchange=populateMice;$('mouseSelect').onchange=populateSessions;$('sessionSelect').onchange=loadRun;
  populateMice();bindActions();setupFov();setupCanvas($('wholeCanvas'),'whole');setupCanvas($('chunkCanvas'),'chunk');
  await loadRun();
}
function fill(select,items,value,label){select.innerHTML='';for(const x of items){const o=document.createElement('option');o.value=value(x);o.textContent=label(x);select.append(o)}}
function populateMice(){const g=$('groupSelect').value;const mice=Object.keys(state.catalog.groups[g]||{});fill($('mouseSelect'),mice,x=>x,x=>x);populateSessions()}
function populateSessions(){const g=$('groupSelect').value,m=$('mouseSelect').value,sessions=state.catalog.groups[g]?.[m]||[];fill($('sessionSelect'),sessions,x=>x.run_id,x=>`Session ${x.session} · ${x.reviewed}/${x.n_native}`)}
async function loadRun(){const runId=$('sessionSelect').value;if(!runId)return;state.run=await api(`/api/run?run_id=${encodeURIComponent(runId)}`);let pending=state.run.components.findIndex(x=>x.decision==='pending');state.componentIndex=pending>=0?pending:0;state.chunkStart=0;state.chartViews={whole:null,chunk:null};renderCellList();updateProgress();await loadCell()}
function current(){return state.run?.components[state.componentIndex]}
function renderCellList(){const box=$('cellList');box.innerHTML='';state.run.components.forEach((c,i)=>{const b=document.createElement('button');b.className=`cell-chip ${c.decision} ${i===state.componentIndex?'active':''}`;b.textContent=c.component_id;b.title=`Component ${c.component_id}: ${c.decision}`;b.onclick=()=>{state.componentIndex=i;state.chunkStart=0;state.chartViews={whole:null,chunk:null};loadCell()};box.append(b)})}
function updateProgress(){const cs=state.run.components,k=cs.filter(x=>x.decision==='keep').length,r=cs.filter(x=>x.decision==='reject').length,p=cs.length-k-r,reviewed=k+r,pc=Math.round(reviewed/cs.length*100);$('progressText').textContent=`${reviewed} / ${cs.length} reviewed`;$('progressPercent').textContent=`${pc}%`;$('progressBar').style.width=`${pc}%`;$('keptCount').textContent=k;$('rejectCount').textContent=r;$('pendingCount').textContent=p}
async function loadCell(){
  const c=current(),row=state.run.row;if(!c)return;
  renderCellList();$('runEyebrow').textContent=`${row.group} · ${row.mouse_id} · SESSION ${row.session_id}`;$('cellTitle').textContent=`Native component ${c.component_id}`;$('runSubtitle').textContent=`${row.variant} · ${state.run.components.length} native accepted · ${fmtTime(state.run.duration_s)} total`;$('cellPosition').textContent=`${state.componentIndex+1} / ${state.run.components.length}`;
  $('metricId').textContent=c.component_id;$('metricSnr').textContent=metric(c.snr);$('metricR').textContent=metric(c.r_value);$('metricCnn').textContent=metric(c.cnn);$('metricSoma').textContent=c.soma_valid?'yes':'no';$('decisionNote').value='';
  setDecisionUI(c.decision);resetFov();$('fovImage').src=fovUrl();
  const max=Math.max(0,state.run.duration_s-state.catalog.chunk_minutes*60);$('chunkSlider').max=max;$('chunkSlider').value=state.chunkStart;
  state.trace=await api(`/api/component?run_id=${encodeURIComponent(row.run_id)}&component_id=${c.component_id}&chunk_start_s=${state.chunkStart}`);
  state.chunkStart=state.trace.chunk_start_s;state.chartViews.whole=[0,state.trace.duration_s];state.chartViews.chunk=[state.trace.chunk_start_s,state.trace.chunk_stop_s];updateChunkTitle();drawAll();
  setTimeout(prefetchNext,120);
}
function prefetchNext(){const next=state.run?.components[state.componentIndex+1];if(!next)return;const run=encodeURIComponent(state.run.row.run_id);const img=new Image();img.src=`/api/fov?run_id=${run}&component_id=${next.component_id}&background=${$('backgroundSelect').value}`;fetch(`/api/component?run_id=${run}&component_id=${next.component_id}&chunk_start_s=0`).catch(()=>{})}
function fovUrl(){return `/api/fov?run_id=${encodeURIComponent(state.run.row.run_id)}&component_id=${current().component_id}&background=${$('backgroundSelect').value}&v=${Date.now()}`}
function setDecisionUI(decision){const panel=document.querySelector('.decision-panel');panel.classList.toggle('is-keep',decision==='keep');panel.classList.toggle('is-reject',decision==='reject');$('decisionHeading').textContent=decision==='keep'?'Manually accepted':decision==='reject'?'Manually rejected':'Pending review'}
async function decide(decision){const c=current(),row=state.run.row;const out=await api('/api/decision',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({run_id:row.run_id,component_id:c.component_id,decision,note:$('decisionNote').value})});c.decision=decision;setDecisionUI(decision);renderCellList();updateProgress();await refreshCatalogFromSql();toast(`${decision==='keep'?'✓ kept':'× rejected'} · component ${c.component_id}`);if(state.catalog.auto_advance&&state.componentIndex<state.run.components.length-1){state.componentIndex++;state.chunkStart=0;state.chartViews={whole:null,chunk:null};await loadCell()}}

async function refreshCatalogFromSql(){
  const group=$('groupSelect').value,mouse=$('mouseSelect').value,runId=$('sessionSelect').value;
  state.catalog=await api('/api/catalog');
  fill($('groupSelect'),Object.keys(state.catalog.groups),x=>x,x=>x);$('groupSelect').value=group;
  fill($('mouseSelect'),Object.keys(state.catalog.groups[group]||{}),x=>x,x=>x);$('mouseSelect').value=mouse;
  const sessions=state.catalog.groups[group]?.[mouse]||[];
  fill($('sessionSelect'),sessions,x=>x.run_id,x=>`Session ${x.session} · ${x.reviewed}/${x.n_native}`);
  $('sessionSelect').value=runId;
}

function bindActions(){
  $('prevCell').onclick=()=>moveCell(-1);$('nextCell').onclick=()=>moveCell(1);$('keepButton').onclick=()=>decide('keep');$('rejectButton').onclick=()=>decide('reject');
  $('backgroundSelect').onchange=()=>{$('fovImage').src=fovUrl()};$('resetFov').onclick=resetFov;
  $('chunkSlider').onchange=()=>setChunk(Number($('chunkSlider').value));$('prevChunk').onclick=()=>setChunk(state.chunkStart-600);$('nextChunk').onclick=()=>setChunk(state.chunkStart+600);
  addEventListener('keydown',e=>{if(['INPUT','SELECT','TEXTAREA'].includes(document.activeElement.tagName))return;if(e.key==='ArrowLeft')moveCell(-1);if(e.key==='ArrowRight')moveCell(1);if(e.key.toLowerCase()==='a')decide('keep');if(e.key.toLowerCase()==='x')decide('reject')});
  addEventListener('resize',drawAll);
}
function moveCell(delta){const next=Math.max(0,Math.min(state.run.components.length-1,state.componentIndex+delta));if(next===state.componentIndex)return;state.componentIndex=next;state.chunkStart=0;state.chartViews={whole:null,chunk:null};loadCell()}
async function setChunk(start){const max=Math.max(0,state.run.duration_s-600);state.chunkStart=Math.max(0,Math.min(max,Math.round(start/600)*600));$('chunkSlider').value=state.chunkStart;const c=current(),row=state.run.row;state.trace=await api(`/api/component?run_id=${encodeURIComponent(row.run_id)}&component_id=${c.component_id}&chunk_start_s=${state.chunkStart}`);state.chartViews.chunk=[state.trace.chunk_start_s,state.trace.chunk_stop_s];updateChunkTitle();drawAll()}
function updateChunkTitle(){$('chunkTitle').textContent=`${fmtTime(state.trace?.chunk_start_s||0)}–${fmtTime(state.trace?.chunk_stop_s||600)}`}

function setupFov(){const v=$('fovViewport'),img=$('fovImage');v.addEventListener('wheel',e=>{e.preventDefault();state.fov.scale=Math.max(1,Math.min(8,state.fov.scale*(e.deltaY<0?1.18:.85)));applyFov()},{passive:false});v.onpointerdown=e=>{state.fov.drag=true;state.fov.px=e.clientX;state.fov.py=e.clientY;v.setPointerCapture(e.pointerId)};v.onpointermove=e=>{if(!state.fov.drag)return;state.fov.x+=e.clientX-state.fov.px;state.fov.y+=e.clientY-state.fov.py;state.fov.px=e.clientX;state.fov.py=e.clientY;applyFov()};v.onpointerup=()=>state.fov.drag=false;v.ondblclick=resetFov}
function applyFov(){$('fovImage').style.transform=`translate(${state.fov.x}px,${state.fov.y}px) scale(${state.fov.scale})`}
function resetFov(){state.fov={scale:1,x:0,y:0,drag:false};applyFov()}

function setupCanvas(canvas,kind){let drag=null;canvas.addEventListener('wheel',e=>{if(!state.trace)return;e.preventDefault();const rect=canvas.getBoundingClientRect(),frac=Math.max(0,Math.min(1,(e.clientX-rect.left-62)/(rect.width-78)));const view=state.chartViews[kind],span=view[1]-view[0],center=view[0]+frac*span,factor=e.deltaY<0?.72:1.38;setView(kind,center-frac*span*factor,center+(1-frac)*span*factor)},{passive:false});canvas.onpointerdown=e=>{drag={x:e.clientX,view:[...state.chartViews[kind]]};canvas.setPointerCapture(e.pointerId)};canvas.onpointermove=e=>{if(!drag)return;const span=drag.view[1]-drag.view[0],dx=(e.clientX-drag.x)/canvas.clientWidth*span;setView(kind,drag.view[0]-dx,drag.view[1]-dx)};canvas.onpointerup=()=>drag=null;canvas.ondblclick=()=>{state.chartViews[kind]=kind==='whole'?[0,state.trace.duration_s]:[state.trace.chunk_start_s,state.trace.chunk_stop_s];drawChart(canvas,kind)}}
function setView(kind,a,b){const domain=kind==='whole'?[0,state.trace.duration_s]:[state.trace.chunk_start_s,state.trace.chunk_stop_s],minSpan=Math.max(2,(domain[1]-domain[0])/500);let span=Math.max(minSpan,b-a);if(a<domain[0]){a=domain[0];b=a+span}if(b>domain[1]){b=domain[1];a=b-span}state.chartViews[kind]=[Math.max(domain[0],a),Math.min(domain[1],b)];drawChart($(kind==='whole'?'wholeCanvas':'chunkCanvas'),kind)}
function drawAll(){if(!state.trace)return;drawChart($('wholeCanvas'),'whole');drawChart($('chunkCanvas'),'chunk')}
function drawChart(canvas,kind){
  const ratio=devicePixelRatio||1,w=canvas.clientWidth,h=canvas.clientHeight;if(!w||!h)return;canvas.width=w*ratio;canvas.height=h*ratio;const x=canvas.getContext('2d');x.scale(ratio,ratio);x.clearRect(0,0,w,h);x.fillStyle='#fff';x.fillRect(0,0,w,h);
  const left=62,right=15,top=12,bottom=26,plotW=w-left-right,rowH=(h-top-bottom)/3,view=state.chartViews[kind]||[0,state.trace.duration_s],names=['F_dff','C','S'];
  x.font='10px Inter,Arial';x.textBaseline='middle';
  names.forEach((name,row)=>{const sig=state.trace.signals[name],ts=sig[kind==='whole'?'whole_t':'chunk_t'],ys=sig[kind==='whole'?'whole_y':'chunk_y'];const visible=[];for(let i=0;i<ts.length;i++)if(ts[i]>=view[0]&&ts[i]<=view[1]&&Number.isFinite(ys[i]))visible.push(ys[i]);let lo=Math.min(...visible),hi=Math.max(...visible);if(!visible.length){lo=0;hi=1}if(hi===lo){hi+=1;lo-=1}const pad=(hi-lo)*.08;lo-=pad;hi+=pad;const y0=top+row*rowH;
    x.strokeStyle='#eeeaf1';x.lineWidth=1;x.beginPath();x.moveTo(left,y0+rowH);x.lineTo(w-right,y0+rowH);x.stroke();x.fillStyle=colors[name];x.font='700 10px Inter,Arial';x.fillText(name==='S'?'S  deconv':name,9,y0+16);x.fillStyle='#938b9b';x.font='8px Inter,Arial';x.fillText(`${lo.toPrecision(3)} … ${hi.toPrecision(3)}`,9,y0+31);
    x.beginPath();let started=false;for(let i=0;i<ts.length;i++){const t=ts[i],v=ys[i];if(t<view[0]||t>view[1]||!Number.isFinite(v))continue;const px=left+(t-view[0])/(view[1]-view[0])*plotW,py=y0+5+(1-(v-lo)/(hi-lo))*(rowH-10);if(!started){x.moveTo(px,py);started=true}else x.lineTo(px,py)}x.strokeStyle=colors[name];x.globalAlpha=.9;x.lineWidth=1;x.stroke();x.globalAlpha=1;
  });
  if(kind==='whole'){const a=state.trace.chunk_start_s,b=state.trace.chunk_stop_s;x.fillStyle='rgba(185,255,72,.12)';x.fillRect(left+(a-view[0])/(view[1]-view[0])*plotW,top,(b-a)/(view[1]-view[0])*plotW,h-top-bottom);x.strokeStyle='rgba(95,145,20,.45)';x.strokeRect(left+(a-view[0])/(view[1]-view[0])*plotW,top,(b-a)/(view[1]-view[0])*plotW,h-top-bottom)}
  x.strokeStyle='#d7d1dd';x.beginPath();x.moveTo(left,h-bottom);x.lineTo(w-right,h-bottom);x.stroke();x.fillStyle='#716a78';x.font='9px Inter,Arial';x.textAlign='center';for(let i=0;i<=5;i++){const t=view[0]+i/5*(view[1]-view[0]),px=left+i/5*plotW;x.fillText(fmtTime(t),px,h-12)}x.textAlign='start';
}

init().catch(e=>{busy(-999);toast(`Error: ${e.message}`);console.error(e)});

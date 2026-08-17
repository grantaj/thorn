CSS = r"""
:root{color-scheme:light;--paper:#f7f7f4;--surface:#fff;--ink:#202421;--muted:#6d746f;--line:#d8dcd8;--strong:#aeb6b0;--accent:#285e68;--warn:#8a6b33;--cycle:#86524b;font-family:Georgia,Cambria,"Times New Roman",serif}
*{box-sizing:border-box}
html,body{margin:0;min-height:100%;background:var(--paper);color:var(--ink)}
body{font-size:16px;line-height:1.4}
button,input{font:inherit}
button:focus-visible,input:focus-visible,a:focus-visible{outline:3px solid color-mix(in srgb,var(--accent) 28%,transparent);outline-offset:2px}
a{color:var(--accent);text-underline-offset:.15em}
.shell{min-height:100vh}
.sidebar{position:sticky;top:0;z-index:20;display:grid;grid-template-columns:auto minmax(120px,1fr) minmax(150px,250px);align-items:center;gap:12px;height:auto;padding:11px clamp(12px,3vw,30px);border:0;border-bottom:1px solid var(--line);background:color-mix(in srgb,var(--paper) 94%,transparent);backdrop-filter:blur(10px)}
.brand{font:700 16px/1.2 system-ui,sans-serif;white-space:nowrap}
.manuscript{min-width:0;margin:0;overflow:hidden;color:var(--muted);font:12px/1.2 ui-monospace,monospace;text-overflow:ellipsis;white-space:nowrap}
.search-label,.result-list{display:none}
.search{width:100%;margin:0;padding:6px 8px;border:1px solid var(--strong);border-radius:5px;background:var(--surface);font:13px/1.2 system-ui,sans-serif}
.main{width:min(1180px,100%);margin:0 auto;padding:20px clamp(8px,3vw,30px) 46px}
.breadcrumb{margin:0 0 8px}
.breadcrumb button{border:0;background:transparent;padding:0;color:var(--accent);cursor:pointer;font:650 12px/1.2 system-ui,sans-serif}
.header{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;margin:0 0 10px}
.eyebrow{display:none}
h1{margin:0;font-size:clamp(24px,4vw,38px);line-height:1.08;font-weight:600;overflow-wrap:anywhere}
.lede{margin:5px 0 0;color:var(--muted);font:12px/1.35 system-ui,sans-serif}
.lede:empty{display:none}
.controls{display:flex;gap:6px;flex:0 0 auto}
.control{padding:6px 9px;border:1px solid var(--strong);border-radius:5px;background:var(--surface);color:var(--ink);cursor:pointer;font:650 12px/1.2 system-ui,sans-serif}
.control[aria-pressed=true]{background:#e8efef;border-color:#8ea9ad}
#zoom-out,#zoom-reset,#zoom-in{display:none}
.graph-box{border-block:1px solid var(--strong);background:#fbfbf8}
.scroller{overflow:visible;min-height:0;max-height:none}
#frame{width:100%!important;height:auto!important}
.canvas{position:relative;width:100%!important;min-height:280px;transform:none!important}
.edges{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;overflow:visible}
.edge{fill:none;stroke:#87918a;stroke-width:1.65}
.edge.ambiguous{stroke:var(--warn);stroke-dasharray:7 5}
.edge.unresolved{stroke:var(--warn);stroke-dasharray:2 5}
.edge.cycle{stroke:var(--cycle)}
.edge.hidden{display:none}
.node{position:absolute;height:88px;padding:10px 12px;border:1px solid #b9c0ba;border-radius:8px;background:var(--surface);text-align:left;color:var(--ink);cursor:pointer;overflow:hidden}
.node:hover{border-color:#7f8b83;box-shadow:0 2px 9px rgba(35,45,38,.08)}
.node.selected{border-color:var(--accent);box-shadow:inset 0 0 0 1px var(--accent);background:#f3f8f8}
.node.dim{opacity:.18}
.node.external{border-style:dashed;background:#f3f3ef}
.node.cycle{border-color:var(--cycle)}
.node-kind{display:block;color:var(--muted);font:700 9px/1.15 system-ui,sans-serif;text-transform:uppercase;letter-spacing:.07em}
.node-name{display:block;margin-top:4px;padding-right:14px;font:650 14px/1.2 system-ui,sans-serif;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.node-preview{display:-webkit-box;margin-top:5px;overflow:hidden;color:#535b56;font-size:12px;line-height:1.3;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.node-open{position:absolute;right:9px;top:28px;color:#87908a;font:18px/1 system-ui,sans-serif}
.cycle-dot{position:absolute;right:9px;top:9px;width:7px;height:7px;border-radius:50%;background:var(--cycle)}
.legend,.footer{display:none}
.detail{margin-top:18px;padding-top:16px;border-top:1px solid var(--line);grid-template-columns:minmax(0,1.3fr) minmax(240px,.7fr);gap:24px}
.detail[hidden]{display:none}
.detail h2{margin:0 0 8px;font-size:21px;line-height:1.2}
.statement{margin:9px 0;padding:10px 12px;border-left:3px solid #aab3ac;background:#efefeb;white-space:pre-wrap;overflow-wrap:anywhere}
.meta{color:var(--muted);font:12px/1.4 system-ui,sans-serif}
.inspector{min-width:0;padding-left:20px;border-left:1px solid var(--line)}
.support-list{list-style:none;margin:8px 0 0;padding:0;display:grid;gap:6px}
.support-list li{padding:6px 8px;border-left:3px solid #aeb7b0;background:#efefeb;font-size:13px}
.support-list li.ambiguous,.support-list li.unresolved{border-left-color:var(--warn)}
.empty{padding:56px 16px;text-align:center;color:var(--muted);font:13px/1.4 system-ui,sans-serif}
@media(max-width:680px){
  .sidebar{position:relative;grid-template-columns:auto minmax(0,1fr);gap:7px 10px;padding:10px}
  .brand{font-size:15px}
  .manuscript{max-width:none}
  .search{grid-column:1/-1}
  .main{padding:15px 6px 36px}
  .header{padding:0 4px}
  .controls{margin-top:1px}
  .node{height:82px}
  .detail{grid-template-columns:1fr}
  .inspector{padding:14px 0 0;border-left:0;border-top:1px solid var(--line)}
}
"""

JS = r"""
(()=>{'use strict';
const data=JSON.parse(document.getElementById('thorn-graph-data').textContent);
const results=new Map(data.results.map(x=>[x.id,x]));
const proof=data.proofUnits||{};
const $=id=>document.getElementById(id);
const stage=$('stage'),svg=$('edges'),detailMain=$('detail-main'),detail=detailMain.closest('.detail'),inspector=$('inspector'),back=$('back'),toggle=$('redundant'),title=$('view-title'),meta=$('view-lede'),search=$('search'),wrap=$('frame');
const H_DESKTOP=88,H_MOBILE=82,MIN_W=180,MAX_W=250,GAP_X=22,ROW_GAP=18,LEVEL_GAP=72,PAD_Y=26;
let mode='overview',active=null,suppress=true,currentNodes=[],currentEdges=[],currentClick=null,resizeTimer=null;

function el(tag,text,cls){const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n}
function sourceRef(s){return !s?'':s.startLine===s.endLine?`${s.file}:${s.startLine}`:`${s.file}:${s.startLine}-${s.endLine}`}
function sourceLine(s){const d=el('div',sourceRef(s),'meta');if(s?.uri?.startsWith('file://')){d.append(' · ');const a=el('a','source');a.href=s.uri;d.append(a)}return d}
function nodeHeight(){return window.matchMedia('(max-width:680px)').matches?H_MOBILE:H_DESKTOP}

function topology(nodes,edges){
  const order=new Map(nodes.map((n,i)=>[n.id,n.order??i])),ids=new Set(order.keys());
  const out=new Map(nodes.map(n=>[n.id,[]])),deg=new Map(nodes.map(n=>[n.id,0])),layer=new Map(nodes.map(n=>[n.id,0]));
  edges.forEach(e=>{if(ids.has(e.from)&&ids.has(e.to)){out.get(e.from).push(e.to);deg.set(e.to,deg.get(e.to)+1)}});
  const q=nodes.filter(n=>deg.get(n.id)===0).map(n=>n.id).sort((a,b)=>order.get(a)-order.get(b)),seen=new Set();
  while(q.length){
    const x=q.shift();seen.add(x);
    (out.get(x)||[]).sort((a,b)=>order.get(a)-order.get(b)).forEach(y=>{
      layer.set(y,Math.max(layer.get(y),layer.get(x)+1));deg.set(y,deg.get(y)-1);
      if(deg.get(y)===0){q.push(y);q.sort((a,b)=>order.get(a)-order.get(b))}
    });
  }
  const residual=new Set(nodes.filter(n=>!seen.has(n.id)).map(n=>n.id));
  if(residual.size){const l=Math.max(0,...layer.values())+1;[...residual].sort((a,b)=>order.get(a)-order.get(b)).forEach(id=>layer.set(id,l))}
  return{order,layer,residual};
}

function layout(nodes,edges){
  const measured=wrap.clientWidth||stage.parentElement.clientWidth||800,width=Math.max(1,measured),h=nodeHeight();
  const padX=Math.max(10,Math.min(30,width*.035));
  const usable=width-2*padX;
  let cols=Math.max(1,Math.floor((usable+GAP_X)/(MIN_W+GAP_X)));
  cols=Math.min(4,cols);
  let w=Math.min(MAX_W,(usable-GAP_X*(cols-1))/cols);
  while(cols>1&&w<MIN_W){cols-=1;w=Math.min(MAX_W,(usable-GAP_X*(cols-1))/cols)}
  const nodeW=Math.max(1,Math.min(MAX_W,(usable-GAP_X*(cols-1))/cols));
  const {order,layer,residual}=topology(nodes,edges);
  const groups=new Map();
  nodes.forEach(n=>{const l=layer.get(n.id)||0;if(!groups.has(l))groups.set(l,[]);groups.get(l).push(n)});
  groups.forEach(v=>v.sort((a,b)=>order.get(a.id)-order.get(b.id)));
  const pos=new Map();let y=PAD_Y;
  [...groups.keys()].sort((a,b)=>a-b).forEach(l=>{
    const group=groups.get(l),rows=Math.ceil(group.length/cols);
    for(let row=0;row<rows;row++){
      const items=group.slice(row*cols,(row+1)*cols);
      const rowWidth=items.length*nodeW+(items.length-1)*GAP_X;
      const startX=(width-rowWidth)/2;
      items.forEach((n,i)=>pos.set(n.id,{x:startX+i*(nodeW+GAP_X),y:y+row*(h+ROW_GAP)}));
    }
    y+=rows*h+Math.max(0,rows-1)*ROW_GAP+LEVEL_GAP;
  });
  return{pos,residual,width,height:Math.max(280,y-LEVEL_GAP+PAD_Y),nodeW,nodeH:h};
}

function marker(){
  svg.replaceChildren();
  const ns='http://www.w3.org/2000/svg',defs=document.createElementNS(ns,'defs'),m=document.createElementNS(ns,'marker'),p=document.createElementNS(ns,'path');
  m.id='arrow';m.setAttribute('markerWidth','8');m.setAttribute('markerHeight','8');m.setAttribute('refX','7');m.setAttribute('refY','3.5');m.setAttribute('orient','auto');
  p.setAttribute('d','M0,0 L7,3.5 L0,7 Z');p.setAttribute('fill','#87918a');m.append(p);defs.append(m);svg.append(defs);
}

function curve(a,b,L){
  const x1=a.x+L.nodeW/2,y1=a.y+L.nodeH,x2=b.x+L.nodeW/2,y2=b.y;
  if(y2>y1+18){const mid=(y1+y2)/2;return`M ${x1} ${y1} C ${x1} ${mid}, ${x2} ${mid}, ${x2} ${y2}`}
  const side=Math.max(18,Math.min(44,L.nodeW*.18)),bend=Math.min(L.width-12,Math.max(12,Math.max(x1,x2)+side));
  return`M ${x1} ${y1} C ${bend} ${y1+28}, ${bend} ${y2-28}, ${x2} ${y2}`;
}

function alternative(edges,e,residual){
  if(residual.has(e.from)||residual.has(e.to))return false;
  const adj=new Map();
  edges.forEach(x=>{if(x.id===e.id||residual.has(x.from)||residual.has(x.to))return;if(!adj.has(x.from))adj.set(x.from,[]);adj.get(x.from).push(x.to)});
  const q=(adj.get(e.from)||[]).map(id=>[id,1]),seen=new Set([e.from]);
  while(q.length){const [x,d]=q.shift();if(x===e.to&&d>=2)return true;if(seen.has(x))continue;seen.add(x);(adj.get(x)||[]).forEach(y=>q.push([y,d+1]))}
  return false;
}

function render(nodes,edges,click,reduce=false){
  currentNodes=nodes;currentEdges=edges;currentClick=click;
  stage.replaceChildren(svg);marker();
  const L=layout(nodes,edges);
  stage.style.height=`${L.height}px`;
  svg.setAttribute('viewBox',`0 0 ${L.width} ${L.height}`);
  const hidden=new Set(reduce?edges.filter(e=>alternative(edges,e,L.residual)).map(e=>e.id):[]);
  edges.forEach(e=>{
    const a=L.pos.get(e.from),b=L.pos.get(e.to);if(!a||!b)return;
    const p=document.createElementNS('http://www.w3.org/2000/svg','path');p.setAttribute('d',curve(a,b,L));p.setAttribute('marker-end','url(#arrow)');p.classList.add('edge');
    if(e.status==='ambiguous')p.classList.add('ambiguous');if(e.status==='unresolved')p.classList.add('unresolved');
    if(hidden.has(e.id))p.classList.add('hidden');svg.append(p);
  });
  nodes.forEach(n=>{
    const p=L.pos.get(n.id),b=el('button');b.type='button';b.className='node';b.style.left=`${p.x}px`;b.style.top=`${p.y}px`;b.style.width=`${L.nodeW}px`;b.dataset.id=n.id;
    if(n.kind==='external_result')b.classList.add('external');
    b.append(el('span',n.kind==='external_result'?n.resultKind:n.kind,'node-kind'),el('span',n.name||n.id,'node-name'));
    if(n.statement||n.text)b.append(el('span',n.statement||n.text,'node-preview'));
    if(mode==='overview'&&results.get(n.id)?.hasProof)b.append(el('span','›','node-open'));
    b.addEventListener('click',()=>click(n));stage.append(b);
  });
  applySearch();
}

function renderCurrent(){if(currentClick)render(currentNodes,currentEdges,currentClick,mode==='overview'&&suppress)}
function sourceMeta(r){meta.replaceChildren();if(r)meta.append(sourceLine(r.source))}
function clearDetail(){detail.hidden=true;detailMain.replaceChildren();inspector.replaceChildren()}
function showClaim(n){
  detail.hidden=false;
  detailMain.replaceChildren(el('h2',n.name),el('div',n.text,'statement'),sourceLine(n.source));
  inspector.replaceChildren();
  const supports=n.supports||[];
  if(supports.length){const ul=el('ul',undefined,'support-list');supports.forEach(s=>{const label=s.namedProperty||s.targetLabel||s.justification||s.kind;const li=el('li',label);li.classList.add(s.status);ul.append(li)});inspector.append(ul)}
  document.querySelectorAll('.node').forEach(x=>x.classList.toggle('selected',x.dataset.id===n.id));
}
function showExternal(n){
  const r=results.get(n.resultId);if(r?.hasProof){openProof(n.resultId);return}
  detail.hidden=false;detailMain.replaceChildren(el('h2',n.name),el('div',n.statement,'statement'),sourceLine(n.source));inspector.replaceChildren();
}
function openProof(id){
  const r=results.get(id),p=proof[id];if(!r)return;
  mode='proof';active=id;back.hidden=false;back.textContent='← Paper';toggle.hidden=true;title.textContent=r.name;sourceMeta(r);clearDetail();
  const nodes=[...(p?.externalResults||[]),...(p?.claims||[])];
  if(!nodes.length){stage.style.height='280px';stage.replaceChildren(svg,el('div','No recovered proof structure.','empty'));return}
  render(nodes,p?.edges||[],n=>n.kind==='external_result'?showExternal(n):showClaim(n),false);
  history.replaceState(null,'',`#proof:${encodeURIComponent(id)}`);
}
function openOverviewNode(n){
  const r=results.get(n.id);
  if(r?.hasProof){openProof(n.id);return}
  detail.hidden=false;detailMain.replaceChildren(el('h2',n.name),el('div',n.statement,'statement'),sourceLine(n.source));inspector.replaceChildren();
}
function overview(){
  mode='overview';active=null;back.hidden=true;toggle.hidden=false;toggle.textContent=suppress?'All edges':'Reduce edges';title.textContent='Paper';meta.textContent='';clearDetail();
  render(data.results,data.overviewEdges,openOverviewNode,suppress);
  history.replaceState(null,'',location.pathname+location.search);
}
function applySearch(){
  const q=(search.value||'').trim().toLowerCase();if(!q){document.querySelectorAll('.node').forEach(n=>n.classList.remove('dim'));return}
  document.querySelectorAll('.node').forEach(n=>{
    const id=n.dataset.id;
    const item=results.get(id)||((proof[active]?.claims||[]).find(x=>x.id===id))||((proof[active]?.externalResults||[]).find(x=>x.id===id));
    const hay=`${item?.name||''} ${item?.statement||item?.text||''} ${item?.id||''}`.toLowerCase();
    n.classList.toggle('dim',!hay.includes(q));
  });
}

back.addEventListener('click',overview);
toggle.addEventListener('click',()=>{suppress=!suppress;toggle.setAttribute('aria-pressed',String(!suppress));toggle.textContent=suppress?'All edges':'Reduce edges';renderCurrent()});
search.addEventListener('input',applySearch);
search.addEventListener('keydown',e=>{
  if(e.key!=='Enter')return;
  const q=search.value.trim().toLowerCase();if(!q)return;
  const r=data.results.find(x=>`${x.name} ${x.statement} ${x.id}`.toLowerCase().includes(q));if(r){e.preventDefault();openOverviewNode(r)}
});
window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(renderCurrent,80)});
const hash=decodeURIComponent(location.hash||'');
if(hash.startsWith('#proof:')&&results.has(hash.slice(7)))openProof(hash.slice(7));else overview();
})();
"""

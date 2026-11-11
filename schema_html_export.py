"""Build a fully self-contained, read-only HTML schema viewer."""
from __future__ import annotations
import html
import json
import shlex
import subprocess


def graphviz_layout(graph):
    """Compute a stable, relationship-aware node order for the offline HTML canvas.

    Layout is exported as metadata only; the browser owns its HTML field rows and
    routes SVG connectors again when tables are expanded, filtered or dragged.
    """
    tables = graph.get("tables", [])
    if not tables or len(tables) > 250:
        return {}
    ids = {str(t["id"]) for t in tables}
    dot = [
        "digraph schema {",
        'graph [rankdir=LR, nodesep=0.60, ranksep=1.45, splines=ortho];',
        'node [shape=box, fixedsize=true, width=3.4, height=0.9];',
    ]
    for table in tables:
        dot.append(f'T{int(table["id"])};')
    for link in graph.get("relationships", []):
        a, b = str(link.get("left_table_id")), str(link.get("right_table_id"))
        if a in ids and b in ids and a != b:
            # Only saved edges inform layout; lineage is directional.
            direction = "" if link.get("relationship_type") == "lineage" else " [dir=none]"
            dot.append(f"T{int(a)} -> T{int(b)}{direction};")
    dot.append("}")
    try:
        result = subprocess.run(
            ["dot", "-Tplain"], input="\n".join(dot),
            capture_output=True, text=True, timeout=18, check=False
        )
        if result.returncode:
            return {}
        positions = {}
        for line in result.stdout.splitlines():
            parts = shlex.split(line)
            if len(parts) >= 4 and parts[0] == "node" and parts[1].startswith("T"):
                tid = parts[1][1:]
                if tid in ids:
                    positions[tid] = [round(float(parts[2]), 3), round(float(parts[3]), 3)]
        return positions if len(positions) == len(tables) else {}
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        # Keep the offline export usable on installations without Graphviz.
        return {}


def export_html(snapshot):
    snapshot = {**snapshot, "layouts": {
        layer: graphviz_layout(graph) for layer, graph in snapshot.get("layers", {}).items()
    }}
    # Escape "<" so captured metadata cannot break out of the JSON script element.
    data = json.dumps(snapshot, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    template = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>QueryBridge · Offline Schema Map</title>
<style>
:root{font-family:system-ui,-apple-system,sans-serif;color-scheme:light;--bg:#f4f7fb;--fg:#182230;--panel:#ffffff;--panel-alt:#f8fafc;--line:#d6e0ea;--control:#ffffff;--muted:#667085;--canvas:#eff4fa;--dots:#c9d5e1;--card:#ffffff;--card-head:#e6edf5;--card-text:#182230;--field-line:#e4eaf1;--edge:#6684a8;--active:#f5d769;background:var(--bg);color:var(--fg)}
:root[data-theme="dark"]{color-scheme:dark;--bg:#101820;--fg:#e6eef5;--panel:#192633;--panel-alt:#17222d;--line:#394959;--control:#233447;--muted:#aabac8;--canvas:#111d28;--dots:#344353;--card:#223143;--card-head:#31465b;--card-text:#ffffff;--field-line:#34485b;--edge:#7ab4df;--active:#745f24}
html,body{background:var(--bg);color:var(--fg)}
:root[data-embedded="true"] body>header{display:none}
:root[data-embedded="true"] .toolbar{padding:8px 12px;gap:9px}
:root[data-embedded="true"] #viewport{height:calc(100vh - 78px)}
*{box-sizing:border-box}body{margin:0}header{padding:14px 20px;background:var(--panel);border-bottom:1px solid var(--line)}
h1{font-size:20px;margin:0 0 5px}p{margin:3px 0;color:var(--muted);font-size:12px}
.toolbar{display:flex;flex-wrap:wrap;gap:12px;align-items:end;padding:12px 20px;background:var(--panel-alt);border-bottom:1px solid var(--line)}
label{display:flex;flex-direction:column;font-size:12px;gap:4px}select,input,button{font:inherit;border:1px solid var(--line);background:var(--control);color:var(--fg);padding:7px;border-radius:6px}
button{cursor:pointer}button:hover{background:var(--card-head)}.check{flex-direction:row;align-items:center}
#stats{margin-left:auto;color:var(--muted);font-size:12px}
#viewport{height:calc(100vh - 155px);min-height:460px;overflow:hidden;position:relative;cursor:grab;touch-action:none;background-color:var(--canvas);background-image:radial-gradient(var(--dots) 1px,transparent 1px);background-size:24px 24px}
#viewport.grabbing{cursor:grabbing}#world{position:absolute;left:0;top:0;transform-origin:0 0}
#lines{position:absolute;left:0;top:0;pointer-events:none;overflow:visible}
.node{position:absolute;width:245px;background:var(--card);color:var(--card-text);border:1px solid var(--line);border-radius:9px;overflow:hidden;box-shadow:0 5px 22px #0006}
.node.external{border-color:#e9a85d}.node.unjoined{border-color:#65707b;opacity:.82}.node.selected{outline:3px solid #75c8ff}
.node header{background:var(--card-head);padding:9px 11px;border:0;cursor:move;touch-action:none;user-select:none}
.node strong{font-size:13px;overflow-wrap:anywhere;color:var(--card-text)}.node small{display:block;color:var(--muted);font-size:10px;margin-top:3px}
.fields{padding:2px 0;overflow:visible}.field{padding:7px 10px;min-height:29px;border-top:1px solid var(--field-line);font-size:11px;display:flex;justify-content:space-between;gap:6px;cursor:pointer}
.field:hover,.field.active{background:var(--active)}.field span{overflow-wrap:anywhere}.field em{color:var(--muted);font-style:normal}
.meta{color:var(--muted);font-size:11px;padding:8px}.edges{stroke:var(--edge);stroke-width:2;fill:none}.edges.lineage{stroke:#15a1b7;stroke-dasharray:6 4}.edges.active{stroke:#ffd166;stroke-width:4}.node.db{border-color:#188cb7}.node.ui{border-color:#996ed0}
#help{position:absolute;bottom:12px;left:15px;background:var(--panel);border:1px solid var(--line);padding:9px 12px;border-radius:7px;font-size:11px;color:var(--fg);pointer-events:none}
</style></head><body>
<header><h1>QueryBridge · Standalone Schema Map</h1><p id="scope-banner"></p><p>Read-only metadata snapshot · no live data access · works offline · click table headers to expand/collapse fields or drag to reposition tables, click fields to highlight recorded joins</p></header>
<div class="toolbar">
<button id="theme-toggle" type="button" aria-label="Switch colour theme" aria-pressed="false">◐ Dark mode</button>
<label>Data layer<select id="layer"><option value="source">Source dictionaries</option><option value="databricks">Databricks selections</option><option value="application">Application consumption</option><option value="combined">Databricks + Application (UI)</option><option value="lineage">End-to-end lineage</option></select></label>
<label>Application<select id="application"></select></label>
<label>Focus table<select id="focus"></select></label>
<label>Diagram view<select id="mode"><option value="overview">Overview</option><option value="detail">Detail · fields</option></select></label>
<label>Highlight field<select id="field"><option value="">None</option></select></label>
<label class="check"><input type="checkbox" id="unjoined" checked>Show unjoined</label>
<label class="check"><input type="checkbox" id="descriptions">Field descriptions</label>
<label class="check"><input type="checkbox" id="cross" checked>Cross-application links</label>
<label>Find table<input id="search" placeholder="Table name…"></label>
<button id="fit">Fit / reset</button><button id="reset-positions" type="button">Reset positions</button><button id="plus">Zoom +</button><button id="minus">Zoom −</button>
<span id="stats"></span></div>
<div id="viewport"><div id="world"><svg id="lines"></svg><div id="nodes"></div></div>
<div id="help">Drag to pan · Mouse wheel to zoom · Click any field to highlight linked fields · No network required</div></div>
<script type="application/json" id="snapshot">__GRAPH_DATA__</script>
<script>
(()=>{
"use strict";
const snapshot=JSON.parse(document.getElementById("snapshot").textContent);
const $=id=>document.getElementById(id);
const themeKey="querybridge.theme";
function storedTheme(){try{return localStorage.getItem(themeKey)}catch(_){return null}}
function setTheme(value,save=true){
 const theme=value==="dark"?"dark":"light";
 document.documentElement.dataset.theme=theme;
 $("theme-toggle").textContent=theme==="dark"?"☀ Light mode":"◐ Dark mode";
 $("theme-toggle").setAttribute("aria-pressed",String(theme==="dark"));
 if(save){try{localStorage.setItem(themeKey,theme)}catch(_){}}
}
document.documentElement.dataset.embedded=String(Boolean(snapshot.initial?.embedded));
setTheme(snapshot.initial?.theme||storedTheme()||"light",false);
$("theme-toggle").onclick=()=>setTheme(document.documentElement.dataset.theme==="dark"?"light":"dark");
window.addEventListener("message",event=>{
 if(event.data?.type!=="querybridge:set-theme")return;
 if(event.origin!==location.origin&&event.origin!=="null")return;
 setTheme(event.data.theme);
});
let graph={tables:[],relationships:[]},tables=[],links=[],byId=new Map();
$("scope-banner").textContent="Export scope: "+(snapshot.scope||"all captured layers");
for(const option of $("layer").options){option.disabled=!Object.prototype.hasOwnProperty.call(snapshot.layers,option.value)}
let zoom=1,panX=24,panY=24,selected="",opened=new Set(),rendered=[],positions=new Map();
const opt=(select,value,label)=>{const o=document.createElement("option");o.value=String(value);o.textContent=label;select.append(o)};
const fullName=t=>[t.catalog,t.schema_name,t.table_name].filter(Boolean).join(".");
const name=t=>t.table_name||fullName(t);
const connected=id=>links.some(l=>String(l.left_table_id)===id||String(l.right_table_id)===id);
const neighbors=id=>{const s=new Set([id]);for(const l of links){if(String(l.left_table_id)===id)s.add(String(l.right_table_id));if(String(l.right_table_id)===id)s.add(String(l.left_table_id))}return s};
function initialiseLayer(){
  graph=snapshot.layers[$("layer").value]||{tables:[],relationships:[]};
  tables=graph.tables||[];links=graph.relationships||[];byId=new Map(tables.map(t=>[String(t.id),t]));
  const apps=[...new Set(tables.map(t=>t.application_name).filter(Boolean))].sort();
  const previous=$("application").value;$("application").replaceChildren();
  opt($("application"),"","All applications");apps.forEach(a=>opt($("application"),a,a));
  if(tables.some(t=>!t.application_name))opt($("application"),"__unassigned__","Unassigned");
  if([...$("application").options].some(o=>o.value===previous))$("application").value=previous;
  $("focus").value="";selected="";opened=new Set();refreshFocus();draw();fit();
}
function applyTransform(){$("world").style.transform="translate("+panX+"px,"+panY+"px) scale("+zoom+")"}
function filterTables(){
 const a=$("application").value,f=$("focus").value,q=$("search").value.trim().toLowerCase();
 const base=t=>!a||(a==="__unassigned__"?!t.application_name:t.application_name===a);
 const baseIDs=new Set(tables.filter(base).map(t=>String(t.id)));
 let ids=new Set(baseIDs);
 if(a&&$("cross").checked){for(const l of links){const x=String(l.left_table_id),y=String(l.right_table_id);if(baseIDs.has(x))ids.add(y);if(baseIDs.has(y))ids.add(x)}}
 if(!$("unjoined").checked)ids=new Set([...ids].filter(connected));
 if(f){const near=neighbors(f);ids=new Set([...ids].filter(id=>near.has(id)))}
 if(q){ids=new Set([...ids].filter(id=>{const t=byId.get(id);return [name(t),fullName(t),t.application_name].join(" ").toLowerCase().includes(q)}))}
 return tables.filter(t=>ids.has(String(t.id)));
}
function refreshFocus(){
 const current=$("focus").value;const base=$("application").value;
 $("focus").replaceChildren();opt($("focus"),"","All tables");
 for(const t of tables){if(base&&!(base==="__unassigned__"?!t.application_name:t.application_name===base))continue;opt($("focus"),t.id,fullName(t))}
 if([...$("focus").options].some(o=>o.value===current))$("focus").value=current;
}
function refreshFields(items){
 const old=$("field").value;$("field").replaceChildren();opt($("field"),"","No highlighted field");
 for(const t of items)for(const f of t.fields||[])opt($("field"),f.id,name(t)+" · "+f.column_name);
 if([...$("field").options].some(o=>o.value===old))$("field").value=old;
}
function highlight(id){
 selected=String(id||"");$("field").value=selected;
 const match=links.filter(l=>String(l.left_column_id)===selected||String(l.right_column_id)===selected);
 const related=new Set(match.flatMap(l=>[String(l.left_column_id),String(l.right_column_id)]));
 if(selected)related.add(selected);
 document.querySelectorAll(".field").forEach(e=>e.classList.toggle("active",related.has(e.dataset.id)));
 document.querySelectorAll(".edges").forEach(e=>e.classList.toggle("active",match.some(l=>String(l.id)===e.dataset.id)));
}
const manualPositions=new Map();
const positionsKey="querybridge.schema.map.positions.v1";
try {
 const saved=JSON.parse(localStorage.getItem(positionsKey)||"{}");
 for(const [key,pos] of Object.entries(saved)){
   if(pos&&Number.isFinite(pos.x)&&Number.isFinite(pos.y)&&pos.x>=0&&pos.y>=0)
     manualPositions.set(key,{x:pos.x,y:pos.y});
 }
} catch(_) {}
function persistPositions(){
 try{localStorage.setItem(positionsKey,JSON.stringify(Object.fromEntries(manualPositions)))}catch(_){}
}
$("reset-positions").onclick=()=>{for(const key of [...manualPositions.keys()])
 if(key.startsWith($("layer").value+":"))manualPositions.delete(key);
 persistPositions();draw();fit();};
const CARD_WIDTH=245;
function layoutNodes(items,detail) {
 const layer=$("layer").value, graphviz=snapshot.layouts?.[layer]||{};
 const combined=layer==="combined";
 const kindRank={source:0,databricks:1,application:2};
 const graphX=[...new Set(items.map(t=>graphviz[String(t.id)]?.[0]).filter(x=>x!==undefined))].sort((a,b)=>a-b);
 const rankFor=t=>combined ? (t.layer_kind==="databricks"?0:1)
   : layer==="lineage" ? (kindRank[t.layer_kind]??0)
   : graphX.indexOf(graphviz[String(t.id)]?.[0])>=0 ? graphX.indexOf(graphviz[String(t.id)][0]) : 0;
 const columns=new Map();
 for(const t of items){
   const rank=rankFor(t),a=columns.get(rank)||[];a.push(t);columns.set(rank,a);
 }
 const nodes=[];
 [...columns].sort((a,b)=>a[0]-b[0]).forEach(([rank,group],rankIndex)=>{
   group.sort((a,b)=>(graphviz[String(b.id)]?.[1]??0)-(graphviz[String(a.id)]?.[1]??0)
     || String(a.table_name).localeCompare(String(b.table_name)));
   let y=24;
   for(const t of group){
     const expanded=detail?!opened.has(String(t.id)):opened.has(String(t.id));
     // Each row gets sufficient space for labels/types, plus the fixed header.
     const height=expanded?60+Math.max(1,(t.fields||[]).length)*($("descriptions").checked?46:29):58;
     const saved=manualPositions.get(layer+":"+t.id);
     nodes.push({t,x:saved?.x??24+rankIndex*395,y:saved?.y??y,height,expanded});
     y+=height+80;
   }
 });
 return nodes;
}
function makeSVG(tag){return document.createElementNS("http://www.w3.org/2000/svg",tag)}
function fieldAnchor(position,fieldID,onRight){
 const node=position.node;
 const row=[...node.querySelectorAll(".field")].find(el=>el.dataset.id===String(fieldID));
 let y=position.y+29;
 if(row){
   const box=row.getBoundingClientRect(),host=node.getBoundingClientRect();
   y=position.y+(box.top-host.top+box.height/2)/zoom;
 }
 return {x:position.x+(onRight?CARD_WIDTH:0),y};
}
function segmentHits(a,b,box){
 const margin=11;
 const left=box.x-margin,right=box.x+CARD_WIDTH+margin,top=box.y-margin,bottom=box.y+box.h+margin;
 if(Math.abs(a.y-b.y)<0.1){
   return a.y>top&&a.y<bottom&&Math.max(a.x,b.x)>left&&Math.min(a.x,b.x)<right;
 }
 return a.x>left&&a.x<right&&Math.max(a.y,b.y)>top&&Math.min(a.y,b.y)<bottom;
}
function clearRoute(points,excluded){
 const blocks=[...positions].filter(([id])=>!excluded.has(id)).map(([,p])=>p);
 return points.slice(1).every((p,i)=>blocks.every(b=>!segmentHits(points[i],p,b)));
}
function routedPath(link,index){
 const a=positions.get(String(link.left_table_id)),b=positions.get(String(link.right_table_id));
 if(!a||!b)return "";
 const forward=(a.x+CARD_WIDTH/2)<(b.x+CARD_WIDTH/2);
 const sign=forward?1:-1;
 const start=fieldAnchor(a,link.left_column_id,forward),end=fieldAnchor(b,link.right_column_id,!forward);
 const sa={x:start.x+sign*21,y:start.y},sb={x:end.x-sign*21,y:end.y};
 const excluded=new Set([String(link.left_table_id),String(link.right_table_id)]);
 // Graphviz ranks leave broad horizontal gutters. Try a separate vertical
 // channel for each link before falling back to a top/bottom obstacle bypass.
 const minimum=Math.min(sa.x,sb.x),maximum=Math.max(sa.x,sb.x);
 const candidates=[];
 for(let delta=0;delta<20;delta++){
   const step=(delta%2? -1:1)*Math.ceil(delta/2)*13;
   candidates.push((sa.x+sb.x)/2+step);
 }
 for(const x of candidates){
   if(x<=minimum+8||x>=maximum-8)continue;
   const route=[start,sa,{x,y:sa.y},{x,y:sb.y},sb,end];
   if(clearRoute(route,excluded))return toPath(route);
 }
 const others=[...positions].filter(([id])=>!excluded.has(id)).map(([,p])=>p);
 const upper=Math.min(start.y,end.y,...others.map(p=>p.y))-30-index%4*11;
 const lower=Math.max(start.y,end.y,...others.map(p=>p.y+p.h))+30+index%4*11;
 for(const y of [upper,lower]){
   const route=[start,sa,{x:sa.x,y},{x:sb.x,y},sb,end];
   if(clearRoute(route,excluded))return toPath(route);
 }
 // Keep the exact field ports even in the rare overcrowded case.
 return toPath([start,sa,{x:(sa.x+sb.x)/2,y:sa.y},{x:(sa.x+sb.x)/2,y:sb.y},sb,end]);
}
function toPath(points){
 const clean=points.filter((p,i)=>!i||p.x!==points[i-1].x||p.y!==points[i-1].y);
 if(clean.length<2)return "";
 let d="M"+clean[0].x+" "+clean[0].y;
 for(let i=1;i<clean.length;i++){
   const a=clean[i-1],b=clean[i],next=clean[i+1];
   if(!next){d+=" L"+b.x+" "+b.y;break}
   const length1=Math.abs(b.x-a.x)+Math.abs(b.y-a.y);
   const length2=Math.abs(next.x-b.x)+Math.abs(next.y-b.y);
   const radius=Math.min(9,length1/2,length2/2);
   if(radius<1){d+=" L"+b.x+" "+b.y;continue}
   const before={x:b.x-Math.sign(b.x-a.x)*radius,y:b.y-Math.sign(b.y-a.y)*radius};
   const after={x:b.x+Math.sign(next.x-b.x)*radius,y:b.y+Math.sign(next.y-b.y)*radius};
   d+=" L"+before.x+" "+before.y+" Q"+b.x+" "+b.y+" "+after.x+" "+after.y;
 }
 return d;
}
function drawEdges(){
 $("lines").replaceChildren();
 const defs=makeSVG("defs"),marker=makeSVG("marker"),arrow=makeSVG("path");
 marker.setAttribute("id","lineage-arrow");
 marker.setAttribute("markerWidth","9");marker.setAttribute("markerHeight","9");
 marker.setAttribute("refX","8");marker.setAttribute("refY","4");marker.setAttribute("orient","auto");
 arrow.setAttribute("d","M0 0 L8 4 L0 8");arrow.setAttribute("stroke","#15a1b7");
 arrow.setAttribute("fill","none");marker.append(arrow);defs.append(marker);$("lines").append(defs);
 const w=Math.max(300,...[...positions.values()].map(p=>p.x+CARD_WIDTH+50));
 const h=Math.max(300,...[...positions.values()].map(p=>p.y+p.h+55));
 $("world").style.width=w+"px";$("world").style.height=h+"px";
 $("lines").setAttribute("width",w);$("lines").setAttribute("height",h);
 let index=0;
 for(const link of links){
   if(!positions.has(String(link.left_table_id))||!positions.has(String(link.right_table_id)))continue;
   const path=makeSVG("path");path.classList.add("edges");
   path.dataset.id=String(link.id);
   if(link.relationship_type==="lineage"){
     path.classList.add("lineage");path.setAttribute("marker-end","url(#lineage-arrow)");
   }
   path.setAttribute("d",routedPath(link,index++));
   const tip=makeSVG("title");
   tip.textContent=(byId.get(String(link.left_table_id))?.table_name||"")+"."+link.left_field+
     (link.relationship_type==="lineage"?" → ":" = ")+
     (byId.get(String(link.right_table_id))?.table_name||"")+"."+link.right_field+
     " ("+(link.source||"recorded")+")";
   path.append(tip);$("lines").append(path);
 }
 if(selected)highlight(selected);
}
function bindTableDrag(head,node,position,tableId){
 let drag=null,suppress=false;
 head.addEventListener("pointerdown",e=>{
   if(e.button!==0)return;
   e.stopPropagation();
   drag={x:e.clientX,y:e.clientY,originalX:position.x,originalY:position.y,moved:false};
   head.setPointerCapture(e.pointerId);
 });
 head.addEventListener("pointermove",e=>{
   if(!drag)return;
   const dx=(e.clientX-drag.x)/zoom,dy=(e.clientY-drag.y)/zoom;
   if(Math.abs(dx)+Math.abs(dy)>4)drag.moved=true;
   if(!drag.moved)return;
   position.x=Math.max(0,drag.originalX+dx);position.y=Math.max(0,drag.originalY+dy);
   node.style.left=position.x+"px";node.style.top=position.y+"px";
   manualPositions.set($("layer").value+":"+tableId,{x:position.x,y:position.y});
   drawEdges();
 });
 const stop=()=>{if(drag?.moved){suppress=true;persistPositions()}drag=null};
 head.addEventListener("pointerup",stop);head.addEventListener("pointercancel",stop);
 head.addEventListener("click",e=>{
   if(suppress){suppress=false;e.preventDefault();return}
   if(opened.has(String(tableId)))opened.delete(String(tableId));
   else opened.add(String(tableId));
   draw();
 });
}
function draw(){
 const items=filterTables(),detail=$("mode").value==="detail";
 rendered=items;positions=new Map();$("nodes").replaceChildren();
 const nodes=layoutNodes(items,detail);
 for(const item of nodes){
   const {t,x,y,expanded,height}=item;
   const id=String(t.id);
   const node=document.createElement("div");
   node.className="node"+(t.layer_kind==="databricks"?" db":t.layer_kind==="application"?" ui":"")+
     (!connected(id)?" unjoined":"")+
     ($("application").value&&t.application_name!==$("application").value?" external":"");
   node.style.left=x+"px";node.style.top=y+"px";
   const head=document.createElement("header"),title=document.createElement("strong"),sub=document.createElement("small");
   title.textContent=fullName(t)||name(t);
   sub.textContent=[t.layer_kind||"source",t.application_name||"Unassigned",(t.fields||[]).length+" fields"].join(" · ");
   head.append(title,sub);head.title="Click to expand/collapse; drag to move";
   node.append(head);
   if(expanded){
     const body=document.createElement("div");body.className="fields";
     for(const f of t.fields||[]){
       const line=document.createElement("div");line.className="field";line.dataset.id=String(f.id);
       line.title=[f.column_name,f.data_type,f.description,f.comment].filter(Boolean).join(" · ");
       const a=document.createElement("span"),b=document.createElement("em");
       a.textContent=f.column_name;b.textContent=f.data_type||"";
       if($("descriptions").checked&&(f.description||f.comment)){
         const desc=document.createElement("small");desc.textContent=f.description||f.comment;
         a.append(desc);
       }
       line.append(a,b);line.onclick=()=>highlight(String(f.id));body.append(line);
     }
     if(!(t.fields||[]).length){
       const empty=document.createElement("div");empty.className="meta";
       empty.textContent="No captured fields";body.append(empty);
     }
     node.append(body);
   }
   $("nodes").append(node);
   const position={x,y,h:Math.max(height,node.offsetHeight),expanded,node};
   positions.set(id,position);
   bindTableDrag(head,node,position,id);
 }
 // Reconcile estimated row heights with actual rendered HTML (long names,
 // descriptions and wrapping can make cards taller than the metadata estimate).
 const bottoms=new Map();
 for(const item of nodes){
   const p=positions.get(String(item.t.id)),column=Math.round(p.x);
   const manual=manualPositions.has($("layer").value+":"+item.t.id);
   if(!manual && bottoms.has(column) && p.y<bottoms.get(column)+45){
     p.y=bottoms.get(column)+45;
     p.node.style.top=p.y+"px";
   }
   p.h=p.node.offsetHeight;
   bottoms.set(column,Math.max(bottoms.get(column)||0,p.y+p.h));
 }
 drawEdges();refreshFields(items);
 $("stats").textContent=items.length+" tables · "+
   links.filter(l=>positions.has(String(l.left_table_id))&&positions.has(String(l.right_table_id))).length+
   " recorded links · "+(Object.keys(snapshot.layouts?.[$("layer").value]||{}).length?"Graphviz layout":"automatic layout");
 applyTransform();
}
function fit(){const r=$("viewport").getBoundingClientRect(),w=$("world").offsetWidth,h=$("world").offsetHeight;zoom=Math.min(1.4,Math.max(.1,Math.min((r.width-40)/Math.max(w,1),(r.height-40)/Math.max(h,1))));panX=20;panY=20;applyTransform()}
function update(){refreshFocus();draw();fit()}
$("application").onchange=()=>{$("focus").value="";update()};
$("focus").onchange=draw;$("mode").onchange=draw;$("descriptions").onchange=draw;$("cross").onchange=update;$("unjoined").onchange=draw;$("search").oninput=draw;
$("field").onchange=()=>{selected=$("field").value;highlight(selected)};
$("fit").onclick=fit;
function changeZoom(f,cx,cy){const before=zoom;zoom=Math.max(.08,Math.min(4,zoom*f));panX=cx-(cx-panX)*zoom/before;panY=cy-(cy-panY)*zoom/before;applyTransform()}
$("plus").onclick=()=>changeZoom(1.25,$("viewport").clientWidth/2,$("viewport").clientHeight/2);
$("minus").onclick=()=>changeZoom(.8,$("viewport").clientWidth/2,$("viewport").clientHeight/2);
$("viewport").addEventListener("wheel",e=>{e.preventDefault();const r=e.currentTarget.getBoundingClientRect();changeZoom(e.deltaY<0?1.12:.89,e.clientX-r.left,e.clientY-r.top)},{passive:false});
let drag=null;
$("viewport").addEventListener("pointerdown",e=>{if(e.target.closest(".node"))return;drag={x:e.clientX,y:e.clientY,px:panX,py:panY};$("viewport").setPointerCapture(e.pointerId);$("viewport").classList.add("grabbing")});
$("viewport").addEventListener("pointermove",e=>{if(!drag)return;panX=drag.px+e.clientX-drag.x;panY=drag.py+e.clientY-drag.y;applyTransform()});
$("viewport").addEventListener("pointerup",()=>{drag=null;$("viewport").classList.remove("grabbing")});
$("viewport").addEventListener("pointercancel",()=>{drag=null;$("viewport").classList.remove("grabbing")});
$("layer").value=snapshot.initial?.layer||"combined";
$("layer").onchange=initialiseLayer;
initialiseLayer();
if(snapshot.initial?.application){$("application").value=snapshot.initial.application;update()}
if(snapshot.initial?.mode){$("mode").value=snapshot.initial.mode;draw();fit()}
})();
</script></body></html>'''
    return template.replace("__GRAPH_DATA__", data)

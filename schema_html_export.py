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
:root{font-family:system-ui,-apple-system,sans-serif;color-scheme:dark;background:#101820;color:#e6eef5}
*{box-sizing:border-box}body{margin:0}header{padding:14px 20px;background:#192633;border-bottom:1px solid #394959}
h1{font-size:20px;margin:0 0 5px}p{margin:3px 0;color:#aabac8;font-size:12px}
.toolbar{display:flex;flex-wrap:wrap;gap:12px;align-items:end;padding:12px 20px;background:#17222d}
label{display:flex;flex-direction:column;font-size:12px;gap:4px}select,input,button{font:inherit;border:1px solid #526578;background:#233447;color:#fff;padding:7px;border-radius:6px}
button{cursor:pointer}button:hover{background:#354b60}.check{flex-direction:row;align-items:center}
#stats{margin-left:auto;color:#bdcbd8;font-size:12px}
#viewport{height:calc(100vh - 155px);min-height:460px;overflow:hidden;position:relative;cursor:grab;touch-action:none;background-image:radial-gradient(#344353 1px,transparent 1px);background-size:24px 24px}
#viewport.grabbing{cursor:grabbing}#world{position:absolute;left:0;top:0;transform-origin:0 0}
#lines{position:absolute;left:0;top:0;pointer-events:none;overflow:visible}
.node{position:absolute;width:245px;background:#223143;border:1px solid #607489;border-radius:9px;overflow:hidden;box-shadow:0 5px 22px #0006}
.node.external{border-color:#e9a85d}.node.unjoined{border-color:#65707b;opacity:.82}.node.selected{outline:3px solid #75c8ff}
.node header{background:#31465b;padding:9px 11px;border:0;cursor:pointer}
.node strong{font-size:13px;overflow-wrap:anywhere}.node small{display:block;color:#b8c6d2;font-size:10px;margin-top:3px}
.fields{padding:2px 0;overflow:visible}.field{padding:5px 10px;border-top:1px solid #34485b;font-size:11px;display:flex;justify-content:space-between;gap:6px;cursor:pointer}
.field:hover,.field.active{background:#745f24}.field span{overflow-wrap:anywhere}.field em{color:#9eafbf;font-style:normal}
.meta{color:#c2d3e0;font-size:11px;padding:8px}.edges{stroke:#7ab4df;stroke-width:2;fill:none}.edges.active{stroke:#ffd166;stroke-width:4}.edges.lineage{stroke:#15a1b7;stroke-dasharray:6 4}.node.db{border-color:#188cb7}.node.ui{border-color:#996ed0}
#help{position:absolute;bottom:12px;left:15px;background:#14212ae8;padding:9px 12px;border-radius:7px;font-size:11px;color:#c7d6e2;pointer-events:none}
</style></head><body>
<header><h1>QueryBridge · Standalone Schema Map</h1><p id="scope-banner"></p><p>Read-only metadata snapshot · no live data access · works offline · click table headers to expand/collapse fields, click fields to highlight recorded joins</p></header>
<div class="toolbar">
<label>Data layer<select id="layer"><option value="source">Source dictionaries</option><option value="databricks">Databricks selections</option><option value="application">Application consumption</option><option value="combined">Databricks + Application (UI)</option><option value="lineage">End-to-end lineage</option></select></label>
<label>Application<select id="application"></select></label>
<label>Focus table<select id="focus"></select></label>
<label>Diagram view<select id="mode"><option value="overview">Overview</option><option value="detail">Detail · fields</option></select></label>
<label>Highlight field<select id="field"><option value="">None</option></select></label>
<label class="check"><input type="checkbox" id="unjoined" checked>Show unjoined</label>
<label class="check"><input type="checkbox" id="cross" checked>Cross-application links</label>
<label>Find table<input id="search" placeholder="Table name…"></label>
<button id="fit">Fit / reset</button><button id="plus">Zoom +</button><button id="minus">Zoom −</button>
<span id="stats"></span></div>
<div id="viewport"><div id="world"><svg id="lines"></svg><div id="nodes"></div></div>
<div id="help">Drag to pan · Mouse wheel to zoom · Click any field to highlight linked fields · No network required</div></div>
<script type="application/json" id="snapshot">__GRAPH_DATA__</script>
<script>
(()=>{
"use strict";
const snapshot=JSON.parse(document.getElementById("snapshot").textContent);
const $=id=>document.getElementById(id);
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
 document.querySelectorAll(".field").forEach(e=>e.classList.toggle("active",related.has(e.dataset.id)));
 document.querySelectorAll(".edges").forEach(e=>e.classList.toggle("active",match.some(l=>String(l.id)===e.dataset.id)));
}
function draw(){
 const items=filterTables();rendered=items;const visible=new Set(items.map(t=>String(t.id)));
 $("nodes").replaceChildren();$("lines").replaceChildren();positions=new Map();
 const defs=document.createElementNS("http://www.w3.org/2000/svg","defs");
 const marker=document.createElementNS("http://www.w3.org/2000/svg","marker");
 marker.setAttribute("id","lineage-arrow");marker.setAttribute("markerWidth","9");marker.setAttribute("markerHeight","9");
 marker.setAttribute("refX","8");marker.setAttribute("refY","4");marker.setAttribute("orient","auto");
 const arrow=document.createElementNS("http://www.w3.org/2000/svg","path");
 arrow.setAttribute("d","M0 0 L8 4 L0 8");arrow.setAttribute("stroke","#15a1b7");arrow.setAttribute("fill","none");
 marker.append(arrow);defs.append(marker);$("lines").append(defs);
 const detail=$("mode").value==="detail";
 const combined=$("layer").value==="combined";
 const cols=combined?2:Math.max(1,Math.ceil(Math.sqrt(items.length/1.5)));
 const width=combined?345:280,rowHeights=[],nodes=[],starts=[];
 if(combined){
   const lanes=[items.filter(t=>t.layer_kind==="databricks"),items.filter(t=>t.layer_kind==="application")];
   let maximum=0;
   lanes.forEach((lane,col)=>{let y=0;lane.forEach(t=>{
     const expanded=detail||opened.has(String(t.id));
     const height=expanded?65+(t.fields||[]).length*29:64;
     nodes.push({t,x:col*width,y,height,expanded});
     y+=height+55;
   });maximum=Math.max(maximum,y)});
   starts.push(0);rowHeights.push(maximum);
 }else{
   items.forEach((t,i)=>{
     const expanded=detail||opened.has(String(t.id));
     const height=expanded?65+(t.fields||[]).length*29:64;
     const col=i%cols,row=Math.floor(i/cols),x=col*width;
     rowHeights[row]=Math.max(rowHeights[row]||0,height+90);
     nodes.push({t,x,row,height,expanded});
   });
   let offset=0;for(const v of rowHeights){starts.push(offset);offset+=v}
 }
 const w=cols*width,h=Math.max(300,rowHeights.reduce((a,b)=>a+b,0));
 $("world").style.width=w+"px";$("world").style.height=h+"px";
 $("lines").setAttribute("width",w);$("lines").setAttribute("height",h);
 for(const item of nodes){
 const {t,x,row,height,expanded}=item,y=item.y===undefined?starts[row]:item.y;positions.set(String(t.id),{x,y,h:height,expanded});
 const node=document.createElement("div");node.className="node"+(t.layer_kind==="databricks"?" db":t.layer_kind==="application"?" ui":"")+(!connected(String(t.id))?" unjoined":"")+($("application").value&&t.application_name!==$("application").value?" external":"");
 node.style.left=x+"px";node.style.top=y+"px";
 const head=document.createElement("header"),title=document.createElement("strong"),sub=document.createElement("small");
 title.textContent=name(t);sub.textContent=[t.application_name||"Unassigned",t.schema_name||"",t.field_count+" fields"].filter(Boolean).join(" · ");
 head.append(title,sub);head.title="Expand / collapse";head.onclick=()=>{if(opened.has(String(t.id)))opened.delete(String(t.id));else opened.add(String(t.id));draw()};
 node.append(head);
 if(expanded){const body=document.createElement("div");body.className="fields";
 for(const f of t.fields||[]){const line=document.createElement("div");line.className="field";line.dataset.id=String(f.id);line.title=[f.column_name,f.data_type,f.comment].filter(Boolean).join(" · ");
 const a=document.createElement("span"),b=document.createElement("em");a.textContent=f.column_name;b.textContent=f.data_type||"";line.append(a,b);line.onclick=()=>{selected=String(f.id);highlight(selected)};body.append(line)}
 if(!(t.fields||[]).length){const empty=document.createElement("div");empty.className="meta";empty.textContent="No captured fields";body.append(empty)}node.append(body)}
 $("nodes").append(node);
 }
 for(const l of links){
 const a=positions.get(String(l.left_table_id)),b=positions.get(String(l.right_table_id));if(!a||!b)continue;
 const anchor=(p,tid,fid,side)=>{
   const t=byId.get(String(tid)),idx=(t?.fields||[]).findIndex(f=>String(f.id)===String(fid));
   return {x:p.x+(side==="right"?245:0),y:p.y+(p.expanded&&idx>=0?65+idx*29+13:Math.min(p.h/2,40))};
 };
 const p1=anchor(a,l.left_table_id,l.left_column_id,"right");
 const p2=anchor(b,l.right_table_id,l.right_column_id,"left");
 const x1=p1.x,y1=p1.y,x2=p2.x,y2=p2.y;
 const path=document.createElementNS("http://www.w3.org/2000/svg","path");path.classList.add("edges");if(l.relationship_type==="lineage"){path.classList.add("lineage");path.setAttribute("marker-end","url(#lineage-arrow)")}path.dataset.id=String(l.id);
 const middle=(x1+x2)/2;path.setAttribute("d","M"+x1+" "+y1+" L"+middle+" "+y1+" L"+middle+" "+y2+" L"+x2+" "+y2);
 const tip=document.createElementNS("http://www.w3.org/2000/svg","title");tip.textContent=(byId.get(String(l.left_table_id))?.table_name||"")+"."+l.left_field+(l.relationship_type==="lineage"?" → ":" = ")+(byId.get(String(l.right_table_id))?.table_name||"")+"."+l.right_field+" ("+(l.source||"recorded")+")";path.append(tip);$("lines").append(path)
 }
 refreshFields(items);if(selected)highlight(selected);
 $("stats").textContent=items.length+" tables · "+links.filter(l=>visible.has(String(l.left_table_id))&&visible.has(String(l.right_table_id))).length+" recorded links";
 applyTransform();
}
function fit(){const r=$("viewport").getBoundingClientRect(),w=$("world").offsetWidth,h=$("world").offsetHeight;zoom=Math.min(1.4,Math.max(.1,Math.min((r.width-40)/Math.max(w,1),(r.height-40)/Math.max(h,1))));panX=20;panY=20;applyTransform()}
function update(){refreshFocus();draw();fit()}
$("application").onchange=()=>{$("focus").value="";update()};
$("focus").onchange=draw;$("mode").onchange=draw;$("cross").onchange=update;$("unjoined").onchange=draw;$("search").oninput=draw;
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

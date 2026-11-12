/* Selected-field Schema Explorer for Source, Databricks, Application and
   cross-layer consumption. All relationships come from saved QueryBridge metadata. */
(() => {
  "use strict";
  const byId=id=>document.getElementById(id);
  const layer=byId("explorer-layer"),app=byId("explorer-layer-application"),
    search=byId("explorer-layer-search"),panel=byId("explorer-layer-panel"),
    source=byId("explorer-source-panel"),rows=byId("explorer-layer-rows"),
    status=byId("explorer-layer-status"),summary=byId("explorer-layer-summary"),
    inspector=byId("explorer-field-inspector");
  if(!layer||!panel||!source)return;
  let graph=null,context=null,revision=0,chosenField=null;

  const elem=(tag,text,cls)=>{
    const node=document.createElement(tag);
    if(cls)node.className=cls;
    if(text!==undefined&&text!==null)node.textContent=String(text);
    return node;
  };
  const fullName=t=>[t.catalog,t.schema_name,t.table_name].filter(Boolean).join(".");
  const option=(select,value,label)=>{
    const o=elem("option",label);o.value=value;select.append(o);
  };
  const fieldIndex=()=>{
    const index=new Map();
    for(const g of [context,graph]){
      for(const t of g?.tables||[])for(const f of t.fields||[])
        index.set(String(f.id),{table:t,field:f});
    }
    return index;
  };
  const relationships=()=>{
    const byLink=new Map();
    for(const g of [context,graph])for(const rel of g?.relationships||[])
      byLink.set(String(rel.id),rel);
    return [...byLink.values()];
  };
  function related(field,index,links){
    const result=[];
    for(const rel of links){
      const from=String(rel.left_column_id),to=String(rel.right_column_id);
      if(from!==String(field.id)&&to!==String(field.id))continue;
      const incoming=to===String(field.id),other=index.get(incoming?from:to);
      if(!other)continue;
      result.push({
        label:fullName(other.table)+"."+other.field.column_name,
        direction:rel.relationship_type==="lineage"?(incoming?"From":"To"):"Join",
        type:rel.relationship_type==="lineage"?"Recorded lineage":"Mapped join",
        notes:rel.notes||"",origin:rel.source||"",
      });
    }
    return result;
  }
  function showField(t,f,links){
    inspector.hidden=false;inspector.replaceChildren();
    inspector.append(elem("h3",f.column_name),elem("p",fullName(t),"muted"));
    const dl=elem("dl");
    for(const [label,value] of [
      ["Layer",t.layer_kind||"source"],
      ["Application",t.application_name||"Unassigned"],
      ["Type",f.data_type||"Not recorded"],
      ["Description",f.description||"Not recorded"],
      ["Description provenance",f.description_source||"Not recorded"],
      ["Transformation",f.comment||"Not recorded"]
    ]){
      dl.append(elem("dt",label),elem("dd",value));
    }
    inspector.append(dl);
    inspector.append(elem("h4","Saved field relationships ("+links.length+")"));
    if(!links.length)inspector.append(elem("p","No recorded upstream mapping or join for this field.","muted"));
    for(const l of links){
      inspector.append(elem("p",l.direction+" · "+l.label+" · "+l.type+(l.notes?" · "+l.notes:""),"explorer-layer-relation"));
    }
  }
  function render(){
    rows.replaceChildren();summary.replaceChildren();inspector.hidden=true;
    if(!graph)return;
    const query=search.value.trim().toLocaleLowerCase(),index=fieldIndex(),links=relationships();
    const types=new Map(),matches=[];
    for(const t of graph.tables){
      const own=(t.fields||[]),kind=t.layer_kind||"source";
      types.set(kind,(types.get(kind)||0)+1);
      for(const f of own){
        const connected=related(f,index,links);
        const label=connected.map(x=>x.direction+" "+x.label).join(" · ");
        const keywords=[kind,t.application_name,fullName(t),f.column_name,
          f.data_type,f.comment,f.description,label].join(" ").toLocaleLowerCase();
        if(!keywords.includes(query))continue;
        matches.push({t,f,connected,label});
      }
      // An object without captured fields must still be discoverable.
      if(!own.length && [kind,t.application_name,fullName(t)].join(" ").toLocaleLowerCase().includes(query))
        matches.push({t,f:null,connected:[],label:"No selected fields"});
    }
    for(const [kind,total] of types)summary.append(elem("span",kind+" · "+total+" objects","explorer-layer-count"));
    for(const {t,f,connected,label} of matches){
      const tr=elem("tr");
      for(const value of [t.layer_kind||"source",t.application_name||"Unassigned",fullName(t)])
        tr.append(elem("td",value||"—"));
      const fieldCell=elem("td");
      if(f){
        const select=elem("button",f.column_name,"explorer-layer-field");
        select.type="button";select.setAttribute("aria-label","Inspect "+f.column_name);
        select.onclick=()=>showField(t,f,connected);
        fieldCell.append(select);
      }else fieldCell.textContent="No captured fields";
      tr.append(fieldCell,elem("td",f?.data_type||"—"),elem("td",f?.description||"—"));
      const mappings=elem("td",label||"No recorded relationship");
      mappings.title=connected.map(x=>x.type+" · "+x.label).join("\n");
      tr.append(mappings);rows.append(tr);
    }
    if(!matches.length){
      const tr=elem("tr"),td=elem("td",graph.message||
        "No fields are recorded for this layer/application. Capture application fields under Admin → Application Data Layers.",
        "catalogue-empty");
      td.colSpan=7;tr.append(td);rows.append(tr);
    }
    status.textContent=matches.length+" rows · "+graph.tables.length+" objects · "+
      graph.relationships.length+" recorded links. "+
      (layer.value==="application"?"Use Databricks + Application to view both sides of consumption mappings. ":"")+
      "No joins are inferred.";
  }
  async function fetchLayer(name,application){
    const params=new URLSearchParams({layer:name,include_unjoined:"1",include_cross_app:"1"});
    if(application)params.set("application",application);
    const url=new URL("api/schema-map?"+params,document.baseURI);
    const response=await fetch(url,{credentials:"same-origin",cache:"no-store"});
    const data=await response.json();
    if(!response.ok||!data.ok)throw Error(data.error||"Could not load selected schema layer");
    return data;
  }
  async function load(){
    const seq=++revision,currentLayer=layer.value,selected=app.value;
    if(currentLayer==="source")return;
    status.textContent="Loading "+currentLayer+" metadata…";
    try{
      // The combined graph supplies upstream Databricks field names for the
      // Application-only inspector, without adding physical objects to that view.
      const [result,extra]=await Promise.all([
        fetchLayer(currentLayer,selected),
        currentLayer==="application"?fetchLayer("combined",selected):Promise.resolve(null)
      ]);
      if(seq!==revision)return;
      graph=result;context=extra;
      const previous=app.value;
      app.replaceChildren();option(app,"","All applications");
      for(const a of result.applications||[])option(app,a,a);
      app.value=[...app.options].some(x=>x.value===previous)?previous:"";
      chosenField=null;render();
    }catch(err){
      if(seq!==revision)return;
      graph=null;context=null;rows.replaceChildren();
      status.textContent=err.message;
    }
  }
  layer.addEventListener("change",()=>{
    const isSource=layer.value==="source";
    source.hidden=!isSource;panel.hidden=isSource;
    app.value="";graph=null;context=null;++revision;
    if(!isSource)load();
  });
  app.addEventListener("change",load);
  search.addEventListener("input",render);
  // Default Source remains available without an extra API call.
  if(layer.value!=="source"){source.hidden=true;panel.hidden=false;load()}
})();
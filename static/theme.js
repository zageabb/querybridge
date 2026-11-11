/* QueryBridge theme preference, following Notes' saved light/dark pattern.
   All application pages use the same preference key. */
(() => {
  "use strict";
  const key="querybridge.theme";
  const read=()=>{try{return localStorage.getItem(key)}catch(_){return null}};
  const save=value=>{try{localStorage.setItem(key,value)}catch(_){}};
  const setTheme=(value,persist=true)=>{
    const theme=value==="dark"?"dark":"light";
    document.documentElement.dataset.theme=theme;
    document.body.classList.toggle("schema-map-dark",theme==="dark");
    if(persist)save(theme);
    const button=document.getElementById("querybridge-theme-toggle");
    if(button){
      button.textContent=theme==="dark"?"☀ Light mode":"◐ Dark mode";
      button.setAttribute("aria-pressed",String(theme==="dark"));
    }
  };
  setTheme(read()||"light",false);
  if(document.getElementById("map-theme-toggle"))return;
  const topbar=document.querySelector(".topbar");
  if(!topbar)return;
  const button=document.createElement("button");
  button.id="querybridge-theme-toggle";
  button.type="button";
  button.className="querybridge-theme-toggle";
  button.setAttribute("aria-label","Switch light or dark colour theme");
  topbar.append(button);
  button.addEventListener("click",()=>{
    setTheme(document.documentElement.dataset.theme==="dark"?"light":"dark");
  });
  setTheme(document.documentElement.dataset.theme,false);
})();
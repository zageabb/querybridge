(() => {
  "use strict";
  const el = id => document.getElementById(id);
  const select = el("dt-select"), search = el("dt-search"), header = el("dt-header");
  const body = el("dt-rows"), status = el("dt-status"), fields = el("dt-fields");
  const editor = el("dt-editor"), title = el("dt-title"), description = el("dt-description");
  const deleteButton = el("dt-delete");
  const state = {table:"",columns:[],rows:[],page:1,total:0,pageSize:50,selected:null,create:false,revision:0};
  const endpoint = path => new URL("admin/api/data-tables" + path, document.baseURI);
  function notice(message, error=false) {
    status.textContent = message;
    status.style.color = error ? "#ab2424" : "";
  }
  async function api(url, method="GET", value=null) {
    const options = {method,credentials:"same-origin",headers:{}};
    if (value !== null) {
      options.headers["Content-Type"] = "application/json";
      options.headers["X-CSRF-Token"] = window.querybridgeAdminToken;
      options.body = JSON.stringify(value);
    }
    const res = await fetch(url, options);
    const data = await res.json();
    if (!res.ok || !data.ok) throw Error(data.error || "Request failed");
    return data;
  }
  function text(node, value) { node.textContent = value == null ? "" : String(value); return node; }
  function option(name, label) {
    const item = document.createElement("option");
    item.value = name; text(item,label); return item;
  }
  function hideEditor() {
    state.selected = null; state.create = false; editor.hidden = true;
    title.textContent = "Select a record";
    description.textContent = "Choose a row to edit it or create a new record.";
    for (const row of body.children) row.setAttribute("aria-selected","false");
  }
  function inputFor(column, value) {
    const label = document.createElement("label");
    const name = column.name;
    const required = !!column.notnull && column.dflt_value == null;
    const dtype = (column.type || "TEXT").toUpperCase();
    text(label, name + (required ? " *" : "") + " (" + dtype + ")");
    if (name === "id") {
      const valueNode = document.createElement("input");
      valueNode.value = value == null ? "Automatic" : String(value);
      valueNode.disabled = true; label.append(valueNode); return label;
    }
    let control;
    if (dtype.includes("TEXT") || dtype.includes("CHAR") || dtype.includes("CLOB")) {
      control = document.createElement("textarea");
      control.rows = 2;
    } else {
      control = document.createElement("input");
      control.type = dtype.includes("INT") || dtype.includes("REAL") ||
        dtype.includes("DOUBLE") || dtype.includes("FLOAT") ? "number" : "text";
      if (control.type === "number") control.step = dtype.includes("INT") ? "1" : "any";
    }
    control.dataset.column = name;
    control.value = value == null ? "" : String(value);
    control.dataset.originalNull = String(value === null);
    control.dataset.original = value == null ? "" : String(value);
    control.dataset.required = String(required);
    if (required) control.required = true;
    label.append(control);
    if (!required) {
      const nullLabel = document.createElement("span");
      nullLabel.style.fontSize = "12px";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.dataset.nullFor = name;
      checkbox.checked = value === null;
      checkbox.addEventListener("change", () => {
        control.disabled = checkbox.checked;
        if (!checkbox.checked && value === null) control.value = "";
      });
      control.disabled = checkbox.checked;
      nullLabel.append(checkbox, document.createTextNode(" Set NULL"));
      label.append(nullLabel);
    }
    return label;
  }
  function openEditor(row=null) {
    state.create = !row; state.selected = row;
    editor.hidden = false; fields.replaceChildren();
    title.textContent = row ? "Edit record #" + row.values.id : "Create new record";
    description.textContent = row ?
      "Only changed fields are sent. Review dependent metadata before saving." :
      "Required fields are marked *. Omitted optional fields use database defaults.";
    for (const column of state.columns) {
      const value = row ? row.values[column.name] : null;
      fields.append(inputFor(column, value));
    }
    if (!row) {
      for (const control of fields.querySelectorAll("[data-column]")) {
        const col = state.columns.find(c => c.name === control.dataset.column);
        if (col && col.dflt_value != null && control.disabled) {
          const nullToggle = fields.querySelector("[data-null-for='" + control.dataset.column + "']");
          if (nullToggle) {nullToggle.checked = false; control.disabled = false;}
        }
      }
    }
    deleteButton.hidden = !row;
    for (const element of body.children) {
      element.setAttribute("aria-selected",
        String(!!row && Number(element.dataset.id) === Number(row.values.id)));
    }
  }
  function collected() {
    const result = {};
    for (const control of fields.querySelectorAll("[data-column]")) {
      const name = control.dataset.column;
      const column = state.columns.find(c => c.name === name);
      const nullable = fields.querySelector("[data-null-for='" + name + "']");
      if (nullable && nullable.checked) {
        if (state.create && column.dflt_value != null) continue;
        if (state.create || !control.dataset.originalNull || control.dataset.originalNull === "false") result[name] = null;
        continue;
      }
      const raw = control.value;
      const isInteger = (column.type || "").toUpperCase().includes("INT");
      const isNumeric = isInteger || /REAL|FLOAT|DOUBLE/.test((column.type || "").toUpperCase());
      if (state.create) {
        if (!raw && !column.notnull && column.dflt_value != null) continue;
        result[name] = isNumeric && raw !== "" ? Number(raw) : raw;
      } else if (control.dataset.originalNull === "true" || raw !== control.dataset.original) {
        result[name] = isNumeric && raw !== "" ? Number(raw) : raw;
      }
    }
    return result;
  }
  async function loadRows() {
    const revision = ++state.revision;
    if (!state.table) return;
    notice("Loading records…");
    try {
      const url = endpoint("/" + encodeURIComponent(state.table));
      url.searchParams.set("page",String(state.page));
      if (search.value.trim()) url.searchParams.set("q",search.value.trim());
      const data = await api(url);
      if (revision !== state.revision) return;
      state.columns = data.columns; state.rows = data.rows;
      state.total = data.total; state.pageSize = data.page_size;
      header.replaceChildren(); body.replaceChildren();
      for (const col of state.columns) header.append(text(document.createElement("th"),col.name));
      for (const row of data.rows) {
        const tr = document.createElement("tr");
        tr.dataset.id = String(row.values.id);
        tr.tabIndex = 0;
        tr.setAttribute("aria-selected","false");
        for (const col of state.columns) {
          const cell = document.createElement("td");
          const value = row.values[col.name];
          text(cell, value === null ? "(NULL)" : value);
          cell.title = value == null ? "NULL" : String(value);
          tr.append(cell);
        }
        tr.addEventListener("click", () => openEditor(row));
        tr.addEventListener("keydown", ev => {if (ev.key === "Enter") openEditor(row);});
        body.append(tr);
      }
      el("dt-page").textContent = "Page " + state.page + " of " +
        Math.max(1, Math.ceil(state.total / state.pageSize));
      el("dt-prev").disabled = state.page <= 1;
      el("dt-next").disabled = state.page * state.pageSize >= state.total;
      notice(state.table + " · " + state.total + " matching records · maximum " + state.pageSize + " per page.");
      hideEditor();
    } catch (err) {
      if (revision !== state.revision) return;
      notice(err.message,true);
    }
  }
  async function loadTables() {
    try {
      const data = await api(endpoint(""));
      select.replaceChildren();
      if (!data.tables.length) {
        notice("No supported local metadata tables found.",true); return;
      }
      for (const table of data.tables) select.append(option(table.name,
        table.name + " (" + table.count + ")"));
      state.table = select.value;
      await loadRows();
    } catch(err) {notice(err.message,true);}
  }
  select.addEventListener("change",() => {
    state.table = select.value; state.page=1; search.value=""; loadRows();
  });
  let delay;
  search.addEventListener("input", () => {
    clearTimeout(delay); delay=setTimeout(() => {state.page=1;loadRows();},250);
  });
  el("dt-refresh").addEventListener("click",loadRows);
  el("dt-create").addEventListener("click",() => {
    if (!state.columns.length) return;
    openEditor(null);
  });
  el("dt-prev").addEventListener("click",()=>{if(state.page>1){state.page--;loadRows();}});
  el("dt-next").addEventListener("click",()=>{
    if(state.page*state.pageSize<state.total){state.page++;loadRows();}
  });
  el("dt-cancel").addEventListener("click",hideEditor);
  editor.addEventListener("submit", async ev => {
    ev.preventDefault();
    const values = collected();
    if (!Object.keys(values).length) {notice("No changes to save.");return;}
    const id = state.selected && state.selected.values.id;
    if (!confirm((state.create ? "Create record" : "Save changes to record #" + id) +
      " in " + state.table + "?")) return;
    try {
      if (state.create) {
        await api(endpoint("/" + encodeURIComponent(state.table)),"POST",{values,confirm:true});
      } else {
        await api(endpoint("/" + encodeURIComponent(state.table) + "/" + id),
          "PATCH",{values,version:state.selected.version,confirm:true});
      }
      await loadRows();
      notice("Record saved to local QueryBridge metadata. Change recorded in Admin audit.");
    } catch(err){notice(err.message,true);}
  });
  deleteButton.addEventListener("click", async () => {
    const row=state.selected; if (!row) return;
    if (!confirm("Permanently DELETE record #" + row.values.id + " from " +
      state.table + "? This cannot be undone. Dependent records may prevent deletion.")) return;
    try {
      await api(endpoint("/" + encodeURIComponent(state.table) + "/" + row.values.id),
        "DELETE",{version:row.version,confirm:true});
      await loadRows();
      notice("Record deleted; action recorded in Admin audit.");
    } catch(err){notice(err.message,true);}
  });
  loadTables();
})();
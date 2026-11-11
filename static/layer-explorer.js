/* Read-only source / Databricks / application / lineage Schema Explorer. */
(() => {
  "use strict";
  const el = id => document.getElementById(id);
  const layer = el("explorer-layer");
  const app = el("explorer-layer-application");
  const search = el("explorer-layer-search");
  const panel = el("explorer-layer-panel");
  const source = el("explorer-source-panel");
  const rows = el("explorer-layer-rows");
  const status = el("explorer-layer-status");
  if (!layer || !panel || !source) return;
  let graph = null;
  let revision = 0;

  function td(value) {
    const cell = document.createElement("td");
    cell.textContent = value == null || value === "" ? "—" : String(value);
    return cell;
  }
  function render() {
    rows.replaceChildren();
    if (!graph) return;
    const q = search.value.trim().toLowerCase();
    const fieldIndex = new Map();
    for (const table of graph.tables) {
      for (const field of table.fields || []) {
        fieldIndex.set(field.id, {table, field});
      }
    }
    let count = 0;
    for (const table of graph.tables) {
      for (const field of table.fields || []) {
        const parents = graph.relationships.filter(r => r.right_column_id === field.id)
          .map(r => {
            const upstream = fieldIndex.get(r.left_column_id);
            return (upstream ? upstream.table.table_name : "?") + "." + r.left_field;
          });
        const joined = parents.join(" + ");
        const searchable = [
          table.layer_kind, table.application_name, table.table_name, field.column_name,
          field.data_type, field.comment, field.description, joined
        ].join(" ").toLowerCase();
        if (!searchable.includes(q)) continue;
        const tr = document.createElement("tr");
        for (const value of [
          table.layer_kind || "source", table.application_name || "Unassigned",
          [table.catalog,table.schema_name,table.table_name].filter(Boolean).join("."),
          field.column_name, field.data_type,
          field.description || "—", joined || "No recorded upstream"
        ]) tr.append(td(value));
        if (field.comment) tr.title = "Transformation: " + field.comment;
        if (field.description_source === "inherited") tr.title += " · Description inherited from upstream";
        rows.append(tr);
        count++;
      }
    }
    status.textContent = count + " fields shown · lineage is recorded metadata, not a verified SQL join.";
    if (!count) {
      const tr = document.createElement("tr");
      const cell = td("No selected fields in this view. Add mappings under Admin → Application Data Layers.");
      cell.colSpan = 7; tr.append(cell); rows.append(tr);
    }
  }
  async function load() {
    if (layer.value === "source") return;
    const sequence = ++revision;
    const params = new URLSearchParams({layer: layer.value, include_unjoined: "1"});
    if (app.value) params.set("application", app.value);
    status.textContent = "Loading layer metadata…";
    try {
      const url = new URL("api/schema-map?" + params.toString(), document.baseURI);
      const response = await fetch(url, {credentials:"same-origin",cache:"no-store"});
      const result = await response.json();
      if (!response.ok || !result.ok) throw Error(result.error || "Layer data unavailable");
      if (sequence !== revision) return;
      graph = result;
      const previous = app.value;
      app.replaceChildren();
      const all = document.createElement("option");
      all.value = ""; all.textContent = "All applications"; app.append(all);
      for (const name of result.applications || []) {
        const option = document.createElement("option");
        option.value = name; option.textContent = name; app.append(option);
      }
      app.value = previous;
      render();
    } catch (error) {
      if (sequence !== revision) return;
      status.textContent = error.message;
      rows.replaceChildren();
    }
  }
  layer.addEventListener("change", () => {
    const isSource = layer.value === "source";
    panel.hidden = isSource;
    source.hidden = !isSource;
    app.value = "";
    graph = null;
    ++revision;
    if (!isSource) load();
  });
  app.addEventListener("change", load);
  search.addEventListener("input", render);
})();

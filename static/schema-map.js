(() => {
  "use strict";
  const el = id => document.getElementById(id);
  const app = el("map-application");
  const focus = el("map-focus");
  const view = el("map-view");
  const unjoined = el("map-unjoined");
  const external = el("map-external");
  const field = el("map-field");
  const stage = el("map-stage");
  const image = el("map-image");
  const empty = el("map-empty");
  const renderer = window.SchemaMapDiagram;
  const state = {graph: null, scope: null, mermaid: "", zoom: 1, natural: 0, revision: 0, imageUrl: null};

  function elText(tag, text, className) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    node.textContent = text == null ? "" : String(text);
    return node;
  }
  function option(select, value, text) {
    const item = document.createElement("option");
    item.value = String(value);
    item.textContent = text;
    select.append(item);
  }
  function status(message, isError) {
    const target = el("map-render-status");
    target.textContent = message;
    target.className = isError ? "schema-map-error" : "";
  }
  function parameters(includeEverything, includeFocus, includeMode) {
    const args = new URLSearchParams();
    if (app.value) args.set("application", app.value);
    if (includeEverything || unjoined.checked) args.set("include_unjoined", "1");
    if (external.checked) args.set("include_cross_app", "1");
    if (includeFocus && focus.value) args.set("focus_table", focus.value);
    if (includeMode) {
      args.set("mode", view.value);
      if (field.value && view.value === "detail") args.set("highlight_field", field.value);
    }
    return args;
  }
  function endpoint(name, args) {
    return new URL("api/schema-map" + (name ? "/" + name : "") + "?" + args.toString(), document.baseURI).toString();
  }
  async function getJson(url) {
    const response = await fetch(url, {credentials: "same-origin", cache: "no-store"});
    const data = await response.json();
    if (!response.ok || !data.ok) throw Error(data.error || "Could not load schema data.");
    return data;
  }
  function fillApplications(names) {
    const previous = app.value;
    app.replaceChildren();
    option(app, "", "All applications");
    names.forEach(name => option(app, name, name));
    if (state.scope && state.scope.has_unassigned) option(app, "__unassigned__", "Unassigned");
    app.value = previous;
  }
  function fillFocus(scope) {
    const previous = focus.value;
    focus.replaceChildren();
    option(focus, "", "All tables in scope");
    scope.tables.filter(t => !t.external).forEach(t => {
      option(focus, t.id, (t.application_name || "Unassigned") + " · " + renderer.displayName(t));
    });
    focus.value = previous;
  }
  function fillFields(graph) {
    const previous = field.value;
    field.replaceChildren();
    option(field, "", "No field highlighted");
    graph.tables.forEach(t => (t.fields || []).forEach(f =>
      option(field, f.id, t.table_name + " · " + f.column_name)
    ));
    field.value = previous;
    el("map-field-label").hidden = view.value !== "detail";
  }
  function stats(graph) {
    const cards = [
      ["Tables in filter", graph.stats.in_application],
      ["Tables drawn", graph.stats.shown_tables],
      ["Joins drawn", graph.stats.shown_joins],
      ["Unjoined in filter", graph.stats.unjoined_in_application],
      ["Other applications", graph.stats.cross_application_tables],
    ];
    const root = el("map-stats");
    root.replaceChildren();
    cards.forEach(([name, count]) => {
      const card = elText("div", "");
      card.append(elText("strong", count), elText("span", name));
      root.append(card);
    });
  }
  function linkButton(text, handler, extra) {
    const button = elText("button", text, "schema-map-list-item" + (extra || ""));
    button.type = "button";
    button.addEventListener("click", handler);
    return button;
  }
  function renderLists(graph) {
    el("map-table-count").textContent = "(" + graph.tables.length + ")";
    el("map-orphan-count").textContent = "(" + graph.unjoined_tables.length + ")";
    el("map-join-count").textContent = "(" + graph.relationships.length + ")";
    const root = el("map-table-list");
    root.replaceChildren();
    const search = el("map-table-search").value.toLocaleLowerCase().trim();
    graph.tables.filter(t => (
      [t.application_name, t.catalog, t.schema_name, t.table_name]
        .filter(Boolean).join(" ").toLocaleLowerCase().includes(search)
    )).forEach(t => {
      const button = linkButton(renderer.displayName(t), () => {
        focus.value = String(t.id);
        reload().catch(showError);
      });
      button.append(elText("small",
        (t.application_name || "Unassigned") +
        (t.external ? " · linked external" : t.joined ? " · joined" : " · unjoined")));
      root.append(button);
    });
    if (!root.children.length) root.append(elText("p", "No matching tables.", "muted"));

    const unjoinedRoot = el("map-orphan-list");
    unjoinedRoot.replaceChildren();
    graph.unjoined_tables.forEach(t => unjoinedRoot.append(linkButton(
      renderer.displayName(t),
      () => {
        unjoined.checked = true;
        focus.value = String(t.id);
        reload().catch(showError);
      },
      " is-orphan"
    )));
    if (!graph.unjoined_tables.length) unjoinedRoot.append(elText("p", "No unjoined tables in this filter.", "muted"));

    const joinedRoot = el("map-joins");
    joinedRoot.replaceChildren();
    graph.relationships.forEach(link => {
      const a = graph.tables.find(t => t.id === link.left_table_id);
      const b = graph.tables.find(t => t.id === link.right_table_id);
      if (!a || !b) return;
      const button = linkButton(
        a.table_name + "." + link.left_field + " = " + b.table_name + "." + link.right_field,
        () => {
          view.value = "detail";
          field.value = String(link.left_column_id);
          // The target field remains selected only if it is part of this graph.
          reload().catch(showError);
        }
      );
      button.append(elText("small",
        (link.source || "saved") + " · " +
        Math.round(Number(link.confidence || 0) * 100) + "%" +
        (link.notes ? " · " + link.notes : "")));
      joinedRoot.append(button);
    });
    if (!joinedRoot.children.length) joinedRoot.append(elText("p", "No stored joins in the current view.", "muted"));
  }
  function showError(error) {
    status(error.message || "Could not render diagram.", true);
    empty.textContent = error.message || "Diagram unavailable.";
    empty.hidden = false;
    image.hidden = true;
  }
  function applyZoom() {
    if (!state.natural) return;
    image.style.width = Math.ceil(state.natural * state.zoom) + "px";
    image.style.maxWidth = "none";
    el("map-zoom-level").textContent = Math.round(state.zoom * 100) + "%";
  }
  function fitZoom() {
    if (!state.natural) return;
    state.zoom = Math.min(1, Math.max(0.08, (stage.clientWidth - 32) / state.natural));
    applyZoom();
  }
  function revokeImage() {
    if (state.imageUrl) URL.revokeObjectURL(state.imageUrl);
    state.imageUrl = null;
  }
  async function renderGraph(revision) {
    if (!state.graph) return;
    const parametersForRender = parameters(false, true, true);
    const url = endpoint("diagram", parametersForRender);
    status("Rendering Graphviz…", false);
    if (!state.graph.tables.length) {
      revokeImage();
      image.hidden = true;
      empty.hidden = false;
      empty.textContent = "No tables to draw. Enable 'Show all tables' to include unjoined tables.";
      status("No relationships in this filter", false);
      return;
    }
    const response = await fetch(url, {credentials: "same-origin", cache: "no-store"});
    if (!response.ok) {
      let message = "Graphviz rendering unavailable.";
      try { message = (await response.json()).error || message; } catch (_) {}
      throw Error(message);
    }
    const blob = await response.blob();
    if (revision !== state.revision) return;
    const next = URL.createObjectURL(blob);
    const previous = state.imageUrl;
    image.onload = () => {
      if (revision !== state.revision) return;
      state.natural = image.naturalWidth || 1200;
      fitZoom();
      status("Graphviz · " + state.graph.tables.length + " tables", false);
      stage.scrollTop = 0;
      stage.scrollLeft = 0;
      if (previous) URL.revokeObjectURL(previous);
    };
    image.onerror = () => showError(Error("Could not display the Graphviz SVG."));
    image.src = next;
    state.imageUrl = next;
    image.hidden = false;
    empty.hidden = true;
  }

  async function reload() {
    const revision = ++state.revision;
    status("Loading metadata…", false);
    const scope = await getJson(endpoint("", parameters(true, false, false)));
    if (revision !== state.revision) return;
    state.scope = scope;
    fillApplications(scope.applications);
    fillFocus(scope);
    const graph = await getJson(endpoint("", parameters(false, true, false)));
    if (revision !== state.revision) return;
    state.graph = graph;
    fillFields(graph);
    stats(graph);
    renderLists(graph);
    el("map-title").textContent = view.value === "detail"
      ? "Detailed table and field relationships" : "Table relationship overview";
    state.mermaid = view.value === "detail" ? renderer.detailed(graph) : renderer.overview(graph);
    el("map-source").textContent = state.mermaid;
    await renderGraph(revision);
  }
  function download(url, filename) {
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
  }
  function downloadMermaid() {
    if (!state.mermaid) return;
    const blob = new Blob([state.mermaid], {type: "text/plain;charset=utf-8"});
    const url = URL.createObjectURL(blob);
    download(url, "querybridge-schema.mmd");
    window.setTimeout(() => URL.revokeObjectURL(url), 2000);
  }
  view.addEventListener("change", () => { field.value = ""; reload().catch(showError); });
  app.addEventListener("change", () => { focus.value = ""; field.value = ""; reload().catch(showError); });
  focus.addEventListener("change", () => { field.value = ""; reload().catch(showError); });
  unjoined.addEventListener("change", () => reload().catch(showError));
  external.addEventListener("change", () => { focus.value = ""; reload().catch(showError); });
  field.addEventListener("change", () => renderGraph(++state.revision).catch(showError));
  el("map-table-search").addEventListener("input", () => state.graph && renderLists(state.graph));
  el("map-zoom-in").addEventListener("click", () => { state.zoom = Math.min(4, state.zoom * 1.25); applyZoom(); });
  el("map-zoom-out").addEventListener("click", () => { state.zoom = Math.max(0.08, state.zoom / 1.25); applyZoom(); });
  el("map-zoom-reset").addEventListener("click", fitZoom);
  el("map-reset").addEventListener("click", () => {
    app.value = ""; focus.value = ""; view.value = "overview"; field.value = "";
    unjoined.checked = false; external.checked = false;
    el("map-table-search").value = "";
    reload().catch(showError);
  });
  el("map-export-svg").addEventListener("click", () =>
    download(endpoint("diagram", parameters(false, true, true)) + "&download=1", "querybridge-schema.svg"));
  el("map-export-dot").addEventListener("click", () => {
    const args = parameters(false, true, true); args.set("format", "dot"); args.set("download", "1");
    download(endpoint("diagram", args), "querybridge-schema.dot");
  });
  el("map-export").addEventListener("click", downloadMermaid);
  el("map-copy").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(state.mermaid); status("Mermaid source copied", false); }
    catch (_) { status("Clipboard unavailable; expand source to copy manually.", true); }
  });
  reload().catch(showError);
})();

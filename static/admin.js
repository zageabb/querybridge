(() => {
  "use strict";
  const el = id => document.getElementById(id);
  const apiUrl = name => new URL("admin/api/" + name, document.baseURI).toString();
  const state = {tables: [], selected: null, details: null, editingField: null, newTable: false, targetRequest: 0};
  const tableForm = el("admin-table-form");
  const fieldForm = el("admin-field-form");
  const joinForm = el("admin-join-form");

  function textNode(tag, text, className) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    node.textContent = text == null ? "" : String(text);
    return node;
  }
  function notify(message, bad) {
    const box = el("admin-alert");
    box.hidden = false;
    box.className = "admin-alert" + (bad ? " admin-error" : "");
    box.textContent = message;
  }
  async function request(path, action, data) {
    const opts = {credentials: "same-origin"};
    if (action) {
      opts.method = "POST";
      opts.headers = {
        "Content-Type": "application/json",
        "X-CSRF-Token": window.querybridgeAdminToken
      };
      opts.body = JSON.stringify({action: action, data: data});
    }
    const response = await fetch(apiUrl(path), opts);
    let body;
    try { body = await response.json(); }
    catch (_) { throw new Error("The server returned an invalid response."); }
    if (!response.ok || !body.ok) throw new Error(body.error || "Request failed.");
    return body;
  }
  function dataFrom(form) {
    const data = {};
    new FormData(form).forEach((value, name) => { data[name] = value; });
    return data;
  }
  function fillForm(form, values, names) {
    names.forEach(name => {
      const element = form.elements.namedItem(name);
      if (element) element.value = values[name] == null ? "" : values[name];
    });
  }
  function resetForm(form) { form.reset(); }
  function countText(num) { return String(num == null ? 0 : num); }
  function tableLabel(table) {
    return [table.catalog, table.schema_name, table.table_name].filter(Boolean).join(".");
  }

  async function reloadOverview(preferredId) {
    const result = await request("overview");
    state.tables = result.tables;
    const stats = el("admin-stats");
    stats.replaceChildren();
    Object.keys(result.stats).forEach(key => {
      const card = textNode("div", "");
      card.append(textNode("strong", result.stats[key]), textNode("span", key));
      stats.append(card);
    });
    const audit = el("admin-audit");
    audit.replaceChildren();
    result.audit.forEach(item => {
      audit.append(textNode(
        "li",
        item.created_at.slice(0, 16).replace("T", " ") + " · " +
        item.action.replaceAll("_", " ") + " · " + item.entity_type + " #" + item.entity_id
      ));
    });
    if (!result.audit.length) audit.append(textNode("li", "No admin changes recorded."));
    renderTables();
    if (preferredId && state.tables.some(t => t.id === preferredId)) {
      await selectTable(preferredId);
    } else if (state.selected && state.tables.some(t => t.id === state.selected)) {
      await selectTable(state.selected);
    } else if (state.tables.length) {
      await selectTable(state.tables[0].id);
    } else {
      state.selected = null;
      startNewTable();
    }
  }

  function renderTables() {
    const search = el("admin-search").value.trim().toLocaleLowerCase();
    const items = state.tables.filter(table =>
      [table.application_name, table.catalog, table.schema_name, table.table_name]
        .filter(Boolean).join(" ").toLocaleLowerCase().includes(search)
    );
    const list = el("admin-table-list");
    list.replaceChildren();
    items.forEach(table => {
      const row = document.createElement("tr");
      if (table.id === state.selected && !state.newTable) row.className = "admin-row-selected";
      const first = document.createElement("td");
      const button = textNode("button", table.table_name, "admin-table-link");
      button.type = "button";
      button.addEventListener("click", () => selectTable(table.id).catch(showError));
      first.append(button);
      first.append(textNode("small", (table.application_name || "Unassigned") + " · " + tableLabel(table), "admin-table-path"));
      row.append(first, textNode("td", countText(table.field_count)), textNode("td", countText(table.join_count)));
      list.append(row);
    });
    if (!items.length) {
      const row = document.createElement("tr");
      const cell = textNode("td", "No matching tables.", "muted");
      cell.colSpan = 3; row.append(cell); list.append(row);
    }
    el("admin-table-count").textContent = items.length + " of " + state.tables.length + " tables shown";
  }

  function startNewTable() {
    state.newTable = true;
    state.selected = null;
    state.details = null;
    el("admin-current-title").textContent = "Add table";
    el("admin-current-path").textContent = "Create a table record in local QueryBridge metadata.";
    tableForm.hidden = false;
    resetForm(tableForm);
    el("admin-delete-table").hidden = true;
    el("admin-save-table").textContent = "Create table";
    el("admin-table-children").hidden = true;
    fieldForm.hidden = true;
    renderTables();
  }

  async function selectTable(id) {
    state.newTable = false;
    state.selected = id;
    state.editingField = null;
    const result = await request("tables/" + encodeURIComponent(id));
    if (state.selected !== id) return;
    state.details = result;
    const t = result.table;
    el("admin-current-title").textContent = t.table_name;
    el("admin-current-path").textContent = tableLabel(t);
    tableForm.hidden = false;
    fillForm(tableForm, t, ["application_name", "catalog", "schema_name", "table_name", "table_type", "description"]);
    el("admin-delete-table").hidden = false;
    el("admin-save-table").textContent = "Save table changes";
    el("admin-table-children").hidden = false;
    fieldForm.hidden = true;
    renderTables();
    renderFields();
    renderJoins();
    populateJoins();
  }

  function renderFields() {
    const fields = state.details.fields;
    el("admin-field-count").textContent = "(" + fields.length + ")";
    const list = el("admin-field-list");
    list.replaceChildren();
    fields.forEach(field => {
      const row = document.createElement("tr");
      row.append(
        textNode("td", field.ordinal_position),
        textNode("td", field.column_name),
        textNode("td", field.data_type || "—"),
        textNode("td", field.join_count)
      );
      const actions = document.createElement("td");
      const edit = textNode("button", "Edit", "secondary small");
      edit.type = "button";
      edit.addEventListener("click", () => editField(field));
      actions.append(edit);
      row.append(actions); list.append(row);
    });
    if (!fields.length) {
      const row = document.createElement("tr"), cell = textNode("td", "No fields captured yet.", "muted");
      cell.colSpan = 5; row.append(cell); list.append(row);
    }
  }

  function editField(field) {
    state.editingField = field ? field.id : null;
    fieldForm.hidden = false;
    resetForm(fieldForm);
    if (field) fillForm(fieldForm, field, ["column_name", "data_type", "nullable", "comment", "ordinal_position"]);
    el("admin-field-form-title").textContent = field ? "Edit field · " + field.column_name : "Add field";
    el("admin-delete-field").hidden = !field;
    fieldForm.scrollIntoView({block: "nearest", behavior: "smooth"});
  }
  function renderJoins() {
    const links = state.details.joins;
    el("admin-join-count").textContent = "(" + links.length + ")";
    const list = el("admin-joins");
    list.replaceChildren();
    links.forEach(link => {
      const item = document.createElement("li");
      const body = document.createElement("div");
      body.append(textNode("strong", link.left_table + "." + link.left_field +
        " = " + link.right_table + "." + link.right_field));
      body.append(textNode("small", link.source + " · confidence " +
        Math.round(Number(link.confidence) * 100) + "%" +
        (link.notes ? " · " + link.notes : ""), "admin-table-path"));
      const button = textNode("button", "Remove", "danger small");
      button.type = "button";
      button.addEventListener("click", async () => {
        if (!window.confirm("Delete this saved relationship? Queries that rely on it may change.")) return;
        await submitChange("delete_join", {id: link.id, confirm: true});
      });
      item.append(body, button); list.append(item);
    });
    if (!links.length) list.append(textNode("li", "No stored joins for this table.", "muted"));
  }

  function option(select, value, label) {
    const item = document.createElement("option");
    item.value = value;
    item.textContent = label;
    select.append(item);
  }
  async function populateTargetFields() {
    const chosen = el("admin-join-target-table").value;
    const fieldSelect = el("admin-join-target-field");
    const sequence = ++state.targetRequest;
    fieldSelect.replaceChildren();
    if (!chosen) return;
    try {
      const response = await request("tables/" + encodeURIComponent(chosen));
      if (sequence !== state.targetRequest) return;
      response.fields.forEach(f => option(fieldSelect, f.id, f.column_name));
    } catch (error) { notify(error.message, true); }
  }
  function populateJoins() {
    const left = el("admin-join-left");
    left.replaceChildren();
    state.details.fields.forEach(f => option(left, f.id, f.column_name));
    const target = el("admin-join-target-table");
    const previousValue = target.value;
    target.replaceChildren();
    state.tables.filter(t => t.id !== state.selected && t.field_count > 0).forEach(t =>
      option(target, t.id, (t.application_name || "Unassigned") + " · " + tableLabel(t))
    );
    if (state.tables.some(t => String(t.id) === previousValue && t.id !== state.selected)) {
      target.value = previousValue;
    }
    populateTargetFields();
  }

  async function submitChange(action, data) {
    try {
      const result = await request("change", action, data);
      notify("Saved: " + action.replaceAll("_", " ") + ".");
      await reloadOverview(result.table_id);
      return true;
    } catch (error) {
      notify(error.message, true);
      return false;
    }
  }
  function showError(error) { notify(error.message || "Operation failed.", true); }

  tableForm.addEventListener("submit", event => {
    event.preventDefault();
    const data = dataFrom(tableForm);
    if (!state.newTable) data.id = state.selected;
    submitChange(state.newTable ? "create_table" : "update_table", data);
  });
  el("admin-delete-table").addEventListener("click", () => {
    if (!state.details) return;
    const t = state.details.table;
    const fields = state.details.fields.length;
    const joins = state.details.joins.length;
    const confirmed = window.prompt(
      "This removes the local table, " + fields + " field(s) and " + joins +
      " join(s). Saved snapshots are not changed.\nType the exact table name to proceed:", ""
    );
    if (confirmed !== t.table_name) return;
    if (!window.confirm("Permanently remove this table from the current local schema?")) return;
    submitChange("delete_table", {id: t.id, confirm_name: confirmed, acknowledge_impact: true});
  });
  el("admin-add-table").addEventListener("click", startNewTable);
  el("admin-cancel-table").addEventListener("click", () => {
    if (state.tables.length) selectTable(state.selected || state.tables[0].id).catch(showError);
    else startNewTable();
  });

  el("admin-add-field").addEventListener("click", () => editField(null));
  el("admin-cancel-field").addEventListener("click", () => { fieldForm.hidden = true; });
  fieldForm.addEventListener("submit", event => {
    event.preventDefault();
    const data = dataFrom(fieldForm);
    if (state.editingField) data.id = state.editingField;
    else data.table_id = state.selected;
    submitChange(state.editingField ? "update_field" : "create_field", data);
  });
  el("admin-delete-field").addEventListener("click", () => {
    const field = state.details.fields.find(f => f.id === state.editingField);
    if (!field) return;
    const confirmed = window.prompt(
      "Deleting this field will also remove " + field.join_count +
      " stored join(s).\nType the exact field name:", ""
    );
    if (confirmed !== field.column_name) return;
    if (!window.confirm("Permanently remove this local field?")) return;
    submitChange("delete_field", {
      id: field.id, confirm_name: confirmed, acknowledge_impact: true
    });
  });
  el("admin-join-target-table").addEventListener("change", populateTargetFields);
  joinForm.addEventListener("submit", event => {
    event.preventDefault();
    const data = dataFrom(joinForm);
    if (!data.left_column_id || !data.right_column_id) {
      notify("Choose both fields for the relationship.", true);
      return;
    }
    submitChange("create_join", data);
  });
  el("admin-search").addEventListener("input", renderTables);
  reloadOverview().catch(showError);
})();

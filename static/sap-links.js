(() => {
  "use strict";
  const get = id => document.getElementById(id);
  const fileInput = get("sap-import-file");
  const previewButton = get("sap-import-preview");
  const applyButton = get("sap-import-apply");
  const results = get("sap-import-results");
  const status = get("sap-import-status");
  let documentToImport = null;
  let preview = null;

  function message(text, failed = false) {
    status.textContent = text;
    status.className = failed ? "schema-map-error" : "muted";
  }

  function invalidate() {
    documentToImport = null;
    preview = null;
    applyButton.disabled = true;
    results.hidden = true;
    message("");
  }

  async function post(path, body) {
    const response = await fetch(new URL("admin/api/sap-links/" + path, document.baseURI), {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": window.querybridgeAdminToken,
      },
      body: JSON.stringify(body),
    });
    let result;
    try {
      result = await response.json();
    } catch (_) {
      throw new Error("The server returned an invalid response.");
    }
    if (!response.ok || !result.ok) throw new Error(result.error || "SAP import failed.");
    return result;
  }

  function list(id, items, formatter) {
    const target = get(id);
    target.replaceChildren();
    if (!items.length) {
      const item = document.createElement("li");
      item.textContent = "None";
      target.append(item);
    }
    items.forEach(value => {
      const item = document.createElement("li");
      item.textContent = formatter(value);
      target.append(item);
    });
  }

  function display(plan) {
    get("sap-import-counts").textContent =
      plan.counts.tables_to_add + " tables, " +
      plan.counts.fields_to_add + " fields, " +
      plan.counts.links_to_add + " relationships to add.";
    list("sap-import-tables", plan.new_tables, x => x + " — SAP S/4HANA (Catalog and Schema blank)");
    list("sap-import-fields", plan.new_fields, x =>
      x.table + "." + x.field + (x.data_type ? " — " + x.data_type : " — type unspecified")
    );
    list("sap-import-links", plan.new_links, x =>
      x.left + " = " + x.right + " — " + x.reason
    );
    get("sap-import-existing").textContent =
      plan.counts.links_already_present + " relationships already exist and will be skipped. " + plan.note;
    results.hidden = false;
  }

  fileInput.addEventListener("change", invalidate);
  previewButton.addEventListener("click", async () => {
    invalidate();
    const file = fileInput.files && fileInput.files[0];
    if (!file) {
      message("Choose a SAP relationships JSON file first.", true);
      return;
    }
    if (file.size > 1024 * 1024) {
      message("The file exceeds the 1 MB import limit.", true);
      return;
    }
    previewButton.disabled = true;
    message("Checking SAP tables, fields and joins against the current subset…");
    try {
      const parsed = JSON.parse(await file.text());
      const response = await post("preview", {document: parsed});
      preview = response.preview;
      documentToImport = parsed;
      display(preview);
      const total = preview.counts.tables_to_add +
        preview.counts.fields_to_add + preview.counts.links_to_add;
      applyButton.disabled = total === 0;
      message(total ? "Review the changes below, then confirm the import." :
        "All entries already exist. No changes are needed.");
    } catch (error) {
      message(error instanceof SyntaxError ? "File is not valid JSON." : error.message, true);
    } finally {
      previewButton.disabled = false;
    }
  });

  applyButton.addEventListener("click", async () => {
    if (!documentToImport || !preview) return;
    const c = preview.counts;
    const question = "Add " + c.tables_to_add + " table(s), " + c.fields_to_add +
      " field(s), and " + c.links_to_add + " join(s) to QueryBridge's LOCAL subset?" +
      "\n\nNew tables will have no Catalog or Schema. No saved schema snapshot will be created." +
      "\n\nThis will not change SAP or Databricks.";
    if (!window.confirm(question)) return;
    applyButton.disabled = true;
    message("Importing reviewed SAP relationships…");
    try {
      const response = await post("apply", {document: documentToImport, confirm: true});
      display(response.result);
      message("Import completed. New tables and fields are available in Schema Explorer and Schema Map.");
      preview = null;
      documentToImport = null;
      applyButton.disabled = true;
    } catch (error) {
      message(error.message, true);
      // Do not retry silently; the server may have changed since preview.
      preview = null;
      documentToImport = null;
      applyButton.disabled = true;
    }
  });
})();

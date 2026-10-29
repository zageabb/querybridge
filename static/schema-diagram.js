/* QueryBridge schema graph generator; identifiers are local integer DB IDs. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.SchemaMapDiagram = api;
})(typeof globalThis === "object" ? globalThis : this, function () {
  "use strict";
  function label(value) {
    return String(value == null ? "" : value)
      .replace(/[\u0000-\u001f\u007f]/g, " ")
      .replace(/&/g, "&amp;")
      .replace(/#/g, "&#35;")
      .replace(/\\/g, "&#92;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\|/g, "&#124;")
      .replace(new RegExp(String.fromCharCode(96), "g"), "&#96;");
  }
  function id(value) {
    if (!Number.isSafeInteger(Number(value)) || Number(value) < 1) throw Error("Invalid graph ID");
    return Number(value);
  }
  function displayName(t) {
    return [t.catalog, t.schema_name, t.table_name].filter(Boolean).join(".") || "(unnamed table)";
  }
  function key(t) { return "T" + id(t.id); }
  function fieldKey(f) { return "F" + id(f.id); }

  function overview(graph) {
    const lines = ["flowchart LR"];
    const tables = graph.tables || [];
    const links = graph.relationships || [];
    tables.forEach(t => {
      const title = displayName(t);
      const app = t.application_name || "Unassigned";
      lines.push('    ' + key(t) + '["' + label(title) + ' · ' + label(app) + '"]');
      if (!t.joined) lines.push("    class " + key(t) + " orphan");
      if (t.external) lines.push("    class " + key(t) + " external");
    });
    const pairs = new Map();
    links.forEach(link => {
      const a = id(link.left_table_id), b = id(link.right_table_id);
      const pairId = [Math.min(a,b), Math.max(a,b)].join(":");
      const pair = pairs.get(pairId) || {a: Math.min(a,b), b: Math.max(a,b), count: 0};
      pair.count++;
      pairs.set(pairId, pair);
    });
    Array.from(pairs.values()).sort((x,y) => x.a-y.a || x.b-y.b).forEach(pair => {
      lines.push("    T" + pair.a + ' ---|"' + pair.count +
        (pair.count === 1 ? " join" : " joins") + '"| T' + pair.b);
    });
    lines.push("    classDef orphan fill:#f8fafc,stroke:#98a2b3,stroke-dasharray:5 4");
    lines.push("    classDef external fill:#fff7ed,stroke:#f79009");
    return lines.join("\n") + "\n";
  }

  function detailed(graph) {
    const lines = ["flowchart LR"];
    (graph.tables || []).forEach(t => {
      const title = displayName(t) + " · " + (t.application_name || "Unassigned");
      lines.push('    subgraph G' + id(t.id) + '["' + label(title) + '"]');
      lines.push("      direction TB");
      const fields = t.fields || [];
      if (!fields.length) {
        lines.push('      ' + key(t) + '["(no captured fields)"]');
      } else {
        fields.forEach(f => {
          const suffix = f.data_type ? " : " + f.data_type : "";
          lines.push('      ' + fieldKey(f) + '["' + label(f.column_name) + label(suffix) + '"]');
        });
        for (let n=1; n<fields.length; n++) {
          lines.push("      " + fieldKey(fields[n-1]) + " ~~~ " + fieldKey(fields[n]));
        }
      }
      lines.push("    end");
      if (!t.joined) lines.push("    class G" + id(t.id) + " orphan");
      if (t.external) lines.push("    class G" + id(t.id) + " external");
    });
    (graph.relationships || []).forEach(link => {
      const source = label(link.source || "saved");
      const confidence = Number.isFinite(Number(link.confidence))
        ? " · " + Math.round(Number(link.confidence)*100) + "%" : "";
      lines.push("    F" + id(link.left_column_id) + ' ---|"' +
        source + confidence + '"| F' + id(link.right_column_id));
    });
    lines.push("    classDef orphan fill:#f8fafc,stroke:#98a2b3,stroke-dasharray:5 4");
    lines.push("    classDef external fill:#fff7ed,stroke:#f79009");
    return lines.join("\n") + "\n";
  }
  return {label, displayName, overview, detailed};
});

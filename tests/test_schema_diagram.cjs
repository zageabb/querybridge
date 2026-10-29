const assert = require("node:assert/strict");
const graph = require("../static/schema-diagram.js");
const payload = {
  tables: [
    {
      id: 1, catalog: "main", schema_name: "scm", table_name: 'strange"table',
      application_name: "P6", joined: true, fields: [{id: 11, column_name: '<script>alert(1)</script>', data_type: "STRING"}],
    },
    {
      id: 2, table_name: "orders", application_name: null, joined: true,
      fields: [{id: 21, column_name: "order_id", data_type: "INT"}],
    },
    {
      id: 3, table_name: "isolated", application_name: "TAIJU", joined: false, fields: [],
    },
  ],
  relationships: [{
    id: 1, left_table_id: 1, left_column_id: 11, right_table_id: 2, right_column_id: 21,
    source: 'manual', confidence: 0.9,
  }],
};
const summary = graph.overview(payload);
const details = graph.detailed(payload);
assert.match(summary, /T1/);
assert.match(summary, /T3/);
assert.match(summary, /1 join/);
assert.match(details, /F11/);
assert.match(details, /F21/);
assert.match(details, /subgraph G1/);
assert.match(details, /class G3 orphan/);
assert.doesNotMatch(summary, /strange"table/);
assert.doesNotMatch(details, /<script>/);
assert.match(details, /&lt;script&gt;/);
assert.throws(() => graph.overview({
  tables: [{id: "x", table_name: "bad", fields: []}], relationships: [],
}), /Invalid graph ID/);
console.log("Mermaid graph generator tests passed");

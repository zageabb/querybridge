/* QueryBridge application layer editor. All writes use existing Admin CSRF protection. */
(() => {
  const root = document.getElementById('application-layers');
  if (!root) return;
  const token = window.querybridgeAdminToken;
  const status = document.getElementById('layer-status');
  const objectsBox = document.getElementById('layer-objects');
  const sourceSelect = document.getElementById('layer-source');
  const targetSelect = document.getElementById('layer-target');
  const objectSelect = document.getElementById('layer-object');
  let state = {objects: [], fields: [], lineage: [], sources: []};

  const option = (id, label) => {
    const o = document.createElement('option');
    o.value = id;
    o.textContent = label;
    return o;
  };
  const replaceOptions = (select, choices, placeholder) => {
    select.replaceChildren(option('', placeholder));
    for (const [id, label] of choices) select.append(option(String(id), label));
  };
  const api = async (path, data, method = 'POST') => {
    const response = await fetch(path, {
      method, headers: {'Content-Type':'application/json', 'X-CSRF-Token':token},
      body: JSON.stringify(data)
    });
    const result = await response.json();
    if (!response.ok || !result.ok) throw Error(result.error || 'Request failed');
    return result;
  };
  const refresh = async () => {
    const response = await fetch('admin/api/layers');
    if (!response.ok) throw Error('Could not load application layers');
    state = await response.json();
    replaceOptions(objectSelect, state.objects.map(o => [o.id,
      o.application_name + ' / ' + o.kind + ' / ' + o.object_name]), 'Choose layer object');
    replaceOptions(targetSelect, state.fields.map(f => [f.id,
      f.application_name + ' / ' + f.object_name + '.' + f.field_name]), 'Choose target field');
    const sourceChoices = [
      ...state.sources.map(s => ['source:' + s.id,
        'SOURCE ' + (s.application_name || 'Unassigned') + ' / ' + s.table_name + '.' + s.column_name]),
      ...state.fields.filter(f => f.kind === 'databricks').map(f => ['upstream:' + f.id,
        'DATABRICKS ' + f.object_name + '.' + f.field_name])
    ];
    replaceOptions(sourceSelect, sourceChoices, 'Choose source / Databricks field');
    objectsBox.replaceChildren();
    for (const obj of state.objects) {
      const div = document.createElement('div');
      div.className = 'admin-layer-object';
      const heading = document.createElement('strong');
      heading.textContent = obj.application_name + ' — ' + obj.kind + ' — ' + obj.object_name;
      div.append(heading);
      const fields = state.fields.filter(f => f.object_id === obj.id);
      const list = document.createElement('p');
      list.textContent = fields.map(f => f.field_name).join(', ') || 'No fields selected yet';
      div.append(list);
      const detail = document.createElement('ul');
      for (const f of fields) {
        const links = state.lineage.filter(l => l.target_field_id === f.id);
        if (!links.length) continue;
        const li = document.createElement('li');
        li.textContent = f.field_name + ' ← ' +
          links.map(l => l.source_column_id ?
            (l.source_application || 'Source') + '.' + l.source_table + '.' + l.source_field :
            l.upstream_object + '.' + l.upstream_field).join(' + ');
        detail.append(li);
      }
      div.append(detail);
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'secondary small';
      remove.textContent = 'Remove layer object';
      remove.addEventListener('click', async () => {
        if (!confirm('Remove this layer object, fields and mapping links? Source dictionary stays unchanged.')) return;
        try { await api('admin/api/layers/objects/' + obj.id, {}, 'DELETE'); await refresh(); }
        catch (err) { status.textContent = err.message; }
      });
      div.append(remove);
      objectsBox.append(div);
    }
  };
  const run = async (endpoint, data) => {
    try {
      status.textContent = 'Saving local metadata…';
      await api(endpoint, data);
      await refresh();
      status.textContent = 'Saved. Source system tables are unchanged.';
    } catch (err) {
      status.textContent = err.message;
    }
  };
  document.getElementById('layer-add-object').addEventListener('submit', e => {
    e.preventDefault();
    const f = new FormData(e.target);
    run('admin/api/layers/objects', Object.fromEntries(f.entries()));
  });
  document.getElementById('layer-add-field').addEventListener('submit', e => {
    e.preventDefault();
    const f = new FormData(e.target);
    run('admin/api/layers/fields', Object.fromEntries(f.entries()));
  });
  document.getElementById('layer-add-lineage').addEventListener('submit', e => {
    e.preventDefault();
    const selected = sourceSelect.value.split(':');
    if (!selected[1]) { status.textContent = 'Choose a source field'; return; }
    const data = {target_field_id: targetSelect.value};
    data[selected[0] === 'source' ? 'source_column_id' : 'upstream_field_id'] = Number(selected[1]);
    run('admin/api/layers/lineage', data);
  });
  document.getElementById('layer-import').addEventListener('click', async () => {
    try {
      const file = document.getElementById('layer-import-file').files[0];
      if (!file) throw Error('Select an application layer JSON file');
      const doc = JSON.parse(await file.text());
      const preview = await api('admin/api/layers/import?preview=1', doc);
      if (!confirm('Import ' + preview.objects + ' layer objects and ' + preview.fields +
          ' selected fields? Existing entries will be kept.')) return;
      await run('admin/api/layers/import', doc);
    } catch (err) { status.textContent = err.message; }
  });
  refresh().catch(err => { status.textContent = err.message; });
})();
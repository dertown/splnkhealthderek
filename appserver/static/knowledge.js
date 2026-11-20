/* Knowledge objects page: dashboards, apps, macros, lookup files. */
(function () {
  Health.link('home', 'executive_overview');

  var ORDER = ['In use', 'Disabled', 'Unused'];
  var DASH_COLS = [
    { key: 'app_name', label: 'App' }, { key: 'label', label: 'Title' },
    { key: 'ko_name', label: 'Name' }, { key: 'owner', label: 'Owner' },
    { key: 'sharing', label: 'Sharing' }, { key: 'last_used', label: 'Last used' },
    { key: 'views', label: 'Views' }, { key: 'users', label: 'Users' },
    { key: 'usage', label: 'Status' },
    { key: 'disable', label: '', button: disableLabel, off: alreadyOff }
  ];
  var APP_COLS = [
    { key: 'app_name', label: 'App' }, { key: 'label', label: 'Title' },
    { key: 'version', label: 'Version' }, { key: 'owner', label: 'Owner' },
    { key: 'last_used', label: 'Last used' }, { key: 'views', label: 'Views' },
    { key: 'users', label: 'Users' }, { key: 'usage', label: 'Status' },
    { key: 'disable', label: '', button: disableLabel, off: alreadyOff }
  ];
  var KO_COLS = [
    { key: 'app_name', label: 'App' }, { key: 'ko_name', label: 'Name' },
    { key: 'owner', label: 'Owner' }, { key: 'sharing', label: 'Sharing' },
    { key: 'last_used', label: 'Last used' }, { key: 'refs', label: 'Saved searches' },
    { key: 'usage', label: 'Status' },
    { key: 'disable', label: '', button: disableLabel, off: alreadyOff }
  ];
  var LOOKUP_COLS = [
    { key: 'app_name', label: 'App' }, { key: 'ko_name', label: 'Name' },
    { key: 'owner', label: 'Owner' }, { key: 'sharing', label: 'Sharing' },
    { key: 'last_used', label: 'Last used' }, { key: 'refs', label: 'Saved searches' },
    { key: 'usage', label: 'Status' }
  ];

  function usageOf(row) {
    return row.usage || 'In use';
  }

  function alreadyOff(row) {
    return usageOf(row) === 'Disabled';
  }

  function disableLabel(row) {
    return alreadyOff(row) ? 'Off' : 'Disable';
  }

  function counts(rows) {
    var tally = { 'In use': 0, Disabled: 0, Unused: 0 };
    rows.forEach(function (row) {
      var key = usageOf(row);
      tally[key] = (tally[key] || 0) + 1;
    });
    return ORDER.map(function (name) { return { usage: name, count: tally[name] || 0 }; });
  }

  function shown(rows, filter) {
    if (!filter || filter === 'all') return rows;
    return rows.filter(function (row) { return usageOf(row) === filter; });
  }

  function paint(chartId, statsId, tableId, rows, columns, filter, kind) {
    var summary = counts(rows);
    var filtered = shown(rows, filter);
    Charts.pie(document.getElementById(chartId), summary.filter(function (row) { return row.count > 0; }), 'usage', 'count', '');
    Health.stats(document.getElementById(statsId), [
      { val: rows.length, lbl: 'On system', kind: '' },
      { val: summary[0].count, lbl: 'In use', kind: 'ok' },
      { val: summary[1].count, lbl: 'Disabled', kind: summary[1].count ? 'warn' : '' },
      { val: summary[2].count, lbl: 'Unused', kind: summary[2].count ? 'bad' : '' }
    ]);
    Health.table(document.getElementById(tableId), filtered, columns, kind ? function (row, col) {
      if (col === 'disable') disable(kind, row);
    } : null);
  }

  function failAll(error) {
    ['dashTable', 'appTable', 'macroTable', 'lookupTable', 'stats'].forEach(function (id) {
      Health.fail(document.getElementById(id), error);
    });
  }

  function load() {
    var params = { tok_ko_window: document.getElementById('koWindow').value || '30d' };
    var filter = document.getElementById('koFilter').value || 'all';
    Promise.all([
      Health.query('ko_dashboards', params),
      Health.query('ko_apps', params),
      Health.query('ko_macros', params),
      Health.query('ko_lookups', params)
    ]).then(function (res) {
      var dash = res[0], apps = res[1], macros = res[2], lookups = res[3];
      function unused(rows) { return rows.filter(function (row) { return usageOf(row) === 'Unused'; }).length; }
      Health.stats(document.getElementById('stats'), [
        { val: dash.length + apps.length + macros.length + lookups.length, lbl: 'Objects on this search head', kind: '' },
        { val: unused(dash), lbl: 'Unused dashboards', kind: unused(dash) ? 'bad' : 'ok' },
        { val: unused(apps), lbl: 'Unused apps', kind: unused(apps) ? 'warn' : 'ok' },
        { val: unused(macros), lbl: 'Unused macros', kind: unused(macros) ? 'warn' : 'ok' },
        { val: unused(lookups), lbl: 'Unused lookup files', kind: unused(lookups) ? 'warn' : 'ok' }
      ]);
      paint('dashChart', 'dashStats', 'dashTable', dash, DASH_COLS, filter, 'dashboard');
      paint('appChart', 'appStats', 'appTable', apps, APP_COLS, filter, 'app');
      paint('macroChart', 'macroStats', 'macroTable', macros, KO_COLS, filter, 'macro');
      paint('lookupChart', 'lookupStats', 'lookupTable', lookups, LOOKUP_COLS, filter, null);
    }).catch(failAll);
  }

  function disable(kind, row) {
    var name = kind === 'app' ? (row.app_name || '') : (row.ko_name || '');
    var app = row.app_name || '';
    var owner = row.owner || 'nobody';
    var note = document.getElementById('koNote');
    if (!name) return;
    var ok = window.confirm('Disable this ' + kind + ': ' + name + (kind === 'app' ? '' : ' in ' + app) + '? It stays on disk. Lookup files cannot be disabled. This app and the search and launcher apps stay on.');
    if (!ok) return;
    note.textContent = 'Disabling ' + name + '.';
    Health.koDisable({
      tok_ko_kind: kind,
      tok_ko_app: app || name,
      tok_ko_name: name,
      tok_ko_owner: owner,
      tok_ko_confirm: 'yes'
    }).then(function (rows) {
      var result = (rows && rows[0]) || {};
      note.textContent = result.status === 'already off'
        ? name + ' was already disabled.'
        : 'Disabled ' + name + '. Checking again.';
      load();
    }, function (error) {
      note.textContent = String(error && error.message ? error.message : error);
    });
  }

  document.getElementById('apply').addEventListener('click', load);
  load();
})();

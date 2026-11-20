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

  var cache = { dash: [], apps: [], macros: [], lookups: [] };

  function appNames() {
    var seen = {};
    [cache.dash, cache.apps, cache.macros, cache.lookups].forEach(function (rows) {
      rows.forEach(function (row) { if (row.app_name) seen[row.app_name] = 1; });
    });
    return Object.keys(seen).sort(function (a, b) { return a.toLowerCase().localeCompare(b.toLowerCase()); });
  }

  function checkedApps() {
    var chosen = {};
    var count = 0;
    Array.prototype.forEach.call(document.querySelectorAll('#appFilterList input[type="checkbox"]'), function (box) {
      if (box.checked) { chosen[box.value] = 1; count += 1; }
    });
    return { set: chosen, count: count, total: document.querySelectorAll('#appFilterList input[type="checkbox"]').length };
  }

  function forApps(rows) {
    var pick = checkedApps();
    if (!pick.total || pick.count === pick.total) return rows;
    if (!pick.count) return [];
    return rows.filter(function (row) { return pick.set[row.app_name]; });
  }

  function updateAppButton() {
    var pick = checkedApps();
    var btn = document.getElementById('appFilterBtn');
    if (!pick.total || pick.count === pick.total) btn.textContent = 'All apps';
    else if (!pick.count) btn.textContent = 'No apps';
    else if (pick.count === 1) btn.textContent = Object.keys(pick.set)[0];
    else btn.textContent = pick.count + ' of ' + pick.total + ' apps';
  }

  function fillAppList() {
    var list = document.getElementById('appFilterList');
    var prev = {};
    var had = false;
    Array.prototype.forEach.call(list.querySelectorAll('input[type="checkbox"]'), function (box) {
      had = true;
      if (box.checked) prev[box.value] = 1;
    });
    var names = appNames();
    list.innerHTML = names.map(function (name) {
      var on = !had || !!prev[name];
      return '<label class="app-filter-item"><input type="checkbox" value="' + Health.esc(name) + '"'
        + (on ? ' checked' : '') + '> ' + Health.esc(name) + '</label>';
    }).join('') || '<p class="note">No apps in this look-back.</p>';
    filterAppList();
    updateAppButton();
  }

  function filterAppList() {
    var q = (document.getElementById('appFilterSearch').value || '').toLowerCase();
    Array.prototype.forEach.call(document.querySelectorAll('#appFilterList .app-filter-item'), function (item) {
      var name = (item.textContent || '').toLowerCase();
      item.style.display = !q || name.indexOf(q) >= 0 ? '' : 'none';
    });
  }

  function setAppChecks(on) {
    Array.prototype.forEach.call(document.querySelectorAll('#appFilterList input[type="checkbox"]'), function (box) {
      box.checked = !!on;
    });
    updateAppButton();
    paintAll();
  }

  function paint(chartId, statsId, tableId, rows, columns, filter, kind) {
    var scoped = forApps(rows);
    var summary = counts(scoped);
    var filtered = shown(scoped, filter);
    Charts.pie(document.getElementById(chartId), summary.filter(function (row) { return row.count > 0; }), 'usage', 'count', '');
    Health.stats(document.getElementById(statsId), [
      { val: scoped.length, lbl: 'On system', kind: '' },
      { val: summary[0].count, lbl: 'In use', kind: 'ok' },
      { val: summary[1].count, lbl: 'Disabled', kind: summary[1].count ? 'warn' : '' },
      { val: summary[2].count, lbl: 'Unused', kind: summary[2].count ? 'bad' : '' }
    ]);
    if (!checkedApps().count && checkedApps().total) {
      document.getElementById(tableId).innerHTML = '<p class="note">Tick at least one app, or click All.</p>';
      return;
    }
    Health.table(document.getElementById(tableId), filtered, columns, kind ? function (row, col) {
      if (col === 'disable') disable(kind, row);
    } : null);
  }

  function paintAll() {
    var filter = document.getElementById('koFilter').value || 'all';
    var dash = forApps(cache.dash), apps = forApps(cache.apps), macros = forApps(cache.macros), lookups = forApps(cache.lookups);
    function unused(rows) { return rows.filter(function (row) { return usageOf(row) === 'Unused'; }).length; }
    Health.stats(document.getElementById('stats'), [
      { val: dash.length + apps.length + macros.length + lookups.length, lbl: 'Objects on this search head', kind: '' },
      { val: unused(dash), lbl: 'Unused dashboards', kind: unused(dash) ? 'bad' : 'ok' },
      { val: unused(apps), lbl: 'Unused apps', kind: unused(apps) ? 'warn' : 'ok' },
      { val: unused(macros), lbl: 'Unused macros', kind: unused(macros) ? 'warn' : 'ok' },
      { val: unused(lookups), lbl: 'Unused lookup files', kind: unused(lookups) ? 'warn' : 'ok' }
    ]);
    paint('dashChart', 'dashStats', 'dashTable', cache.dash, DASH_COLS, filter, 'dashboard');
    paint('appChart', 'appStats', 'appTable', cache.apps, APP_COLS, filter, 'app');
    paint('macroChart', 'macroStats', 'macroTable', cache.macros, KO_COLS, filter, 'macro');
    paint('lookupChart', 'lookupStats', 'lookupTable', cache.lookups, LOOKUP_COLS, filter, null);
  }

  function failAll(error) {
    ['dashTable', 'appTable', 'macroTable', 'lookupTable', 'stats'].forEach(function (id) {
      Health.fail(document.getElementById(id), error);
    });
  }

  function load() {
    var params = { tok_ko_window: document.getElementById('koWindow').value || '30d' };
    Promise.all([
      Health.query('ko_dashboards', params),
      Health.query('ko_apps', params),
      Health.query('ko_macros', params),
      Health.query('ko_lookups', params)
    ]).then(function (res) {
      cache.dash = res[0]; cache.apps = res[1]; cache.macros = res[2]; cache.lookups = res[3];
      fillAppList();
      paintAll();
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
  document.getElementById('koFilter').addEventListener('change', paintAll);
  document.getElementById('appFilterBtn').addEventListener('click', function () {
    var menu = document.getElementById('appFilterMenu');
    var open = menu.hasAttribute('hidden');
    if (open) menu.removeAttribute('hidden'); else menu.setAttribute('hidden', '');
    document.getElementById('appFilterBtn').setAttribute('aria-expanded', open ? 'true' : 'false');
  });
  document.getElementById('appFilterAll').addEventListener('click', function () { setAppChecks(true); });
  document.getElementById('appFilterNone').addEventListener('click', function () { setAppChecks(false); });
  document.getElementById('appFilterSearch').addEventListener('input', filterAppList);
  document.getElementById('appFilterList').addEventListener('change', function () { updateAppButton(); paintAll(); });
  document.addEventListener('click', function (event) {
    var wrap = document.getElementById('appFilter');
    if (wrap && !wrap.contains(event.target)) {
      document.getElementById('appFilterMenu').setAttribute('hidden', '');
      document.getElementById('appFilterBtn').setAttribute('aria-expanded', 'false');
    }
  });
  load();
})();

/* Knowledge objects page: dashboards, apps, macros, lookup files. */
(function () {
  Health.link('home', 'executive_overview');
  Health.link('setup', 'ai_provider_setup');

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
  var picker = Health.appPicker({
    wrap: 'appFilter', button: 'appFilterBtn', menu: 'appFilterMenu',
    search: 'appFilterSearch', list: 'appFilterList', all: 'appFilterAll', none: 'appFilterNone'
  }, paintAll);

  function appNames() {
    var seen = {};
    [cache.dash, cache.apps, cache.macros, cache.lookups].forEach(function (rows) {
      rows.forEach(function (row) { if (row.app_name) seen[row.app_name] = 1; });
    });
    return Object.keys(seen);
  }

  function forApps(rows) {
    return picker ? picker.filter(rows) : rows;
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

  function loadNames() {
    Health.query('ko_app_names').then(function (rows) {
      if (picker) picker.fill((rows || []).map(function (row) { return row.app_name; }));
    }).catch(function () {});
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
      if (picker) picker.fill(appNames());
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

  function usageTally(rows) {
    var t = { total: rows.length, unused: 0, disabled: 0, inuse: 0 };
    rows.forEach(function (row) {
      var u = usageOf(row);
      if (u === 'Unused') t.unused += 1;
      else if (u === 'Disabled') t.disabled += 1;
      else t.inuse += 1;
    });
    return t;
  }

  function sampleUnused(rows, n) {
    return forApps(rows).filter(function (row) { return usageOf(row) === 'Unused'; }).slice(0, n).map(function (row) {
      return (row.app_name || '') + '/' + (row.ko_name || row.app_name || '') + ' last=' + (row.last_used || 'never')
        + (row.refs != null ? ' refs=' + row.refs : '');
    });
  }

  function cleanupFacts() {
    var dash = forApps(cache.dash), apps = forApps(cache.apps), macros = forApps(cache.macros), lookups = forApps(cache.lookups);
    var d = usageTally(dash), a = usageTally(apps), m = usageTally(macros), l = usageTally(lookups);
    var pick = picker ? picker.selected() : { count: 0, total: 0 };
    var lines = [
      'Look-back ' + (document.getElementById('koWindow').value || '30d') + '.',
      pick.count && pick.count !== pick.total ? 'Apps selected: ' + Object.keys(pick.set).slice(0, 40).join(', ') + '.' : 'Apps: all.',
      'Dashboards total ' + d.total + ' unused ' + d.unused + ' disabled ' + d.disabled + ' in-use ' + d.inuse + '.',
      'Apps total ' + a.total + ' unused ' + a.unused + ' disabled ' + a.disabled + ' in-use ' + a.inuse + '.',
      'Macros total ' + m.total + ' unused ' + m.unused + ' disabled ' + m.disabled + ' in-use ' + m.inuse + '.',
      'Lookups total ' + l.total + ' unused ' + l.unused + ' in-use ' + l.inuse + '. Lookups cannot be disabled from this app.',
      'Protected: do not disable splunk_exec_health, search, launcher, learned, splunk_monitoring_console.',
      'Unused dashboard sample: ' + (sampleUnused(cache.dash, 12).join('; ') || 'none') + '.',
      'Unused app sample: ' + (sampleUnused(cache.apps, 8).join('; ') || 'none') + '.',
      'Unused macro sample: ' + (sampleUnused(cache.macros, 12).join('; ') || 'none') + '.',
      'Unused lookup sample: ' + (sampleUnused(cache.lookups, 8).join('; ') || 'none') + '.'
    ];
    return lines.join(' ').replace(/[|"`$\r\n]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 5800);
  }

  function localSavings(d, a, m) {
    var unused = d.unused + a.unused + m.unused;
    var load = unused > 200 ? 'high' : unused > 40 ? 'medium' : unused > 0 ? 'low' : 'none';
    var pct = unused < 1 ? 0 : Math.min(25, Math.round(unused / Math.max(d.total + a.total + m.total, 1) * 40));
    return 'Local estimate only: disabling ' + unused + ' unused objects is a ' + load
      + ' knowledge-object load reduction, roughly ' + pct + '% of the listed inventory. Not a measured CPU saving.';
  }

  var asking = false;
  function askCleanup() {
    var note = document.getElementById('koCleanupNote');
    var out = document.getElementById('koCleanupOut');
    if (asking) return;
    if (!cache.dash.length && !cache.apps.length) {
      note.textContent = 'Wait for the inventory to load, then ask again.';
      return;
    }
    var facts = cleanupFacts();
    var d = usageTally(forApps(cache.dash)), a = usageTally(forApps(cache.apps)), m = usageTally(forApps(cache.macros));
    out.innerHTML = '<p class="note">Asking the saved provider…</p>';
    note.textContent = localSavings(d, a, m);
    asking = true;
    document.getElementById('koCleanup').disabled = true;
    Health.act('ko_cleanup', { tok_ai_brief: facts }).then(function (rows) {
      var row = (rows && rows[0]) || {};
      if (row.status === 'replied' && row.reply && row.reply !== 'none') {
        out.innerHTML = Health.reply(row.reply, { from_ai: row.provider, requested_at: 'estimate, not measured' });
        var sav = String(row.reply).split('\n').filter(function (line) { return /^SAVINGS:/i.test(line); })[0];
        note.textContent = (sav ? sav.replace(/^SAVINGS:\s*/i, '') + ' ' : '') + localSavings(d, a, m);
      } else {
        out.innerHTML = '<p class="note">The provider did not reply. Save an AI provider under Configure, then try again. ' + Health.esc(row.cleanup_error || 'No rows. The provider is off or the key is missing.') + '</p>';
      }
    }, function (error) {
      Health.fail(out, error);
    }).then(function () {
      asking = false;
      document.getElementById('koCleanup').disabled = false;
    });
  }

  document.getElementById('apply').addEventListener('click', load);
  document.getElementById('koFilter').addEventListener('change', paintAll);
  document.getElementById('koCleanup').addEventListener('click', askCleanup);
  loadNames();
  load();
})();

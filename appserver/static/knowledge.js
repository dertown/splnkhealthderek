/* Knowledge objects page: dashboards, apps, macros, lookup files. */
(function () {
  Health.link('home', 'executive_overview');
  Health.link('setup', 'ai_provider_setup');

  var ORDER = ['In use', 'Required', 'Disabled', 'Unused'];
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
    var usage = usageOf(row);
    return usage === 'Disabled' || usage === 'Required';
  }

  function disableLabel(row) {
    if (usageOf(row) === 'Required') return 'Required';
    return alreadyOff(row) ? 'Off' : 'Disable';
  }

  function counts(rows) {
    var tally = { 'In use': 0, Required: 0, Disabled: 0, Unused: 0 };
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

  function hideSystem() {
    var box = document.getElementById('koHideSystem');
    return !box || box.checked;
  }

  function scopedRows(rows) {
    var picked = Health.koMarkRows(forApps(rows).map(function (row) {
      var copy = {};
      Object.keys(row).forEach(function (key) { copy[key] = row[key]; });
      return copy;
    }));
    var filter = (document.getElementById('koFilter') || {}).value || 'all';
    if (hideSystem() && filter !== 'Required') {
      return picked.filter(function (row) { return usageOf(row) !== 'Required'; });
    }
    return picked;
  }

  function paint(chartId, statsId, tableId, rows, columns, filter, kind) {
    var scoped = scopedRows(rows);
    var summary = counts(scoped);
    var filtered = shown(scoped, filter);
    Charts.pie(document.getElementById(chartId), summary.filter(function (row) { return row.count > 0; }), 'usage', 'count', '');
    var tiles = [
      { val: scoped.length, lbl: hideSystem() && filter !== 'Required' ? 'Custom objects' : 'On system', kind: '' },
      { val: summary[0].count, lbl: 'In use', kind: 'ok' }
    ];
    if (!hideSystem() || filter === 'Required') {
      tiles.push({ val: summary[1].count, lbl: 'Required', kind: '' });
    }
    tiles.push(
      { val: summary[2].count, lbl: 'Disabled', kind: summary[2].count ? 'warn' : '' },
      { val: summary[3].count, lbl: 'Unused', kind: summary[3].count ? 'bad' : '' }
    );
    Health.stats(document.getElementById(statsId), tiles);
    Health.table(document.getElementById(tableId), filtered, columns, kind ? function (row, col) {
      if (col === 'disable') disable(kind, row);
    } : null);
  }

  function paintAll() {
    var filter = document.getElementById('koFilter').value || 'all';
    var dash = scopedRows(cache.dash), apps = scopedRows(cache.apps), macros = scopedRows(cache.macros), lookups = scopedRows(cache.lookups);
    function unused(rows) { return rows.filter(function (row) { return usageOf(row) === 'Unused'; }).length; }
    Health.stats(document.getElementById('stats'), [
      { val: dash.length + apps.length + macros.length + lookups.length, lbl: hideSystem() ? 'Custom objects' : 'Objects on this search head', kind: '' },
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
      classifyRequired();
    }).catch(failAll);
  }

  function unknownUnusedApps() {
    var seen = {};
    cache.apps.forEach(function (row) {
      var app = row.app_name || '';
      if (!app || Health.koRuleRequired(app) || Health.koRequired(app)) return;
      if ((row.usage || '') !== 'Unused') return;
      seen[app] = 1;
    });
    return Object.keys(seen).slice(0, 80);
  }

  var classifying = false;
  function classifyRequired() {
    var note = document.getElementById('koNote');
    var names = unknownUnusedApps();
    if (!names.length || classifying) return;
    var fingerprint = names.slice().sort().join(',');
    try {
      var prior = JSON.parse(window.localStorage.getItem('exec_health_ko_class') || '{}');
      if (prior.fp === fingerprint && Date.now() - (prior.at || 0) < 86400000) return;
    } catch (err) {}
    classifying = true;
    Health.query('ai_current').then(function (rows) {
      var status = ((rows && rows[0]) || {}).ai_status || '';
      if (status !== 'READY') {
        classifying = false;
        return;
      }
      note.textContent = 'Asking the AI provider which remaining unused apps are TAs or premium components that must stay on.';
      var brief = ('Classify Splunk app folders. KEEP if the app is a TA, SA, DA, CIM, ES, ITSI, SOAR, UBA, ESCU, or other component required for collection or a premium product. REVIEW if it looks like unused custom content. Reply with exactly two lines. KEEP: comma-separated folder names or none. REVIEW: comma-separated folder names or none. Apps: ' + names.join(', ') + '.')
        .replace(/[|"`$\r\n]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 5800);
      return Health.act('ko_classify', { tok_ai_brief: brief }).then(function (replyRows) {
        try { window.localStorage.setItem('exec_health_ko_class', JSON.stringify({ fp: fingerprint, at: Date.now() })); } catch (err) {}
        var row = (replyRows && replyRows[0]) || {};
        var kept = Health.koParseKeep(row.reply || '');
        if (row.status === 'replied' && kept.length) {
          Health.koRememberKeep(kept);
          paintAll();
          note.textContent = 'AI marked ' + kept.length + ' app' + (kept.length === 1 ? '' : 's') + ' as required: ' + kept.slice(0, 12).join(', ') + (kept.length > 12 ? '…' : '') + '. They are hidden with TAs and premium apps.';
        } else if (row.status === 'replied') {
          note.textContent = 'AI did not add more required apps. TAs and known premium apps stay hidden.';
        }
      });
    }).catch(function () {}).then(function () { classifying = false; });
  }

  function disable(kind, row) {
    var name = kind === 'app' ? (row.app_name || '') : (row.ko_name || '');
    var app = row.app_name || '';
    var owner = row.owner || 'nobody';
    var note = document.getElementById('koNote');
    if (!name) return;
    if (Health.koRequired(app || name)) return;
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
    var t = { total: rows.length, unused: 0, disabled: 0, inuse: 0, required: 0 };
    rows.forEach(function (row) {
      var u = usageOf(row);
      if (u === 'Unused') t.unused += 1;
      else if (u === 'Disabled') t.disabled += 1;
      else if (u === 'Required') t.required += 1;
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
    var dash = scopedRows(cache.dash), apps = scopedRows(cache.apps), macros = scopedRows(cache.macros), lookups = scopedRows(cache.lookups);
    var d = usageTally(dash), a = usageTally(apps), m = usageTally(macros), l = usageTally(lookups);
    var pick = picker ? picker.selected() : { count: 0, total: 0 };
    var lines = [
      'Look-back ' + (document.getElementById('koWindow').value || '30d') + '.',
      pick.count && pick.count !== pick.total ? 'Apps selected: ' + Object.keys(pick.set).slice(0, 40).join(', ') + '.' : 'Apps: all.',
      'Dashboards total ' + d.total + ' unused ' + d.unused + ' disabled ' + d.disabled + ' in-use ' + d.inuse + ' required ' + d.required + '.',
      'Apps total ' + a.total + ' unused ' + a.unused + ' disabled ' + a.disabled + ' in-use ' + a.inuse + ' required ' + a.required + '.',
      'Macros total ' + m.total + ' unused ' + m.unused + ' disabled ' + m.disabled + ' in-use ' + m.inuse + ' required ' + m.required + '.',
      'Lookups total ' + l.total + ' unused ' + l.unused + ' in-use ' + l.inuse + ' required ' + l.required + '. Lookups cannot be disabled from this app.',
      'Do not disable TAs, SA or DA add-ons, CIM, ES, ITSI, SOAR, UBA, ESCU, or other Required objects. Protected: splunk_exec_health, search, launcher.',
      'Unused dashboard sample: ' + (sampleUnused(dash, 12).join('; ') || 'none') + '.',
      'Unused app sample: ' + (sampleUnused(apps, 8).join('; ') || 'none') + '.',
      'Unused macro sample: ' + (sampleUnused(macros, 12).join('; ') || 'none') + '.',
      'Unused lookup sample: ' + (sampleUnused(lookups, 8).join('; ') || 'none') + '.'
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
    var d = usageTally(scopedRows(cache.dash)), a = usageTally(scopedRows(cache.apps)), m = usageTally(scopedRows(cache.macros));
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
  document.getElementById('koHideSystem').addEventListener('change', paintAll);
  document.getElementById('koCleanup').addEventListener('click', askCleanup);
  loadNames();
  load();
})();

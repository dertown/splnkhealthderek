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

  // Unused objects per app, from the rows the page is showing (TAs and premium hidden).
  function unusedByApp() {
    var by = {};
    function entry(app) {
      return by[app] = by[app] || { dashboards: 0, macros: 0, lookups: 0, appUnused: false };
    }
    [['dash', 'dashboards'], ['macros', 'macros'], ['lookups', 'lookups']].forEach(function (pair) {
      scopedRows(cache[pair[0]]).forEach(function (row) {
        if (row.app_name && usageOf(row) === 'Unused') entry(row.app_name)[pair[1]] += 1;
      });
    });
    scopedRows(cache.apps).forEach(function (row) {
      if (row.app_name && usageOf(row) === 'Unused') entry(row.app_name).appUnused = true;
    });
    return by;
  }

  function byAppFact(by) {
    return Object.keys(by).map(function (app) {
      var e = by[app];
      return { app: app, total: e.dashboards + e.macros + e.lookups + (e.appUnused ? 1 : 0), e: e };
    }).sort(function (x, y) { return y.total - x.total; }).slice(0, 30).map(function (item) {
      return item.app + ' dashboards ' + item.e.dashboards + ' macros ' + item.e.macros + ' lookups ' + item.e.lookups
        + (item.e.appUnused ? ' app unused' : '');
    }).join('; ');
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
      'Unused objects by app: ' + (byAppFact(unusedByApp()) || 'none') + '.',
      loadFact(),
      'Unused dashboard sample: ' + (sampleUnused(dash, 12).join('; ') || 'none') + '.',
      'Unused app sample: ' + (sampleUnused(apps, 8).join('; ') || 'none') + '.',
      'Unused macro sample: ' + (sampleUnused(macros, 12).join('; ') || 'none') + '.',
      'Unused lookup sample: ' + (sampleUnused(lookups, 8).join('; ') || 'none') + '.'
    ];
    return lines.join(' ').replace(/[|"`$\r\n]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 5800);
  }

  // --- Measured search-head load by app (ko_load: _introspection + scheduler) ---

  var measured = { all: null, by: {}, ok: false };

  function setLoad(rows) {
    measured = { all: null, by: {}, ok: false };
    (rows || []).forEach(function (row) {
      if (row.app === 'ALL') measured.all = row; else if (row.app) measured.by[row.app] = row;
    });
    measured.ok = !!(measured.all && Health.num(measured.all.coverage_days) > 0);
  }

  function pct(value, digits) {
    var n = Health.num(value);
    return (n >= 10 ? n.toFixed(0) : n.toFixed(digits == null ? 2 : digits)) + '%';
  }

  function loadFact() {
    var all = measured.all;
    if (!measured.ok) {
      return all && Health.num(all.sched_runs) > 0
        ? 'Measured scheduler load last 7 days: ' + all.sched_runs + ' scheduled runs, ' + all.skipped + ' skipped. Search-head CPU and memory not measured.'
        : 'Search-head load: not measured.';
    }
    var by = unusedByApp();
    var names = Object.keys(by).filter(function (app) { return measured.by[app]; });
    Object.keys(measured.by).sort(function (x, y) { return Health.num(measured.by[y].cpu_sec) - Health.num(measured.by[x].cpu_sec); })
      .slice(0, 10).forEach(function (app) { if (names.indexOf(app) < 0) names.push(app); });
    var parts = names.slice(0, 30).map(function (app) {
      var r = measured.by[app];
      return app + ' cpu ' + pct(r.cpu_pct, 3) + ' of search head (scheduled ' + pct(r.sched_cpu_pct, 3) + ', accelerations ' + pct(r.accel_cpu_pct, 3)
        + ', dashboards ' + pct(r.dash_cpu_pct, 3) + '), avg memory ' + Health.num(r.avg_mem_mb) + ' MB (' + pct(r.mem_pct, 3) + '), scheduled runs '
        + Health.num(r.sched_runs) + ', skipped ' + Health.num(r.skipped) + ', scheduler time ' + pct(r.sched_share);
    });
    return 'Measured search-head load, last ' + all.coverage_days + ' days on ' + Health.num(all.hosts) + ' search head(s): busy ' + pct(all.cpu_pct)
      + ' of CPU, ' + Health.num(all.sched_runs) + ' scheduled runs, ' + Health.num(all.skipped) + ' skipped. By app: ' + (parts.join('; ') || 'none') + '.';
  }

  // Sum the measured load of the apps the AI named (or the apps with unused objects).
  function measuredFor(apps) {
    var sum = { cpu: 0, sched_cpu: 0, sched_share: 0, runs: 0, skipped: 0, mem: 0, mem_mb: 0, matched: 0 };
    apps.forEach(function (app) {
      var r = measured.by[app];
      if (!r) return;
      sum.matched += 1;
      sum.cpu += Health.num(r.cpu_pct);
      sum.sched_cpu += Health.num(r.sched_cpu_pct);
      sum.sched_share += Health.num(r.sched_share);
      sum.runs += Health.num(r.sched_runs);
      sum.skipped += Health.num(r.skipped);
      sum.mem += Health.num(r.mem_pct);
      sum.mem_mb += Health.num(r.avg_mem_mb);
    });
    return sum;
  }

  // Confidence from how much measurement backs the number, not from the AI.
  function rate(area) {
    var all = measured.all || {};
    var days = Health.num(all.coverage_days);
    if (area === 'SAVE_SCHEDULED') {
      if (Health.num(all.sched_runs) > 0) return { level: 'high', basis: 'measured from ' + Health.num(all.sched_runs) + ' scheduler runs in 7 days' };
      return { level: 'low', basis: 'no scheduler runs found, AI estimate only' };
    }
    if (measured.ok && days >= 5) return { level: 'high', basis: 'measured, ' + days + ' days of _introspection on ' + Health.num(all.hosts) + ' search head(s)' };
    if (measured.ok) return { level: 'medium', basis: 'measured, only ' + days + ' days of _introspection' };
    return { level: 'low', basis: 'no _introspection data, AI estimate only' };
  }

  function localSavings(d, a, m) {
    var unused = d.unused + a.unused + m.unused;
    var load = unused > 200 ? 'high' : unused > 40 ? 'medium' : unused > 0 ? 'low' : 'none';
    var pct = unused < 1 ? 0 : Math.min(25, Math.round(unused / Math.max(d.total + a.total + m.total, 1) * 40));
    return 'Local estimate only: disabling ' + unused + ' unused objects is a ' + load
      + ' knowledge-object load reduction, roughly ' + pct + '% of the listed inventory. Not a measured CPU saving.';
  }

  // --- AI cleanup reply: savings tiles, app table with drill-down, prose ---------

  var SAVE_AREAS = [
    { key: 'SAVE_CPU', label: 'Search-head CPU' },
    { key: 'SAVE_SCHEDULED', label: 'Scheduled searches' },
    { key: 'SAVE_MEMORY', label: 'Memory' }
  ];
  var MARKER = /^\s*(?:[-*]\s*)?\**\s*(APP|SAVE_CPU|SAVE_SCHEDULED|SAVE_MEMORY|CONFIDENCE|SAVINGS)\s*\**\s*:\s*(.*)$/i;
  var APP_ACTION_COLS = [
    { key: 'app_name', label: 'App' }, { key: 'action', label: 'AI action' },
    { key: 'dashboards', label: 'Unused dashboards' }, { key: 'macros', label: 'Unused macros' },
    { key: 'lookups', label: 'Unused lookups' }, { key: 'usage', label: 'App status' },
    { key: 'cpu_pct', label: 'CPU % of search head' }, { key: 'avg_mem_mb', label: 'Avg memory MB' },
    { key: 'sched_runs', label: 'Scheduled runs' }, { key: 'skipped', label: 'Skipped' },
    { key: 'reason', label: 'Why' },
    { key: 'show', label: '', button: 'Show here' },
    { key: 'search', label: '', button: 'Search' }
  ];

  function level(text) {
    var match = String(text || '').toLowerCase().match(/\b(none|low|medium|high)\b/);
    return match ? match[1] : '';
  }

  function parseCleanup(text) {
    var out = { apps: [], save: {}, confidence: '', savings: '', prose: [] };
    String(text || '').split('\n').forEach(function (line) {
      var match = line.match(MARKER);
      if (!match) { out.prose.push(line); return; }
      var tag = match[1].toUpperCase();
      var body = match[2].replace(/\*\*/g, '').trim();
      var parts = body.split(';').map(function (part) { return part.trim(); });
      if (tag === 'APP') {
        var name = (parts[0] || '').replace(/[`'"*]/g, '').trim();
        if (name) out.apps.push({ app: name, action: parts[1] || 'review', reason: parts.slice(2).join('; ') });
      } else if (tag === 'CONFIDENCE') {
        out.confidence = body;
      } else if (tag === 'SAVINGS') {
        out.savings = body;
      } else {
        out.save[tag] = { level: level(parts[0]), range: parts[1] || '', confidence: level(parts[2]), reason: parts.slice(3).join('; ') };
      }
    });
    out.prose = out.prose.join('\n').trim();
    return out;
  }

  // One tile per area: the measured current use of the named apps (the most that
  // disabling them could save), the AI's estimate, and a confidence that comes
  // from how much measurement backs the number.
  function saveTiles(save, apps) {
    var esc = Health.esc;
    var m = measuredFor(apps);
    var have = measured.ok && m.matched > 0;
    var values = {
      SAVE_CPU: have ? { val: pct(m.cpu, 2), sub: 'of search-head CPU used by these apps (' + pct(m.sched_cpu, 2) + ' scheduled)' } : null,
      SAVE_SCHEDULED: measured.all && Health.num(measured.all.sched_runs) > 0
        ? { val: pct(m.sched_share, 1), sub: 'of scheduler run time, ' + m.runs + ' runs and ' + m.skipped + ' skipped in 7 days' } : null,
      SAVE_MEMORY: have ? { val: pct(m.mem, 2), sub: 'of search-head memory, about ' + Math.round(m.mem_mb) + ' MB on average' } : null
    };
    return '<div class="stats-row save-tiles">' + SAVE_AREAS.map(function (area) {
      var s = save[area.key] || {};
      var v = values[area.key];
      var conf = v ? rate(area.key)
        : { level: 'low', basis: 'Nothing measured, AI estimate only' + (s.confidence ? ' (the AI rated itself ' + s.confidence + ')' : '') };
      var shown = v ? v.val : (s.level ? s.level.toUpperCase() : 'N/A');
      var share = v ? parseFloat(v.val) : 0;
      var kind = v ? (share >= 5 ? 'ok' : (share >= 1 ? 'warn' : '')) : (s.level === 'high' ? 'ok' : (s.level === 'medium' ? 'warn' : ''));
      return '<div class="stat save-tile">'
        + '<div class="lbl">' + esc(area.label) + '</div>'
        + '<div class="val ' + kind + '">' + esc(shown) + '</div>'
        + '<div class="range">' + esc(v ? v.sub + ' (the most it could save)' : 'Not measured') + '</div>'
        + '<div class="range ai">AI estimate: ' + esc((s.level ? s.level.toUpperCase() : 'none') + (s.range ? ', ' + s.range : '')) + '</div>'
        + '<div class="conf conf-' + esc(conf.level) + '" title="' + esc(conf.basis) + '">Confidence: ' + esc(conf.level) + '</div>'
        + '<div class="why">' + esc(conf.basis) + (s.reason ? '. ' + s.reason : '') + '</div>'
        + '</div>';
    }).join('') + '</div>';
  }

  function safeApp(name) {
    return /^[A-Za-z0-9._-]{1,100}$/.test(name);
  }

  // Every knowledge object owned by these apps, from REST on this search head.
  function searchUrl(apps) {
    var list = apps.filter(safeApp).map(function (app) { return '"' + app + '"'; }).join(', ');
    var spl = '| rest /servicesNS/-/-/directory count=0 splunk_server=local\n'
      + '| search eai:acl.app IN (' + list + ')\n'
      + '| rename eai:acl.app AS app, eai:type AS type, eai:acl.owner AS owner, eai:acl.sharing AS sharing\n'
      + '| table app, type, title, owner, sharing, disabled, updated\n'
      + '| sort 0 app, type, title';
    return Health.root() + '/app/search/search?q=' + encodeURIComponent(spl) + '&earliest=-24h&latest=now';
  }

  function showHere(apps) {
    var filter = document.getElementById('koFilter');
    if (filter) filter.value = 'Unused';
    if (picker && picker.only) picker.only(apps); else paintAll();
    var target = document.getElementById('dashTable');
    if (target && target.scrollIntoView) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function appActionRows(parsed) {
    var known = {};
    appNames().forEach(function (name) { known[name.toLowerCase()] = name; });
    var appUsage = {};
    cache.apps.forEach(function (row) { if (row.app_name) appUsage[row.app_name] = usageOf(row); });
    var by = unusedByApp();
    var rows = [], dropped = [], seen = {};
    parsed.apps.forEach(function (item) {
      var name = known[item.app.toLowerCase()];
      if (!name || !safeApp(name)) { dropped.push(item.app); return; }
      if (seen[name]) return;
      seen[name] = 1;
      var e = by[name] || { dashboards: 0, macros: 0, lookups: 0 };
      var r = measured.by[name] || {};
      rows.push({
        app_name: name, action: item.action, reason: item.reason || '',
        dashboards: e.dashboards, macros: e.macros, lookups: e.lookups,
        cpu_pct: measured.ok ? pct(r.cpu_pct, 3) : 'not measured',
        avg_mem_mb: measured.ok ? Health.num(r.avg_mem_mb) : 'not measured',
        sched_runs: Health.num(r.sched_runs), skipped: Health.num(r.skipped),
        usage: Health.koRequired(name) ? 'Required' : (appUsage[name] || 'In use')
      });
    });
    return { rows: rows, dropped: dropped };
  }

  function renderCleanup(out, row) {
    var parsed = parseCleanup(row.reply);
    var esc = Health.esc;
    var html = '';
    var actions = appActionRows(parsed);
    var tileApps = actions.rows.length ? actions.rows.map(function (r) { return r.app_name; }) : Object.keys(unusedByApp());
    html += saveTiles(parsed.save, tileApps);
    if (parsed.confidence || parsed.savings) {
      html += '<p class="note">' + (parsed.savings ? esc(parsed.savings) + ' ' : '')
        + (parsed.confidence ? 'Overall confidence: ' + esc(parsed.confidence) + '. ' : '')
        + 'The AI ranges are estimates. Tile values are measured current use, the most that disabling these apps could save.</p>';
    }
    if (actions.rows.length) {
      html += '<h3 class="sub-title">Apps to act on (' + actions.rows.length + ')</h3>'
        + '<div class="ko-app-actions"><button type="button" class="btn secondary" id="koShowAll">Show all here</button>'
        + '<a class="btn secondary" id="koSearchAll" target="_blank" rel="noopener" href="' + esc(searchUrl(actions.rows.map(function (r) { return r.app_name; }))) + '">Search the full list</a></div>'
        + '<div id="koAppActions"></div>';
      if (actions.dropped.length) {
        html += '<p class="note">Not on this search head, so not listed: ' + esc(actions.dropped.slice(0, 10).join(', ')) + '.</p>';
      }
    }
    html += parsed.prose ? Health.reply(parsed.prose, { from_ai: row.provider, requested_at: 'estimate, not measured' }) : '';
    out.innerHTML = html || '<p class="note">The provider replied without suggestions.</p>';
    var tableEl = document.getElementById('koAppActions');
    if (tableEl) {
      Health.table(tableEl, actions.rows, APP_ACTION_COLS, function (r, col) {
        if (col === 'show') showHere([r.app_name]);
        else if (col === 'search') window.open(searchUrl([r.app_name]), '_blank', 'noopener');
      });
      document.getElementById('koShowAll').addEventListener('click', function () {
        showHere(actions.rows.map(function (r) { return r.app_name; }));
      });
    }
    return parsed;
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
    var d = usageTally(scopedRows(cache.dash)), a = usageTally(scopedRows(cache.apps)), m = usageTally(scopedRows(cache.macros));
    out.innerHTML = '<p class="note">Measuring search-head load by app (last 7 days)…</p>';
    note.textContent = localSavings(d, a, m);
    asking = true;
    document.getElementById('koCleanup').disabled = true;
    Health.query('ko_load').then(setLoad, function () { setLoad([]); }).then(function () {
      out.innerHTML = '<p class="note">' + (measured.ok ? 'Measured ' + measured.all.coverage_days + ' days of load. ' : 'No _introspection load found. ')
        + 'Asking the saved provider…</p>';
      return Health.act('ko_cleanup', { tok_ai_brief: cleanupFacts() });
    }).then(function (rows) {
      var row = (rows && rows[0]) || {};
      if (row.status === 'replied' && row.reply && row.reply !== 'none') {
        renderCleanup(out, row);
        note.textContent = localSavings(d, a, m);
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

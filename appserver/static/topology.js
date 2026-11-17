(function () {
  Health.link('home', 'executive_overview');
  var paths = [];
  var tcpAll = [];
  var rows = [];
  var focus = null;
  var request = 0;
  var map = null;
  var bounds = { events: 'events', mean: 'mean', drop_bound: 'drop (2σ)', burst_bound: 'burst (2σ)' };
  var LABEL = { site: 'Site', host: 'Host', ingest_method: 'Ingestion path', family: 'Sourcetype family', endpoint: 'Sourcetype', splunk_index: 'Index' };
  var HOVER_HINT = 'Hover a node to light its path. Click it to select it and fill the tables below.';
  var sliceColumns = [
    { key: 'environment', label: 'Site' },
    { key: 'data_source', label: 'Host' },
    { key: 'ingest_method', label: 'Ingest' },
    { key: 'endpoint', label: 'Sourcetype' },
    { key: 'splunk_index', label: 'Index' },
    { key: 'network', label: 'CIDR or host' },
    { key: 'events', label: 'Events (24h)' }
  ];
  var flowColumns = [
    { key: 'environment', label: 'Site' },
    { key: 'data_source', label: 'Host' },
    { key: 'ingest_method', label: 'Ingestion path' },
    { key: 'family', label: 'Family' },
    { key: 'endpoint', label: 'Sourcetype' },
    { key: 'splunk_index', label: 'Index' },
    { key: 'events', label: 'Events (24h)' }
  ];
  var directoryColumns = [
    { key: 'endpoint', label: 'Sourcetype' },
    { key: 'family', label: 'Family' },
    { key: 'events', label: 'Events (24h)' },
    { key: 'hosts', label: 'Hosts' },
    { key: 'indexes', label: 'Indexes' }
  ];

  function matches(row, f) {
    if (!f) return true;
    if (f.col === 'site') return row.environment === f.name;
    if (f.col === 'host') return row.data_source === f.name;
    if (f.col === 'ingest_method') return row.ingest_method === f.name;
    if (f.col === 'family') return row.family === f.name;
    if (f.col === 'endpoint') return row.endpoint === f.name && (!f.family || row.family === f.family);
    if (f.col === 'splunk_index') return row.splunk_index === f.name;
    return true;
  }
  function selection() { return rows.filter(function (row) { return matches(row, focus); }); }
  function byEvents(list) {
    return list.slice().sort(function (a, b) { return (Number(b.events) || 0) - (Number(a.events) || 0); });
  }
  function distinct(list, key) {
    var seen = {};
    list.forEach(function (row) { if (row[key]) seen[row[key]] = 1; });
    return Object.keys(seen).length;
  }
  function describe() {
    return focus ? ' · ' + LABEL[focus.col] + ' ' + focus.name : '';
  }

  function endpointTable(list) {
    var bag = {};
    list.forEach(function (row) {
      var key = (row.family || '') + '\u0001' + (row.endpoint || 'unknown');
      if (!bag[key]) bag[key] = { endpoint: row.endpoint || 'unknown', family: row.family || '', events: 0, hosts: {}, indexes: {} };
      bag[key].events += Number(row.events) || 0;
      if (row.data_source) bag[key].hosts[row.data_source] = 1;
      if (row.splunk_index) bag[key].indexes[row.splunk_index] = 1;
    });
    return Object.keys(bag).map(function (key) {
      var item = bag[key];
      return { endpoint: item.endpoint, family: item.family, events: Math.round(item.events), hosts: Object.keys(item.hosts).length, indexes: Object.keys(item.indexes).length };
    }).sort(function (a, b) { return b.events - a.events; });
  }
  function showDirectory(list) {
    var table = endpointTable(list);
    var events = table.reduce(function (sum, row) { return sum + row.events; }, 0);
    Health.stats(document.getElementById('srcStats'), [
      { val: table.length, lbl: 'Sourcetypes' },
      { val: distinct(list, 'family'), lbl: 'Families' },
      { val: Math.round(events).toLocaleString(), lbl: 'Events (24h)' }
    ]);
    Health.table(document.getElementById('srcSlice'), table, directoryColumns, function (row) {
      pick({ col: 'endpoint', name: row.endpoint, family: row.family }, true);
    });
    document.getElementById('srcTrend').innerHTML = '<p class="note">Click a node in the map for its 24-hour trend and 2σ bounds.</p>';
    document.getElementById('srcOutliers').innerHTML = '';
  }

  function showFlows(list) {
    var title = document.getElementById('missingTitle');
    var box = document.getElementById('missing');
    var sorted = byEvents(list);
    if (!focus) {
      title.textContent = 'Busiest flows on the map';
      Health.table(box, sorted.slice(0, 100), flowColumns, function (row) { pick({ col: 'host', name: row.data_source }, true); });
      return;
    }
    title.textContent = 'Flows through ' + LABEL[focus.col].toLowerCase() + ' ' + focus.name;
    if (!sorted.length) {
      box.innerHTML = '<p class="note">Nothing flows through this selection. Click it again to clear it.</p>';
      return;
    }
    Health.table(box, sorted.slice(0, 200), flowColumns, function (row) { pick({ col: 'host', name: row.data_source }, true); });
  }

  function markRows(name) {
    ['paths', 'tcpin'].forEach(function (id) {
      Array.prototype.forEach.call(document.querySelectorAll('#' + id + ' tbody tr'), function (tr) {
        var cell = tr.querySelector('td');
        tr.classList.toggle('selected', !!(cell && name && cell.textContent === name));
      });
    });
  }
  function paintLists(chosen) {
    var hosts = {};
    chosen.forEach(function (row) { if (row.data_source) hosts[row.data_source] = 1; });
    var pathRows = paths;
    var tcpRows = tcpAll;
    if (focus) {
      pathRows = paths.filter(function (row) {
        return hosts[row.data_source] && (focus.col !== 'splunk_index' || row.splunk_index === focus.name);
      });
      tcpRows = tcpAll.filter(function (row) { return hosts[row.data_source]; });
    }
    var hostList = Object.keys(hosts);
    var one = focus && focus.col === 'host' ? focus.name : (focus && hostList.length === 1 ? hostList[0] : '');
    Health.table(document.getElementById('paths'), pathRows, null, function (row) { pick({ col: 'host', name: row.data_source }, true); });
    Health.table(document.getElementById('tcpin'), tcpRows, null, function (row) { pick({ col: 'host', name: row.data_source }, true); });
    markRows(one);
  }

  function loadHost(name) {
    var id = ++request;
    document.getElementById('srcSlice').innerHTML = '';
    document.getElementById('srcTrend').innerHTML = '<p class="note">Loading the 24-hour trend…</p>';
    document.getElementById('srcOutliers').innerHTML = '';
    var params = { tok_data_source: name };
    Promise.all([
      Health.query('topo_src_stats', params),
      Health.query('topo_src_trend', params),
      Health.query('topo_src_outliers', params)
    ]).then(function (res) {
      if (id !== request) return;
      Health.table(document.getElementById('srcStats'), res[0]);
      Health.table(document.getElementById('srcSlice'), byEvents(selection()).slice(0, 15), sliceColumns);
      Charts.line(document.getElementById('srcTrend'), res[1], '_time', ['events', 'mean', 'burst_bound', 'drop_bound'], bounds);
      Health.table(document.getElementById('srcOutliers'), res[2]);
    }).catch(function (error) {
      if (id !== request) return;
      Health.fail(document.getElementById('srcStats'), error);
    });
  }

  function trendParams() {
    var params = { tok_topo_environment: '*', tok_topo_ingest: '*', tok_topo_family: '*', tok_topo_endpoint: '*', tok_topo_index: '*' };
    if (focus.col === 'site') params.tok_topo_environment = focus.name;
    else if (focus.col === 'ingest_method') params.tok_topo_ingest = focus.name;
    else if (focus.col === 'family') params.tok_topo_family = focus.name;
    else if (focus.col === 'endpoint') {
      params.tok_topo_endpoint = focus.name;
      if (focus.family) params.tok_topo_family = focus.family;
    } else if (focus.col === 'splunk_index') params.tok_topo_index = focus.name;
    return params;
  }

  function loadGroup(chosen) {
    var id = ++request;
    var sorted = byEvents(chosen);
    var events = sorted.reduce(function (sum, row) { return sum + (Number(row.events) || 0); }, 0);
    Health.stats(document.getElementById('srcStats'), [
      { val: distinct(sorted, 'data_source'), lbl: 'Hosts' },
      { val: Math.round(events).toLocaleString(), lbl: 'Events (24h)' },
      { val: distinct(sorted, 'endpoint'), lbl: 'Sourcetypes' },
      { val: distinct(sorted, 'splunk_index'), lbl: 'Indexes' },
      { val: distinct(sorted, 'ingest_method'), lbl: 'Ingest methods' }
    ]);
    Health.table(document.getElementById('srcSlice'), sorted.slice(0, 15), sliceColumns, function (row) { pick({ col: 'host', name: row.data_source }, true); });
    document.getElementById('srcTrend').innerHTML = '<p class="note">Loading the 24-hour trend for this selection…</p>';
    document.getElementById('srcOutliers').innerHTML = '';
    Health.query('topo_focus_trend', trendParams()).then(function (trend) {
      if (id !== request) return;
      Charts.line(document.getElementById('srcTrend'), trend, '_time', ['events', 'mean', 'burst_bound', 'drop_bound'], bounds);
      var drops = trend.filter(function (row) { return row.outlier === 'DROP' || row.outlier === 'BURST'; });
      if (!drops.length) {
        document.getElementById('srcOutliers').innerHTML = '<p class="note">No drop or burst buckets in this selection.</p>';
        return;
      }
      Health.table(document.getElementById('srcOutliers'), drops, [
        { key: 'bucket', label: 'Bucket' },
        { key: 'events', label: 'Events' },
        { key: 'mean', label: 'Mean' },
        { key: 'outlier', label: 'Outlier' }
      ]);
    }).catch(function (error) {
      if (id !== request) return;
      Health.fail(document.getElementById('srcTrend'), error);
    });
  }

  function same(a, b) {
    return !!(a && b && a.col === b.col && a.name === b.name && (a.family || '') === (b.family || ''));
  }
  function pick(desc, reveal) {
    focus = !desc || (same(desc, focus) && !reveal) ? null : desc;
    apply(reveal);
  }

  function apply(reveal) {
    document.getElementById('selected').textContent = describe();
    if (map) map.setFocus(focus);
    var title = document.getElementById('mapTitle');
    var note = document.getElementById('mapNote');
    title.textContent = focus
      ? LABEL[focus.col] + ': ' + focus.name
      : 'Estate map: site and host → ingestion path → family and sourcetype → index';
    note.textContent = focus
      ? 'This drawing is only the ' + LABEL[focus.col].toLowerCase() + ' ' + focus.name + '. The columns are the hosts, ingestion paths, sourcetypes, and indexes in that selection. Click Whole estate to return to every flow.'
      : 'Click a family, a host, a path, or a sourcetype and this map is drawn again around that choice. A family opens into its sourcetypes. Scroll to zoom, drag to pan, double-click a node to zoom to it.';
    var chosen = selection();
    paintLists(chosen);
    showFlows(chosen);
    if (!focus) showDirectory(rows);
    else if (focus.col === 'host') loadHost(focus.name);
    else loadGroup(chosen);
    if (window.Health && Health.help) Health.help(document);
  }

  function settled(promise) {
    return promise.then(function (result) { return { rows: result }; }, function (error) { return { error: error }; });
  }

  map = TopoMap.create(document.getElementById('map'), {
    onPick: function (desc) { pick(desc, false); },
    onHover: function (text) { document.getElementById('mapHover').textContent = text || HOVER_HINT; }
  });
  document.getElementById('mapHover').textContent = 'Loading every host, path, sourcetype, and index…';

  Promise.all([
    settled(Health.query('topo_paths')),
    settled(Health.query('tcpin')),
    settled(Health.query('topo_full'))
  ]).then(function (res) {
    paths = res[0].rows || [];
    tcpAll = res[1].rows || [];
    if (res[2].error) {
      Health.fail(document.getElementById('map'), res[2].error);
      document.getElementById('mapHover').textContent = res[2].error.message || String(res[2].error);
    } else {
      rows = res[2].rows || [];
      map.setData(rows);
      document.getElementById('mapHover').textContent = HOVER_HINT;
    }
    Health.stats(document.getElementById('stats'), [
      { val: distinct(rows, 'environment'), lbl: 'Sites' },
      { val: distinct(rows, 'data_source'), lbl: 'Hosts' },
      { val: distinct(rows, 'ingest_method'), lbl: 'Ingest paths' },
      { val: distinct(rows, 'endpoint'), lbl: 'Sourcetypes' },
      { val: distinct(rows, 'splunk_index'), lbl: 'Indexes' },
      { val: distinct(tcpAll, 'data_source'), lbl: 'Forwarders' }
    ]);
    if (res[0].error) Health.fail(document.getElementById('paths'), res[0].error);
    if (res[1].error) Health.fail(document.getElementById('tcpin'), res[1].error);
    apply(false);
  }).catch(function (error) { Health.fail(document.getElementById('stats'), error); });

  function countStatus(list, names) {
    return list.filter(function (row) { return names.indexOf(row.status) >= 0; }).length;
  }
  Health.query('feed_catalog').then(function (feedRows) {
    if (!feedRows.length) {
      document.getElementById('feedStats').innerHTML = '';
      document.getElementById('feeds').innerHTML = '<p class="note">No feeds in the list yet. In lookups/feed_catalog.csv, add a row, set the state to active, and name the index and sourcetype you expect.</p>';
      return;
    }
    Health.stats(document.getElementById('feedStats'), [
      { val: countStatus(feedRows, ['Gone quiet', 'No events in 30 days']), lbl: 'Gone quiet', kind: 'bad' },
      { val: countStatus(feedRows, ['Wrong sourcetype']), lbl: 'Wrong sourcetype', kind: 'bad' },
      { val: countStatus(feedRows, ['New this week']), lbl: 'New this week', kind: 'warn' }
    ]);
    Health.table(document.getElementById('feeds'), feedRows, [
      { key: 'index', label: 'Index' }, { key: 'sourcetype', label: 'Sourcetype' }, { key: 'source', label: 'Source' },
      { key: 'status', label: 'Status' }, { key: 'last_event', label: 'Last event' },
      { key: 'silent_min', label: 'Minutes since last event' }, { key: 'expected_sourcetype', label: 'Expected sourcetype' },
      { key: 'count', label: 'Events (30d)' }, { key: 'notes', label: 'Notes' }
    ]);
  }).catch(function (error) { Health.fail(document.getElementById('feeds'), error); });
  Promise.all([
    settled(Health.query('quarantine_daily')),
    settled(Health.query('quarantine_rows'))
  ]).then(function (res) {
    if (res[0].error) Health.fail(document.getElementById('quarantineDaily'), res[0].error);
    else {
      var keys = Object.keys((res[0].rows[0] || {})).filter(function (key) { return key !== '_time' && key !== '_span' && key.charAt(0) !== '_'; });
      Charts.line(document.getElementById('quarantineDaily'), res[0].rows, '_time', keys.slice(0, 8));
    }
    if (res[1].error) Health.fail(document.getElementById('quarantineRows'), res[1].error);
    else if (!res[1].rows.length) document.getElementById('quarantineRows').innerHTML = '<p class="note">Nothing has landed in the catch-all indexes in the last 7 days.</p>';
    else Health.table(document.getElementById('quarantineRows'), res[1].rows, [
      { key: 'index', label: 'Index' }, { key: 'sourcetype', label: 'Sourcetype' }, { key: 'source', label: 'Source' },
      { key: 'count', label: 'Events' }, { key: 'first_event', label: 'First event' }, { key: 'last_event', label: 'Last event' }
    ]);
  });
})();

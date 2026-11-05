(function () {
  Health.link('home', 'executive_overview');
  var paths = [];
  var tcpAll = [];
  var mapRows = [];
  var mapError = '';
  var request = 0;
  var focus = { category: '', network: '', ingest: '', index: '', host: '', endpoint: '' };
  var bounds = { events: 'events', mean: 'mean', drop_bound: 'drop (2σ)', burst_bound: 'burst (2σ)' };
  var sliceColumns = [
    { key: 'endpoint', label: 'Sourcetype' },
    { key: 'data_source', label: 'Host' },
    { key: 'network', label: 'CIDR or host' },
    { key: 'ingest_method', label: 'Ingest' },
    { key: 'splunk_index', label: 'Index' },
    { key: 'events', label: 'Events (24h)' }
  ];
  var directoryColumns = [
    { key: 'endpoint', label: 'Sourcetype' },
    { key: 'events', label: 'Events (24h)' },
    { key: 'hosts', label: 'Hosts' },
    { key: 'indexes', label: 'Indexes' }
  ];

  function focused() {
    return !!(focus.endpoint || focus.category || focus.network || focus.ingest || focus.index || focus.host);
  }
  function topEndpointNames() {
    var totals = {};
    mapRows.forEach(function (row) {
      var name = row.endpoint || 'unknown';
      totals[name] = (totals[name] || 0) + (Number(row.events) || 0);
    });
    return Object.keys(totals).sort(function (a, b) { return totals[b] - totals[a]; }).slice(0, 8);
  }
  function topHostNames() {
    var totals = {};
    mapRows.forEach(function (row) {
      var name = row.data_source || 'unknown';
      totals[name] = (totals[name] || 0) + (Number(row.events) || 0);
    });
    return Object.keys(totals).sort(function (a, b) { return totals[b] - totals[a]; }).slice(0, 8);
  }
  function selection() {
    var top = topEndpointNames();
    return mapRows.filter(function (row) {
      var name = row.endpoint || 'unknown';
      if (focus.endpoint === '__more__' && top.indexOf(name) >= 0) return false;
      if (focus.endpoint && focus.endpoint !== '__more__' && name !== focus.endpoint) return false;
      if (focus.host === '__more__' && topHostNames().indexOf(row.data_source || 'unknown') >= 0) return false;
      if (focus.category && row.category !== focus.category) return false;
      if (focus.network && row.network !== focus.network) return false;
      if (focus.ingest && row.ingest_method !== focus.ingest) return false;
      if (focus.index && row.splunk_index !== focus.index) return false;
      if (focus.host && focus.host !== '__more__' && row.data_source !== focus.host) return false;
      return true;
    });
  }
  function describe() {
    var parts = [];
    if (focus.endpoint === '__more__') parts.push('other sources');
    else if (focus.endpoint) parts.push(focus.endpoint);
    if (focus.host === '__more__') parts.push('other hosts');
    else if (focus.host) parts.push(focus.host);
    if (focus.category) parts.push(focus.category);
    if (focus.network) parts.push(focus.network);
    if (focus.ingest) parts.push(focus.ingest);
    if (focus.index) parts.push(focus.index);
    return parts.length ? ' · ' + parts.join(' · ') : '';
  }
  function endpointTable(rows) {
    var map = {};
    rows.forEach(function (row) {
      var name = row.endpoint || 'unknown';
      if (!map[name]) map[name] = { endpoint: name, events: 0, hosts: {}, indexes: {} };
      map[name].events += Number(row.events) || 0;
      if (row.data_source) map[name].hosts[row.data_source] = 1;
      if (row.splunk_index) map[name].indexes[row.splunk_index] = 1;
    });
    return Object.keys(map).map(function (name) {
      return {
        endpoint: name,
        events: Math.round(map[name].events),
        hosts: Object.keys(map[name].hosts).length,
        indexes: Object.keys(map[name].indexes).length
      };
    }).sort(function (a, b) { return b.events - a.events; });
  }
  function showDirectory(rows) {
    rows = rows || mapRows;
    var list = endpointTable(rows);
    var products = {};
    rows.forEach(function (row) { if (row.endpoint_kind === 'product') products[row.endpoint] = 1; });
    var events = list.reduce(function (sum, row) { return sum + row.events; }, 0);
    Health.stats(document.getElementById('srcStats'), [
      { val: list.length, lbl: 'Sourcetypes' },
      { val: Object.keys(products).length, lbl: 'Named products' },
      { val: Math.round(events).toLocaleString(), lbl: 'Events (24h)' }
    ]);
    Health.table(document.getElementById('srcSlice'), list, directoryColumns, function (row) { pick('endpoint', row.endpoint); });
    document.getElementById('srcTrend').innerHTML = '<p class="note">Click a source in the map for its 24-hour trend and 2σ bounds.</p>';
    document.getElementById('srcOutliers').innerHTML = '';
  }
  function markRows(name) {
    ['paths', 'tcpin'].forEach(function (id) {
      Array.prototype.forEach.call(document.querySelectorAll('#' + id + ' tbody tr'), function (tr) {
        var cell = tr.querySelector('td');
        tr.classList.toggle('selected', !!(cell && name && cell.textContent === name));
      });
    });
  }
  function pickHost(name) {
    focus = { category: '', network: '', ingest: '', index: '', host: name || '', endpoint: '' };
    apply();
  }
  function pick(col, name) {
    if (col === 'endpoint') {
      var clear = focus.endpoint === name && !focus.index && !focus.host;
      focus = { category: '', network: '', ingest: '', index: '', host: '', endpoint: clear ? '' : name };
    } else if (col === 'host') {
      var same = focus.host === name && !focus.endpoint && !focus.ingest && !focus.index;
      focus = { category: '', network: '', ingest: '', index: '', endpoint: '', host: same ? '' : name };
    } else if (col === 'network') {
      focus.network = focus.network === name ? '' : name;
      focus.host = '';
    } else if (col === 'ingest_method') {
      focus.ingest = focus.ingest === name ? '' : name;
      focus.host = '';
    } else if (col === 'splunk_index') {
      focus.index = focus.index === name ? '' : name;
      focus.host = '';
      focus.category = '';
      focus.network = '';
    } else if (col === 'category') {
      focus.category = focus.category === name ? '' : name;
      focus.network = '';
      focus.ingest = '';
      focus.index = '';
      focus.host = '';
      focus.endpoint = '';
    }
    apply();
  }
  function drawMap() {
    if (mapError) {
      Health.fail(document.getElementById('map'), mapError);
      document.getElementById('mapHover').textContent = mapError;
      return;
    }
    var selected = { endpoint: focus.endpoint, network: focus.network, ingest: focus.ingest, index: focus.index, host: focus.host };
    Charts.sourceFan(document.getElementById('map'), mapRows, selected, pick, function (text) {
      document.getElementById('mapHover').textContent = text;
    });
  }
  function showMissing(rows) {
    var list = rows.slice().sort(function (a, b) { return (Number(b.events) || 0) - (Number(a.events) || 0); });
    if (!list.length) {
      document.getElementById('missing').innerHTML = '<p class="note">Every source is already drawn. There is nothing in the +N list.</p>';
      return;
    }
    Health.table(document.getElementById('missing'), list.slice(0, 80), [
      { key: 'data_source', label: 'Host' },
      { key: 'ingest_method', label: 'Ingestion path' },
      { key: 'endpoint', label: 'Sourcetype' },
      { key: 'splunk_index', label: 'Index' },
      { key: 'events', label: 'Events (24h)' }
    ], function (row) { pick(focus.host === '__more__' ? 'host' : 'endpoint', focus.host === '__more__' ? row.data_source : row.endpoint); });
  }
  function paintLists() {
    var chosen = selection();
    var hosts = {};
    chosen.forEach(function (row) { if (row.data_source) hosts[row.data_source] = 1; });
    var hostList = Object.keys(hosts);
    var pathRows = paths;
    var tcpRows = tcpAll;
    if (focus.host) {
      pathRows = paths.filter(function (row) { return row.data_source === focus.host; });
      tcpRows = tcpAll.filter(function (row) { return row.data_source === focus.host; });
    } else if (focused() && mapRows.length) {
      pathRows = paths.filter(function (row) {
        return hostList.indexOf(row.data_source) >= 0 && (!focus.index || row.splunk_index === focus.index);
      });
      tcpRows = tcpAll.filter(function (row) { return hostList.indexOf(row.data_source) >= 0; });
    }
    var one = focus.host || (hostList.length === 1 ? hostList[0] : '');
    var flowRows = focused() ? chosen : mapRows;
    var flowPick = focus.host && focus.host !== '__more__' ? focus.host : '';
    Charts.flow(document.getElementById('flow'), flowRows, ['data_source', 'ingest_method', 'endpoint', 'splunk_index'], 'events', flowPick, function (name) { pick('host', name); });
    Health.table(document.getElementById('paths'), pathRows, null, function (row) { pickHost(row.data_source); });
    Health.table(document.getElementById('tcpin'), tcpRows, null, function (row) { pickHost(row.data_source); });
    markRows(one);
  }
  function clearDetails() {
    document.getElementById('srcStats').innerHTML = '';
    document.getElementById('srcSlice').innerHTML = '';
    document.getElementById('srcTrend').innerHTML = '<p class="note">Click the map or a source to see volume against the 2σ drop and burst bounds.</p>';
    document.getElementById('srcOutliers').innerHTML = '';
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
      Charts.line(document.getElementById('srcTrend'), res[1], '_time', ['events', 'mean', 'burst_bound', 'drop_bound'], bounds);
      Health.table(document.getElementById('srcOutliers'), res[2]);
    }).catch(function (error) {
      if (id !== request) return;
      Health.fail(document.getElementById('srcStats'), error);
    });
  }
  function loadGroup() {
    var id = ++request;
    var chosen = selection().slice().sort(function (a, b) { return (Number(b.events) || 0) - (Number(a.events) || 0); });
    if (!chosen.length) {
      Health.stats(document.getElementById('srcStats'), [
        { val: 0, lbl: 'Hosts' }, { val: 0, lbl: 'Events (24h)' },
        { val: 0, lbl: 'Indexes' }, { val: 0, lbl: 'Ingest methods' }
      ]);
      document.getElementById('srcSlice').innerHTML = '';
      document.getElementById('srcTrend').innerHTML = '<p class="note">Nothing in this selection.</p>';
      document.getElementById('srcOutliers').innerHTML = '';
      return;
    }
    var hosts = {}, indexes = {}, methods = {}, events = 0;
    chosen.forEach(function (row) {
      hosts[row.data_source] = 1;
      indexes[row.splunk_index] = 1;
      methods[row.ingest_method] = 1;
      events += Number(row.events) || 0;
    });
    Health.stats(document.getElementById('srcStats'), [
      { val: Object.keys(hosts).length, lbl: 'Hosts' },
      { val: Math.round(events).toLocaleString(), lbl: 'Events (24h)' },
      { val: Object.keys(indexes).length, lbl: 'Indexes' },
      { val: Object.keys(methods).length, lbl: 'Ingest methods' }
    ]);
    Health.table(document.getElementById('srcSlice'), chosen.slice(0, 15), sliceColumns, function (row) { pickHost(row.data_source); });
    document.getElementById('srcTrend').innerHTML = '<p class="note">Loading the 24-hour trend for this selection…</p>';
    document.getElementById('srcOutliers').innerHTML = '';
    Health.query('topo_focus_trend', {
      tok_topo_category: focus.category || '*',
      tok_topo_network: focus.network || '*',
      tok_topo_ingest: focus.ingest || '*',
      tok_topo_index: focus.index || '*',
      tok_topo_endpoint: focus.endpoint && focus.endpoint !== '__more__' ? focus.endpoint : '*'
    }).then(function (rows) {
      if (id !== request) return;
      Charts.line(document.getElementById('srcTrend'), rows, '_time', ['events', 'mean', 'burst_bound', 'drop_bound'], bounds);
      var drops = rows.filter(function (row) { return row.outlier === 'DROP' || row.outlier === 'BURST'; });
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
  function apply() {
    document.getElementById('selected').textContent = describe();
    drawMap();
    paintLists();
    if (focus.endpoint === '__more__' || focus.host === '__more__') showMissing(selection());
    else document.getElementById('missing').innerHTML = '<p class="note">Click +N under the hosts or the sourcetypes to list what did not fit.</p>';
    if (focus.host && focus.host !== '__more__') loadHost(focus.host);
    else if (focus.endpoint === '__more__' || focus.host === '__more__') showDirectory(selection());
    else if (focus.endpoint || focus.category || focus.network || focus.ingest || focus.index) loadGroup();
    else showDirectory(mapRows);
  }
  function settled(promise) {
    return promise.then(function (rows) { return { rows: rows }; }, function (error) { return { error: error }; });
  }
  Promise.all([
    settled(Health.query('topo_paths')),
    settled(Health.query('tcpin')),
    settled(Health.query('topo_map'))
  ]).then(function (res) {
    if (!res[0].rows || !res[1].rows) {
      Health.fail(document.getElementById('stats'), (res[0].error || res[1].error || 'The topology searches could not run.'));
      return;
    }
    paths = res[0].rows;
    tcpAll = res[1].rows;
    mapRows = res[2].rows || [];
    mapError = res[2].error ? (res[2].error.message || String(res[2].error)) : '';
    var count = function (key) { var seen = {}; paths.forEach(function (row) { seen[row[key]] = 1; }); return Object.keys(seen).length; };
    Health.stats(document.getElementById('stats'), [
      { val: count('data_source'), lbl: 'Data sources' },
      { val: count('ingest_path'), lbl: 'Ingest paths' },
      { val: count('splunk_index'), lbl: 'Destination indexes' },
      { val: (function () { var seen = {}; tcpAll.forEach(function (row) { seen[row.data_source] = 1; }); return Object.keys(seen).length; })(), lbl: 'Forwarders' }
    ]);
    apply();
    if (res[2].error) document.getElementById('mapHover').textContent = res[2].error.message || String(res[2].error);
  }).catch(function (error) { Health.fail(document.getElementById('stats'), error); });
})();

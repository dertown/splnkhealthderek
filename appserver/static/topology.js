(function () {
  Health.link('home', 'executive_overview');
  var paths = [];
  var tcpAll = [];
  var mapRows = [];
  var mapError = '';
  var macroRows = [];
  var macroError = '';
  var detailRows = null;
  var detailError = '';
  var detailRequest = 0;
  var zoom = { environment: '', family: '', ingest: '', index: '' };
  var request = 0;
  var focus = { category: '', network: '', ingest: '', index: '', host: '', endpoint: '' };
  var macroView = {
    headers: ['SITES', 'INGESTION PATH', 'SOURCETYPE FAMILY', 'INDEX'],
    hostLimit: 9,
    sourceLimit: 9,
    indexLimit: 9,
    hostTotal: 'env_events',
    sourceTotal: 'fam_events',
    indexTotal: 'idx_events',
    methodTotal: 'method_events',
    pinHost: 'Other sites',
    pinSource: 'Other sourcetypes',
    pinIndex: 'Other indexes',
    hostTitle: function (item) { return 'Site ' + item.name + '. ' + Math.round(item.events).toLocaleString() + ' events in the last 24 hours. Click to open the hosts and sourcetypes in this site.'; },
    methodTitle: function (item) { return 'Ingestion path ' + item.name + '. Click to open the hosts that use this path.'; },
    sourceTitle: function (item) { return 'Sourcetype family ' + item.name + '. Click to open the sourcetypes in this family.'; },
    indexTitle: function (item) { return 'Index ' + item.name + '. Click to open the hosts and sourcetypes that land here.'; }
  };
  var detailView = {
    sourceLimit: 16,
    sourceTitle: function (item) {
      return item.name + '. ' + Math.round(item.events).toLocaleString() + ' events. This is a sourcetype from the indexed events. WinEventLog and XmlWinEventLog are split by the event-log channel in the source. Click to follow it.';
    }
  };
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
  function zoomed() {
    return !!(zoom.environment || zoom.family || zoom.ingest || zoom.index);
  }
  function baseRows() {
    var source = zoomed() ? (detailRows || []) : mapRows;
    return source.filter(function (row) {
      if (focus.endpoint && focus.endpoint !== '__more__' && (row.endpoint || 'unknown') !== focus.endpoint) return false;
      if (focus.host && focus.host !== '__more__' && row.data_source !== focus.host) return false;
      if (focus.category && row.category !== focus.category) return false;
      if (focus.network && row.network !== focus.network) return false;
      if (focus.ingest && row.ingest_method !== focus.ingest) return false;
      if (focus.index && row.splunk_index !== focus.index) return false;
      return true;
    });
  }
  function topNames(rows, key) {
    var totals = {};
    rows.forEach(function (row) {
      var name = row[key] || 'unknown';
      totals[name] = (totals[name] || 0) + (Number(row.events) || 0);
    });
    return Object.keys(totals).sort(function (a, b) { return totals[b] - totals[a]; }).slice(0, 8);
  }
  function selection() {
    var rows = baseRows();
    var topEp = topNames(rows, 'endpoint');
    var topHost = topNames(rows, 'data_source');
    return rows.filter(function (row) {
      if (focus.endpoint === '__more__' && topEp.indexOf(row.endpoint || 'unknown') >= 0) return false;
      if (focus.host === '__more__' && topHost.indexOf(row.data_source || 'unknown') >= 0) return false;
      return true;
    });
  }
  function scopeLabel() {
    var parts = [];
    if (zoom.environment) parts.push(zoom.environment);
    if (zoom.ingest) parts.push(zoom.ingest);
    if (zoom.family) parts.push(zoom.family);
    if (zoom.index) parts.push(zoom.index);
    var inner = pathLabel();
    if (inner) parts.push(inner);
    return parts.join(' · ');
  }
  function pathLabel() {
    var parts = [];
    if (focus.host && focus.host !== '__more__') parts.push(focus.host);
    if (focus.ingest) parts.push(focus.ingest);
    if (focus.endpoint && focus.endpoint !== '__more__') parts.push(focus.endpoint);
    if (focus.index) parts.push(focus.index);
    if (focus.network) parts.push(focus.network);
    if (focus.category) parts.push(focus.category);
    return parts.join(' · ');
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
    if ((col === 'host' || col === 'endpoint') && name === '__more__') {
      var moreKey = col === 'host' ? 'host' : 'endpoint';
      focus[moreKey] = focus[moreKey] === '__more__' ? '' : '__more__';
      apply();
      return;
    }
    if (col === 'endpoint') {
      var clear = focus.endpoint === name && !focus.index && !focus.host && !focus.ingest;
      focus = { category: '', network: '', ingest: '', index: '', host: '', endpoint: clear ? '' : name };
    } else if (col === 'host') {
      var same = focus.host === name && !focus.endpoint && !focus.ingest && !focus.index;
      focus = { category: '', network: '', ingest: '', index: '', endpoint: '', host: same ? '' : name };
    } else if (col === 'network') {
      var sameNet = focus.network === name && !focus.host && !focus.endpoint && !focus.index && !focus.ingest;
      focus = { category: '', network: sameNet ? '' : name, ingest: '', index: '', host: '', endpoint: '' };
    } else if (col === 'ingest_method') {
      var sameIn = focus.ingest === name && !focus.host && !focus.endpoint && !focus.index;
      focus = { category: '', network: '', ingest: sameIn ? '' : name, index: '', host: '', endpoint: '' };
    } else if (col === 'splunk_index') {
      var sameIdx = focus.index === name && !focus.host && !focus.endpoint && !focus.ingest;
      focus = { category: '', network: '', ingest: '', index: sameIdx ? '' : name, host: '', endpoint: '' };
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
  function paintMapChrome() {
    var title = document.getElementById('mapTitle');
    var note = document.getElementById('mapNote');
    var crumb = document.getElementById('mapCrumb');
    if (!zoomed() && !focused()) {
      title.textContent = 'Site → ingestion path → sourcetype family → index';
      note.textContent = 'Hundreds of hosts and sourcetypes stay grouped. A site is a shared domain, or an IPv4 /16. A sourcetype family is a known product, or the prefix of the sourcetype. The busiest eight of each are named. Everything else is one Other node, and its count still includes that tail. Hover a node to light its path. Click a site, a path, a family, or an index to open the hosts and sourcetypes inside it.';
      crumb.textContent = 'Estate view';
      return;
    }
    var label = scopeLabel() || 'this selection';
    title.textContent = 'Host → ingestion path → sourcetype → index';
    note.textContent = 'Hosts and sourcetypes inside ' + label + '. Each sourcetype is the name Splunk indexed. For the Windows add-on, WinEventLog and XmlWinEventLog stay one family here, and each event-log channel comes from the source, so Security, System, and any other channel in this estate are separate. Hover a node to light its path. Choose Overview to return to the estate.';
    crumb.innerHTML = '<a href="#" id="mapHome">Overview</a> · ' + Health.esc(label);
    var home = document.getElementById('mapHome');
    if (home) home.addEventListener('click', function (event) {
      event.preventDefault();
      if (zoomed()) clearZoom();
      else {
        focus = { category: '', network: '', ingest: '', index: '', host: '', endpoint: '' };
        apply();
      }
    });
  }
  function clearZoom() {
    detailRequest += 1;
    zoom = { environment: '', family: '', ingest: '', index: '' };
    detailRows = null;
    detailError = '';
    focus = { category: '', network: '', ingest: '', index: '', host: '', endpoint: '' };
    apply();
  }
  function openGroup(col, name) {
    if (!name || name === '__more__') return;
    zoom = { environment: '', family: '', ingest: '', index: '' };
    if (col === 'host' || col === 'data_source') zoom.environment = name;
    else if (col === 'ingest_method') zoom.ingest = name;
    else if (col === 'endpoint') zoom.family = name;
    else if (col === 'splunk_index') zoom.index = name;
    else return;
    focus = { category: '', network: '', ingest: '', index: '', host: '', endpoint: '' };
    loadDetail();
  }
  function loadDetail() {
    var id = ++detailRequest;
    detailRows = null;
    detailError = '';
    paintMapChrome();
    document.getElementById('map').innerHTML = '<p class="note">Loading the hosts and sourcetypes in this selection…</p>';
    Health.query('topo_detail', {
      tok_topo_environment: zoom.environment || '*',
      tok_topo_family: zoom.family || '*',
      tok_topo_ingest: zoom.ingest || '*',
      tok_topo_index: zoom.index || '*'
    }).then(function (rows) {
      if (id !== detailRequest) return;
      detailRows = rows || [];
      apply();
    }).catch(function (error) {
      if (id !== detailRequest) return;
      detailError = error && error.message ? error.message : String(error);
      detailRows = [];
      apply();
    });
  }
  function drawMap() {
    paintMapChrome();
    if (!zoomed() && macroError) {
      Health.fail(document.getElementById('map'), macroError);
      document.getElementById('mapHover').textContent = macroError;
      return;
    }
    if (zoomed() && detailError) {
      Health.fail(document.getElementById('map'), detailError);
      document.getElementById('mapHover').textContent = detailError;
      return;
    }
    var macro = !zoomed() && !focused();
    var rows = macro ? macroRows : (focused() ? baseRows() : (detailRows || []));
    var selected = macro ? {} : {
      endpoint: focus.endpoint === '__more__' ? '' : focus.endpoint,
      network: focus.network,
      ingest: focus.ingest,
      index: focus.index,
      host: focus.host === '__more__' ? '' : focus.host
    };
    if (!rows.length) {
      document.getElementById('map').innerHTML = '<p class="note">' + (zoomed()
        ? 'Nothing in this group sent events in the last 24 hours. Choose Overview to return to the estate.'
        : 'No events in the last 24 hours.') + '</p>';
      return;
    }
    Charts.sourceFan(document.getElementById('map'), rows, selected, macro ? openGroup : pick, function (text) {
      document.getElementById('mapHover').textContent = text;
    }, macro ? macroView : detailView);
  }
  function pathColumns() {
    return [
      { key: 'data_source', label: 'Host' },
      { key: 'ingest_method', label: 'Ingestion path' },
      { key: 'endpoint', label: 'Sourcetype' },
      { key: 'splunk_index', label: 'Index' },
      { key: 'events', label: 'Events (24h)' }
    ];
  }
  function showPath(rows) {
    var list = rows.slice().sort(function (a, b) { return (Number(b.events) || 0) - (Number(a.events) || 0); });
    if (!list.length) {
      document.getElementById('missing').innerHTML = '<p class="note">Nothing feeds this selection. Click it again to restore the full map.</p>';
      return;
    }
    Health.table(document.getElementById('missing'), list.slice(0, 80), pathColumns(), function (row) { pick('host', row.data_source); });
  }
  function showMissing(rows) {
    var list = rows.slice().sort(function (a, b) { return (Number(b.events) || 0) - (Number(a.events) || 0); });
    if (!list.length) {
      document.getElementById('missing').innerHTML = '<p class="note">Every source is already drawn. There is nothing in the +N list.</p>';
      return;
    }
    Health.table(document.getElementById('missing'), list.slice(0, 80), pathColumns(), function (row) {
      pick(focus.host === '__more__' ? 'host' : 'endpoint', focus.host === '__more__' ? row.data_source : row.endpoint);
    });
  }
  function paintLists() {
    var chosen = selection();
    var hosts = {};
    chosen.forEach(function (row) { if (row.data_source) hosts[row.data_source] = 1; });
    var hostList = Object.keys(hosts);
    var pathRows = paths;
    var tcpRows = tcpAll;
    if (focus.host && focus.host !== '__more__') {
      pathRows = paths.filter(function (row) { return row.data_source === focus.host; });
      tcpRows = tcpAll.filter(function (row) { return row.data_source === focus.host; });
    } else if (focused() && mapRows.length) {
      pathRows = paths.filter(function (row) {
        return hostList.indexOf(row.data_source) >= 0 && (!focus.index || row.splunk_index === focus.index);
      });
      tcpRows = tcpAll.filter(function (row) { return hostList.indexOf(row.data_source) >= 0; });
    }
    var one = (focus.host && focus.host !== '__more__') ? focus.host : (hostList.length === 1 ? hostList[0] : '');
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
    var missingTitle = document.getElementById('missingTitle');
    if (focus.endpoint === '__more__' || focus.host === '__more__') {
      missingTitle.textContent = 'Not drawn' + (pathLabel() ? ' for ' + pathLabel() : '');
      showMissing(selection());
    } else if (zoomed() || focused()) {
      missingTitle.textContent = 'Path for ' + (scopeLabel() || 'this selection');
      showPath(focused() ? baseRows() : (detailRows || []));
    } else {
      missingTitle.textContent = 'Not drawn on the map';
      document.getElementById('missing').innerHTML = '<p class="note">Click a site, a path, a family, or an index to open it. The hosts and sourcetypes in that group are listed here. Click +N inside a group to list what did not fit on the drawing.</p>';
    }
    if (focus.host && focus.host !== '__more__') loadHost(focus.host);
    else if (focus.endpoint === '__more__' || focus.host === '__more__') showDirectory(selection());
    else if (focus.endpoint || focus.category || focus.network || focus.ingest || focus.index) loadGroup();
    else if (zoomed()) showDirectory(detailRows || []);
    else showDirectory(mapRows);
  }
  function settled(promise) {
    return promise.then(function (rows) { return { rows: rows }; }, function (error) { return { error: error }; });
  }
  Promise.all([
    settled(Health.query('topo_paths')),
    settled(Health.query('tcpin')),
    settled(Health.query('topo_map')),
    settled(Health.query('topo_macro'))
  ]).then(function (res) {
    if (!res[0].rows || !res[1].rows) {
      Health.fail(document.getElementById('stats'), (res[0].error || res[1].error || 'The topology searches could not run.'));
      return;
    }
    paths = res[0].rows;
    tcpAll = res[1].rows;
    mapRows = res[2].rows || [];
    mapError = res[2].error ? (res[2].error.message || String(res[2].error)) : '';
    macroRows = res[3].rows || [];
    macroError = res[3].error ? (res[3].error.message || String(res[3].error)) : '';
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
  function countStatus(rows, names) {
    return rows.filter(function (row) { return names.indexOf(row.status) >= 0; }).length;
  }
  Health.query('feed_catalog').then(function (rows) {
    if (!rows.length) {
      document.getElementById('feedStats').innerHTML = '';
      document.getElementById('feeds').innerHTML = '<p class="note">No feeds in lookups/feed_catalog.csv. Add an index row with expected_state=active.</p>';
      return;
    }
    Health.stats(document.getElementById('feedStats'), [
      { val: countStatus(rows, ['SILENT', 'NO EVENTS IN WINDOW']), lbl: 'Silent or missing', kind: 'bad' },
      { val: countStatus(rows, ['SOURCETYPE DRIFT']), lbl: 'Sourcetype drift', kind: 'bad' },
      { val: countStatus(rows, ['new in last 7d']), lbl: 'New in last 7 days', kind: 'warn' }
    ]);
    Health.table(document.getElementById('feeds'), rows, [
      { key: 'index', label: 'Index' }, { key: 'sourcetype', label: 'Sourcetype' }, { key: 'source', label: 'Source' },
      { key: 'status', label: 'Status' }, { key: 'last_event', label: 'Last event' },
      { key: 'silent_min', label: 'Silent minutes' }, { key: 'expected_sourcetype', label: 'Expected sourcetype' },
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
    else if (!res[1].rows.length) document.getElementById('quarantineRows').innerHTML = '<p class="note">No events in the catch-all indexes from the feed catalog.</p>';
    else Health.table(document.getElementById('quarantineRows'), res[1].rows, [
      { key: 'sourcetype', label: 'Sourcetype' }, { key: 'source', label: 'Source' },
      { key: 'count', label: 'Events' }, { key: 'first_event', label: 'First event' }, { key: 'last_event', label: 'Last event' }
    ]);
  });
})();

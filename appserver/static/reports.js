(function () {
  var QUEUE_COLUMNS = [
    { key: 'severity', label: 'Severity' }, { key: 'issue', label: 'Issue' }, { key: 'entity', label: 'Entity' },
    { key: 'fix', label: 'Fix' }, { key: 'recurring', label: 'Recurring' }, { key: 'confidence', label: 'Confidence' },
    { key: 'status', label: 'Status' }
  ];
  var AREA_COLUMNS = [
    { key: 'area', label: 'Area' }, { key: 'status', label: 'Status' }, { key: 'detail', label: 'Why' }
  ];
  var BOOKS = {
    summary: {
      title: 'Executive overview',
      sections: [
        { title: 'Status by area', query: 'areas', columns: AREA_COLUMNS },
        { title: 'Daily ingestion vs 7-day average (GB)', query: 'license_daily' },
        { title: 'Events indexed, last 15 minutes', query: 'live' },
        { title: 'Open agent findings', query: 'agent_counts' },
        { title: 'Top indexes by license usage (GB, last 7 days)', query: 'top_indexes' },
        { title: 'Last hour vs the usual hour, by index', query: 'index_season' },
        { title: 'Empty hours by index', query: 'empty_hours' }
      ]
    },
    host: {
      title: 'Host Heartbeat & Instance Health',
      sections: [
        { title: 'Hosts by state', query: 'state_counts', host: true },
        { title: 'Last data received vs last internal heartbeat', query: 'phone_home', host: true },
        { title: 'Heartbeat vs this host usual gap', query: 'heartbeat_learned', host: true },
        { title: 'Last hour vs the same hour this week', query: 'host_season', host: true },
        { title: 'Ingestion latency, last 15 minutes (seconds)', query: 'latency', host: true },
        { title: 'Current volume vs 24-hour baseline', query: 'baseline', host: true },
        { title: 'Splunkd health by feature', query: 'features' },
        { title: 'Instance CPU and memory', query: 'introspection' },
        { title: 'Blocked ingestion queues', query: 'ingest_actions' }
      ]
    },
    hec: {
      title: 'HEC Token Performance',
      sections: [
        { title: 'Token totals', query: 'hec_totals' },
        { title: 'Token state', query: 'hec_state' },
        { title: 'Events over time', query: 'hec_time' },
        { title: 'HTTP handler', query: 'hec_handler' },
        { title: 'Token errors', query: 'hec_errors' },
        { title: 'HEC input errors', query: 'hec_input_errors' },
        { title: 'HEC token configuration load failures', query: 'hec_conf_load' },
        { title: 'Line-breaking warnings', query: 'parse_linebreak' },
        { title: 'Timestamp parse warnings', query: 'parse_time' },
        { title: 'Source, token, and index', query: 'hec_flow' }
      ]
    },
    sc4s: {
      title: 'SC4S Syslog & Edge/Ingest Processors',
      sections: [
        { title: 'Edge Processor summary', query: 'edge_summary' },
        { title: 'SC4S / syslog events', query: 'sc4s_time' },
        { title: 'Events reaching indexers', query: 'indexed' },
        { title: 'Events per syslog source', query: 'sc4s_hosts' },
        { title: 'SC4S issues', query: 'sc4s_errors' },
        { title: 'Edge Processor in vs out', query: 'edge_tp' },
        { title: 'Edge queue fill and export errors', query: 'edge_queue' },
        { title: 'Edge / ingest logs', query: 'edge_logs' },
        { title: 'Blocked ingestion queues', query: 'ingest_actions' }
      ]
    },
    topology: {
      title: 'Data Topology',
      sections: [
        { title: 'Sites, sourcetype families, and indexes', query: 'topo_macro' },
        { title: 'Category, network, ingest method, and index (24h)', query: 'topo_map' },
        { title: 'Top source, path, and index flows', query: 'topo_paths' },
        { title: 'Forwarder to indexer (tcpin)', query: 'tcpin' },
        { title: 'Feeds you expect', query: 'feed_catalog' },
        { title: 'Catch-all indexes by sourcetype and source', query: 'quarantine_rows' }
      ]
    },
    agent: {
      title: 'Data Quality Agent',
      sections: [
        { title: 'Queue health', query: 'agent_status', params: { tok_ask: 'all' } },
        { title: 'Work queue', query: 'agent_queue', params: { tok_ask: 'all' }, columns: QUEUE_COLUMNS },
        { title: 'Saved AI suggestions', query: 'agent_list', params: { tok_ai_list: 'show' } }
      ]
    }
  };
  var ORDER = ['summary', 'host', 'hec', 'sc4s', 'topology', 'agent'];
  var running = false;
  var fileName = '';

  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function when(date) {
    return date.getFullYear() + '-' + pad(date.getMonth() + 1) + '-' + pad(date.getDate())
      + ' ' + pad(date.getHours()) + ':' + pad(date.getMinutes()) + ':' + pad(date.getSeconds());
  }
  function fileWhen(date) {
    return date.getFullYear() + pad(date.getMonth() + 1) + pad(date.getDate())
      + '-' + pad(date.getHours()) + pad(date.getMinutes()) + pad(date.getSeconds());
  }
  function hostFilter() {
    var value = (document.getElementById('host').value || '*').trim();
    if (!/^[\w.:*\-]{1,128}$/.test(value)) {
      throw new Error('Host filter must be 1–128 characters: letters, numbers, dot, colon, star, or hyphen.');
    }
    return value;
  }
  function jobsFor(keys, filter) {
    var jobs = [];
    keys.forEach(function (key) {
      BOOKS[key].sections.forEach(function (section) {
        var params = {};
        Object.keys(section.params || {}).forEach(function (name) { params[name] = section.params[name]; });
        if (section.host) params.host_filter = filter;
        jobs.push({ book: key, title: section.title, query: section.query, params: params, columns: section.columns });
      });
    });
    return jobs;
  }
  function runPool(jobs) {
    var results = new Array(jobs.length);
    var cursor = 0;
    var active = 0;
    var finished = 0;
    var status = document.getElementById('status');
    if (!jobs.length) return Promise.resolve(results);
    return new Promise(function (resolve) {
      function launch() {
        while (active < 3 && cursor < jobs.length) {
          (function (index) {
            active += 1;
            status.textContent = 'Running ' + jobs[index].title + ' (' + (finished + active) + ' of ' + jobs.length + ')';
            Health.query(jobs[index].query, jobs[index].params).then(function (rows) {
              results[index] = { ok: true, rows: rows };
            }, function (error) {
              results[index] = { ok: false, error: error };
            }).then(function () {
              active -= 1;
              finished += 1;
              if (finished === jobs.length) resolve(results);
              else launch();
            });
          })(cursor);
          cursor += 1;
        }
      }
      launch();
    });
  }
  function addTable(parent, title, result, columns) {
    var block = document.createElement('div');
    block.className = 'section';
    var heading = document.createElement('h2');
    heading.className = 'section-title';
    heading.textContent = title;
    var body = document.createElement('div');
    block.appendChild(heading);
    block.appendChild(body);
    parent.appendChild(block);
    if (!result || !result.ok) Health.fail(body, (result && result.error) || 'The search did not return.');
    else Health.table(body, result.rows, columns);
  }
  function renderBook(parent, key, filter, stamp, results, offset) {
    var book = BOOKS[key];
    var article = document.createElement('article');
    article.className = 'report-block';
    var head = document.createElement('div');
    head.className = 'report-head';
    var title = document.createElement('h2');
    title.textContent = book.title;
    var meta = document.createElement('p');
    meta.className = 'note';
    meta.textContent = 'Generated ' + when(stamp)
      + (book.sections.some(function (section) { return section.host; }) ? ' · host filter ' + filter : '');
    head.appendChild(title);
    head.appendChild(meta);
    article.appendChild(head);
    book.sections.forEach(function (section, index) {
      addTable(article, section.title, results[offset + index], section.columns);
    });
    parent.appendChild(article);
    return offset + book.sections.length;
  }
  function downloadHtml() {
    var output = document.getElementById('output');
    if (!output.innerHTML) return;
    var doc = '<!DOCTYPE html><html><head><meta charset="utf-8"><title>'
      + Health.esc(fileName) + '</title><style>'
      + 'body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif;background:#0f1419;color:#e6edf3;margin:0;padding:24px;}'
      + 'h2{font-size:1.2rem;margin:0 0 4px;} .note{color:#8b949e;font-size:0.8rem;}'
      + '.section-title{font-size:0.72rem;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;color:#8b949e;margin:0 0 12px;padding-bottom:8px;border-bottom:1px solid #2d3a4f;}'
      + 'table{width:100%;border-collapse:collapse;font-size:0.8rem;} th,td{text-align:left;padding:6px 10px;border-bottom:1px solid #2d3a4f;vertical-align:top;}'
      + 'th{color:#8b949e;font-size:0.7rem;text-transform:uppercase;} .note.error{color:#f85149;}'
      + '.pill{display:inline-block;padding:2px 8px;border-radius:999px;font-size:0.7rem;font-weight:600;}'
      + '.pill.good{color:#3fb950;background:#3fb95022;} .pill.bad{color:#f85149;background:#f8514922;}'
      + '.pill.warn{color:#d29922;background:#d2992222;} .pill.neutral{color:#8b949e;background:#8b949e22;}'
      + '.report-block{margin:0 0 32px;} .report-banner{font-size:1rem;margin:20px 0 4px;} .section{margin-bottom:28px;}'
      + '@media print{body{background:#fff;color:#111;} th,td,.section-title,.note{color:#111;border-color:#ccc;}}'
      + '</style></head><body>' + output.innerHTML + '</body></html>';
    var blob = new Blob([doc], { type: 'text/html;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = fileName;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  document.getElementById('go').addEventListener('click', function () {
    if (running) return;
    var filter;
    try { filter = hostFilter(); } catch (error) {
      document.getElementById('status').textContent = error.message;
      return;
    }
    var scope = document.getElementById('scope').value;
    var keys = scope === 'overall' || scope === 'each' ? ORDER : [scope];
    if (!BOOKS[keys[0]] && scope !== 'overall' && scope !== 'each') return;
    var jobs = jobsFor(keys, filter);
    var output = document.getElementById('output');
    output.textContent = '';
    document.getElementById('download').disabled = true;
    document.getElementById('print').disabled = true;
    running = true;
    document.getElementById('go').disabled = true;
    runPool(jobs).then(function (results) {
      var stamp = new Date();
      fileName = 'splunk-health-' + scope + '-' + fileWhen(stamp) + '.html';
      if (scope === 'overall') {
        var article = document.createElement('article');
        article.className = 'report-block';
        var head = document.createElement('div');
        head.className = 'report-head';
        var title = document.createElement('h2');
        title.textContent = 'Overall health';
        var meta = document.createElement('p');
        meta.className = 'note';
        meta.textContent = 'Generated ' + when(stamp) + ' · host filter ' + filter + ' · compilation of every dashboard';
        head.appendChild(title);
        head.appendChild(meta);
        article.appendChild(head);
        var offset = 0;
        keys.forEach(function (key) {
          var banner = document.createElement('h2');
          banner.className = 'report-banner';
          banner.textContent = BOOKS[key].title;
          article.appendChild(banner);
          BOOKS[key].sections.forEach(function (section) {
            addTable(article, section.title, results[offset], section.columns);
            offset += 1;
          });
        });
        output.appendChild(article);
      } else {
        var cursor = 0;
        keys.forEach(function (key) {
          cursor = renderBook(output, key, filter, stamp, results, cursor);
        });
      }
      var failed = results.filter(function (item) { return item && !item.ok; }).length;
      document.getElementById('status').textContent = 'Generated ' + when(stamp)
        + (failed ? ' · ' + failed + ' section' + (failed === 1 ? '' : 's') + ' failed' : '');
      document.getElementById('download').disabled = false;
      document.getElementById('print').disabled = false;
    }).catch(function (error) {
      document.getElementById('status').textContent = error && error.message ? error.message : 'The report could not be generated.';
    }).then(function () {
      running = false;
      document.getElementById('go').disabled = false;
    });
  });
  document.getElementById('download').addEventListener('click', downloadHtml);
  document.getElementById('print').addEventListener('click', function () { window.print(); });
})();

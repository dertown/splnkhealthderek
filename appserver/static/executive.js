/* Executive overview. Each panel loads on its own. */
var Executive = (function () {
  var links = {
    'Hosts & instances': 'host_heartbeat',
    'Data flow': 'data_topology',
    'HEC tokens': 'hec_performance',
    'SC4S & Edge': 'sc4s_edge'
  };
  var model = {
    worst: '…',
    worstKind: '',
    gb: '…',
    variance: '…',
    events: '…',
    findings: '…'
  };

  function kind(status) {
    return status === 'GREEN' ? 'ok' : status === 'RED' ? 'bad' : status === 'YELLOW' ? 'warn' : '';
  }

  function worstStatus(rows) {
    return rows.reduce(function (acc, row) {
      if (row.status === 'RED') return 'RED';
      if (acc === 'RED') return acc;
      if (row.status === 'YELLOW') return 'YELLOW';
      return acc;
    }, rows.length ? 'GREEN' : 'N/A');
  }

  function paintStats() {
    Health.stats(document.getElementById('stats'), [
      { val: model.worst, lbl: 'Overall health', kind: model.worstKind },
      { val: model.gb, lbl: 'Ingestion GB, last full day' },
      { val: model.variance, lbl: 'Vs 7-day average' },
      { val: model.events, lbl: 'Events indexed, 15m' },
      { val: model.findings, lbl: 'Agent findings open' }
    ]);
  }

  function paintVerdict(rows) {
    var node = document.getElementById('verdict');
    var worst = worstStatus(rows);
    model.worst = worst;
    model.worstKind = kind(worst);
    paintStats();
    node.className = 'verdict ' + kind(worst);
    if (!rows.length) {
      node.innerHTML = '<h3>No signal yet</h3><p>The area rollup returned no rows.</p>';
      return;
    }
    var title = worst === 'RED' ? 'Needs attention' : worst === 'YELLOW' ? 'Watch' : 'Healthy';
    var trouble = rows.filter(function (row) { return row.status === 'RED' || row.status === 'YELLOW'; });
    var body = trouble.length
      ? trouble.map(function (row) {
        return '<p><strong>' + Health.esc(row.area) + ' is ' + Health.esc(row.status) + '.</strong> ' + Health.esc(row.detail || '') + '</p>';
      }).join('')
      : '<p>No area is yellow or red.</p>';
    node.innerHTML = '<h3>' + title + '</h3>' + body;
  }

  function paintAreas(rows, findings) {
    var cards = rows.map(function (row) {
      var view = links[row.area] || 'executive_overview';
      var tone = kind(row.status);
      return '<a class="card ' + tone + '" href="' + Health.page(view) + '"><h3>' + Health.esc(row.area) + '</h3><p>'
        + Health.esc(row.detail || row.status) + '</p><div class="arrow">' + Health.esc(row.status) + ' · Open</div></a>';
    }).join('');
    var agentText = findings === undefined
      ? 'Counting open findings.'
      : findings === null
        ? 'The finding count did not return. The work queue is still available.'
        : String(findings) + ' open findings.';
    cards += '<a class="card" href="' + Health.page('data_quality_agent') + '"><h3>Data Quality Agent</h3><p>'
      + Health.esc(agentText) + '</p><div class="arrow">Open the work queue</div></a>';
    document.getElementById('areas').innerHTML = cards;
  }

  function start() {
    Health.link('queue', 'data_quality_agent');
    paintStats();
    var areas = [];
    var findingsText;
    Health.query('areas').then(function (rows) {
      areas = rows || [];
      paintVerdict(areas);
      paintAreas(areas, findingsText);
      Health.table(document.getElementById('areaTable'), areas, [
        { key: 'area', label: 'Area' },
        { key: 'status', label: 'Status' },
        { key: 'detail', label: 'Why' }
      ]);
    }, function (error) {
      Health.fail(document.getElementById('verdict'), error);
      Health.fail(document.getElementById('areas'), error);
      Health.fail(document.getElementById('areaTable'), error);
      model.worst = 'N/A';
      paintStats();
    });
    Health.query('license_daily').then(function (rows) {
      var today = rows.length ? rows[rows.length - 1] : {};
      model.gb = today.daily_GB === undefined || today.daily_GB === null || today.daily_GB === '' ? '0' : String(today.daily_GB);
      model.variance = (today.variance_pct === undefined || today.variance_pct === null || today.variance_pct === '' ? '0' : String(today.variance_pct)) + '%';
      paintStats();
      Charts.line(document.getElementById('ingest'), rows, '_time', ['daily_GB', 'ma_7d'], {
        daily_GB: 'GB that day',
        ma_7d: '7-day average'
      });
    }, function (error) { Health.fail(document.getElementById('ingest'), error); });
    Health.query('live').then(function (rows) {
      model.events = String((rows[0] || {}).events || '0');
      paintStats();
    }, function () {
      model.events = 'N/A';
      paintStats();
    });
    Health.query('agent_counts').then(function (rows) {
      model.findings = String((rows[0] || {}).open_findings || '0');
      findingsText = model.findings;
      paintStats();
      if (areas.length) paintAreas(areas, findingsText);
    }, function () {
      model.findings = 'N/A';
      findingsText = null;
      paintStats();
      if (areas.length) paintAreas(areas, findingsText);
    });
    Health.query('top_indexes').then(function (rows) {
      Charts.pie(document.getElementById('pie'), rows, 'index', 'GB');
    }, function (error) { Health.fail(document.getElementById('pie'), error); });
    Health.query('empty_hours').then(function (rows) {
      if (!rows.length) {
        document.getElementById('emptyHours').innerHTML = '<p class="note">No active feeds yet. In the feed list, set a row state to active and name the index.</p>';
        return;
      }
      Health.table(document.getElementById('emptyHours'), rows, [
        { key: 'index', label: 'Index' },
        { key: 'hours', label: 'Hours' },
        { key: 'empty_hours', label: 'Empty hours' },
        { key: 'empty_pct', label: 'Empty %' },
        { key: 'last_empty', label: 'Last empty hour' }
      ]);
    }, function (error) { Health.fail(document.getElementById('emptyHours'), error); });
  }

  return { start: start, worstStatus: worstStatus };
})();
Executive.start();

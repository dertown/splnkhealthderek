/* Small dependency-free SVG charts for the health pages. */
var Charts = (function () {
  var COLORS = ['#58a6ff', '#3fb950', '#d29922', '#f85149', '#a371f7', '#79c0ff', '#ff7b72', '#56d364'];

  function esc(value) {
    return String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function el(node, svg) {
    node.innerHTML = '<div class="chart">' + svg + '</div>';
  }

  function line(node, rows, xKey, yKeys) {
    if (!rows.length) { node.innerHTML = '<p class="note">No data for this chart.</p>'; return; }
    var width = 760, height = 240, pad = 28;
    var max = 0;
    rows.forEach(function (row) {
      yKeys.forEach(function (key) { var n = Number(row[key]); if (!isNaN(n) && n > max) max = n; });
    });
    if (max === 0) max = 1;
    var step = rows.length > 1 ? (width - 2 * pad) / (rows.length - 1) : 0;
    var yOf = function (value) { return height - pad - (Number(value) || 0) / max * (height - 2 * pad); };
    var svg = '<svg viewBox="0 0 ' + width + ' ' + height + '" width="100%">';
    yKeys.forEach(function (key, series) {
      var points = rows.map(function (row, index) { return (pad + index * step) + ',' + yOf(row[key]); }).join(' ');
      svg += '<polyline fill="none" stroke="' + COLORS[series % COLORS.length] + '" stroke-width="2" points="' + points + '"/>';
    });
    var first = rows[0][xKey], last = rows[rows.length - 1][xKey];
    svg += '<text x="' + pad + '" y="' + (height - 8) + '" fill="#8b949e" font-size="11">' + esc(first || '') + '</text>';
    svg += '<text x="' + (width - pad) + '" y="' + (height - 8) + '" fill="#8b949e" font-size="11" text-anchor="end">' + esc(last || '') + '</text>';
    svg += '</svg>';
    yKeys.forEach(function (key, series) {
      svg += '<span class="pill" style="color:' + COLORS[series % COLORS.length] + ';margin-right:8px;">' + esc(key) + '</span>';
    });
    el(node, svg);
  }

  function pie(node, rows, labelKey, valueKey) {
    var total = rows.reduce(function (sum, row) { return sum + (Number(row[valueKey]) || 0); }, 0);
    if (!rows.length || total <= 0) { node.innerHTML = '<p class="note">No data for this chart.</p>'; return; }
    var cx = 120, cy = 120, radius = 100, inner = 58;
    var angle = -Math.PI / 2;
    var svg = '<svg viewBox="0 0 240 240" width="240" height="240">';
    rows.forEach(function (row, index) {
      var share = (Number(row[valueKey]) || 0) / total;
      var next = angle + share * Math.PI * 2;
      var large = share > 0.5 ? 1 : 0;
      var path = 'M ' + (cx + Math.cos(angle) * radius) + ' ' + (cy + Math.sin(angle) * radius)
        + ' A ' + radius + ' ' + radius + ' 0 ' + large + ' 1 ' + (cx + Math.cos(next) * radius) + ' ' + (cy + Math.sin(next) * radius)
        + ' L ' + (cx + Math.cos(next) * inner) + ' ' + (cy + Math.sin(next) * inner)
        + ' A ' + inner + ' ' + inner + ' 0 ' + large + ' 0 ' + (cx + Math.cos(angle) * inner) + ' ' + (cy + Math.sin(angle) * inner) + ' Z';
      svg += '<path d="' + path + '" fill="' + COLORS[index % COLORS.length] + '"><title>' + esc(row[labelKey]) + ' ' + Math.round(share * 100) + '%</title></path>';
      angle = next;
    });
    svg += '</svg>';
    var legend = rows.map(function (row, index) {
      return '<div><span class="pill" style="color:' + COLORS[index % COLORS.length] + ';">' + esc(row[labelKey]) + '</span> '
        + esc(row[valueKey]) + ' GB</div>';
    }).join('');
    el(node, '<div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap;">' + svg + '<div>' + legend + '</div></div>');
  }

  function flow(node, rows, columns, valueKey) {
    if (!rows.length) { node.innerHTML = '<p class="note">No data for this flow.</p>'; return; }
    var stages = columns.map(function () { return {}; });
    rows.forEach(function (row) {
      columns.forEach(function (col, index) {
        var name = row[col] || 'unknown';
        stages[index][name] = (stages[index][name] || 0) + (Number(row[valueKey]) || 0);
      });
    });
    var names = stages.map(function (stage) { return Object.keys(stage).sort(function (a, b) { return stage[b] - stage[a]; }).slice(0, 12); });
    var height = Math.max.apply(null, names.map(function (list) { return list.length; })) * 28 + 20;
    var width = 760, colWidth = width / columns.length;
    var svg = '<svg viewBox="0 0 ' + width + ' ' + height + '" width="100%">';
    var pos = names.map(function (list) {
      var map = {};
      list.forEach(function (name, index) { map[name] = 16 + index * 28; });
      return map;
    });
    for (var stage = 0; stage < columns.length - 1; stage++) {
      var links = {};
      rows.forEach(function (row) {
        var from = row[columns[stage]] || 'unknown';
        var to = row[columns[stage + 1]] || 'unknown';
        if (pos[stage][from] === undefined || pos[stage + 1][to] === undefined) return;
        var key = from + '->' + to;
        links[key] = (links[key] || 0) + (Number(row[valueKey]) || 0);
      });
      var max = Math.max.apply(null, Object.keys(links).map(function (key) { return links[key]; }).concat([1]));
      Object.keys(links).forEach(function (key) {
        var parts = key.split('->');
        var y1 = pos[stage][parts[0]], y2 = pos[stage + 1][parts[1]];
        svg += '<path d="M ' + (colWidth * stage + 150) + ' ' + y1 + ' C ' + (colWidth * stage + colWidth / 2 + 75) + ' ' + y1
          + ', ' + (colWidth * (stage + 1) - colWidth / 2 + 10) + ' ' + y2 + ', ' + (colWidth * (stage + 1) + 10) + ' ' + y2
          + '" stroke="#58a6ff" stroke-opacity="0.35" stroke-width="' + Math.max(1, links[key] / max * 10) + '" fill="none"/>';
      });
    }
    names.forEach(function (list, stage) {
      list.forEach(function (name) {
        svg += '<text x="' + (colWidth * stage + 10) + '" y="' + (pos[stage][name] + 4) + '" fill="#e6edf3" font-size="12">' + esc(name) + '</text>';
      });
    });
    svg += '</svg>';
    el(node, svg);
  }

  return { line: line, pie: pie, flow: flow };
})();

/* Small dependency-free SVG charts for the health pages. */
var Charts = (function () {
  var COLORS = ['#58a6ff', '#3fb950', '#d29922', '#f85149', '#a371f7', '#79c0ff', '#ff7b72', '#56d364'];

  function esc(value) {
    return String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function labelFont(name) {
    var n = String(name).length;
    if (n <= 8) return 16;
    if (n <= 14) return 14;
    if (n <= 22) return 13;
    if (n <= 32) return 12;
    return 11;
  }

  function labelPx(name, size) {
    return Math.ceil(String(name).length * (size || labelFont(name)) * 0.68);
  }

  function fitText(name, room) {
    var size = labelFont(name);
    var text = String(name);
    if (labelPx(text, size) <= room) return { text: text, size: size };
    while (text.length > 1 && labelPx(text + '\u2026', size) > room) text = text.slice(0, -1);
    return { text: text + '\u2026', size: size };
  }

  function el(node, svg) {
    node.innerHTML = '<div class="chart">' + svg + '</div>';
  }

  function line(node, rows, xKey, yKeys, labels) {
    if (!rows.length) { node.innerHTML = '<p class="note">No data for this chart.</p>'; return; }
    var width = 760, height = 240, pad = 28;
    var max = 0;
    function missing(value) { return value === null || value === undefined || value === '' || isNaN(Number(value)); }
    rows.forEach(function (row) {
      yKeys.forEach(function (key) {
        if (missing(row[key])) return;
        var n = Number(row[key]);
        if (n > max) max = n;
      });
    });
    if (max === 0) max = 1;
    var step = rows.length > 1 ? (width - 2 * pad) / (rows.length - 1) : 0;
    var yOf = function (value) { return height - pad - Number(value) / max * (height - 2 * pad); };
    var svg = '<svg viewBox="0 0 ' + width + ' ' + height + '" width="100%">';
    yKeys.forEach(function (key, series) {
      var segment = [];
      function flush() {
        if (segment.length < 2) { segment = []; return; }
        var dash = key.indexOf('bound') >= 0 ? ' stroke-dasharray="6 4"' : '';
        svg += '<polyline fill="none" stroke="' + COLORS[series % COLORS.length] + '" stroke-width="2"' + dash + ' points="' + segment.join(' ') + '"/>';
        segment = [];
      }
      rows.forEach(function (row, index) {
        if (missing(row[key])) flush();
        else segment.push((pad + index * step) + ',' + yOf(row[key]));
      });
      flush();
    });
    var first = rows[0][xKey], last = rows[rows.length - 1][xKey];
    svg += '<text x="' + pad + '" y="' + (height - 8) + '" fill="#8b949e" font-size="11">' + esc(first || '') + '</text>';
    svg += '<text x="' + (width - pad) + '" y="' + (height - 8) + '" fill="#8b949e" font-size="11" text-anchor="end">' + esc(last || '') + '</text>';
    svg += '</svg>';
    yKeys.forEach(function (key, series) {
      svg += '<span class="pill" style="color:' + COLORS[series % COLORS.length] + ';margin-right:8px;">' + esc((labels && labels[key]) || key) + '</span>';
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

  function flow(node, rows, columns, valueKey, selected, onSelect) {
    if (!rows.length) { node.innerHTML = '<p class="note">No data for this flow.</p>'; return; }
    var stages = columns.map(function () { return {}; });
    rows.forEach(function (row) {
      columns.forEach(function (col, index) {
        var name = row[col] || 'unknown';
        stages[index][name] = (stages[index][name] || 0) + (Number(row[valueKey]) || 0);
      });
    });
    var names = stages.map(function (stage) {
      return Object.keys(stage).sort(function (a, b) { return stage[b] - stage[a]; }).slice(0, 12);
    });
    if (selected) {
      rows.forEach(function (row) {
        if ((row[columns[0]] || 'unknown') !== selected) return;
        columns.forEach(function (col, index) {
          var name = row[col] || 'unknown';
          if (names[index].indexOf(name) < 0) names[index].push(name);
        });
      });
    }
    var gap = 72;
    var rooms = names.map(function (list) {
      var room = 72;
      list.forEach(function (name) { room = Math.max(room, labelPx(name) + 12); });
      return Math.min(room, 360);
    });
    var xAt = [];
    var cursor = 16;
    rooms.forEach(function (room) {
      xAt.push(cursor);
      cursor += room + gap;
    });
    var width = Math.max(880, cursor - gap + 20);
    var rowH = 40;
    var height = Math.max.apply(null, names.map(function (list) { return list.length; })) * rowH + 28;
    var pos = names.map(function (list) {
      var map = {};
      list.forEach(function (name, index) { map[name] = 24 + index * rowH; });
      return map;
    });
    var hot = {};
    if (selected) {
      rows.forEach(function (row) {
        if ((row[columns[0]] || 'unknown') !== selected) return;
        columns.forEach(function (col, index) { hot[index + '\n' + (row[col] || 'unknown')] = 1; });
      });
    }
    function curve(stage, y1, y2) {
      var x1 = xAt[stage] + rooms[stage] + 8;
      var x2 = xAt[stage + 1] - 16;
      if (x2 < x1 + 24) x2 = x1 + 24;
      var mid = (x1 + x2) / 2;
      return 'M ' + x1 + ' ' + y1 + ' C ' + mid + ' ' + y1 + ', ' + mid + ' ' + y2 + ', ' + x2 + ' ' + y2;
    }
    function drawLinks(match, color, opacity) {
      var out = '';
      for (var stage = 0; stage < columns.length - 1; stage++) {
        var links = {};
        rows.forEach(function (row) {
          var sourceName = row[columns[0]] || 'unknown';
          if (match !== null && ((sourceName === selected) !== match)) return;
          var from = row[columns[stage]] || 'unknown';
          var to = row[columns[stage + 1]] || 'unknown';
          if (pos[stage][from] === undefined || pos[stage + 1][to] === undefined) return;
          var key = from + '\n' + to;
          links[key] = (links[key] || 0) + (Number(row[valueKey]) || 0);
        });
        var amounts = Object.keys(links).map(function (key) { return links[key]; });
        var max = Math.max.apply(null, amounts.concat([1]));
        Object.keys(links).forEach(function (key) {
          var parts = key.split('\n');
          out += '<path d="' + curve(stage, pos[stage][parts[0]], pos[stage + 1][parts[1]])
            + '" stroke="' + color + '" stroke-opacity="' + opacity + '" stroke-width="'
            + Math.max(1.25, Math.min(4, links[key] / max * 4)) + '" fill="none" stroke-linecap="butt"/>';
        });
      }
      return out;
    }
    var svg = '<svg viewBox="0 0 ' + width + ' ' + height + '" width="100%" style="min-width:' + width + 'px" role="img">';
    if (!selected) svg += drawLinks(null, '#58a6ff', '0.35');
    else {
      svg += drawLinks(false, '#58a6ff', '0.12');
      svg += drawLinks(true, '#58a6ff', '0.95');
    }
    names.forEach(function (list, stage) {
      list.forEach(function (name) {
        var onPath = !selected || hot[stage + '\n' + name];
        var fill = !selected || onPath ? '#e6edf3' : '#6e7681';
        if (selected && stage === 0 && name === selected) fill = '#58a6ff';
        else if (selected && onPath) fill = '#79c0ff';
        var pick = stage === 0 ? ' data-pick="' + esc(name).replace(/"/g, '&quot;') + '"' : '';
        var weight = selected && onPath ? ' font-weight="700"' : '';
        var fitted = fitText(name, rooms[stage] - 8);
        svg += '<text x="' + xAt[stage] + '" y="' + (pos[stage][name] + 4) + '" fill="' + fill
          + '" font-size="' + fitted.size + '"' + weight + pick + '><title>' + esc(name) + '</title>' + esc(fitted.text) + '</text>';
      });
    });
    svg += '</svg>';
    el(node, svg);
    if (onSelect) {
      Array.prototype.forEach.call(node.querySelectorAll('text[data-pick]'), function (text) {
        text.style.cursor = 'pointer';
        text.addEventListener('click', function () { onSelect(text.getAttribute('data-pick')); });
      });
    }
  }

  function topology(node, rows, columns, headers, valueKey, selected, onPick, onHover) {
    if (!rows.length) { node.innerHTML = '<p class="note">No flows for this selection.</p>'; return; }
    selected = selected || {};
    var keys = Object.keys(selected);
    function hotRow(row) {
      if (!keys.length) return false;
      for (var i = 0; i < keys.length; i++) {
        if (String(row[keys[i]] || 'unknown') !== String(selected[keys[i]])) return false;
      }
      return true;
    }
    var stages = columns.map(function () { return {}; });
    rows.forEach(function (row) {
      columns.forEach(function (col, index) {
        var name = row[col] || 'unknown';
        stages[index][name] = (stages[index][name] || 0) + (Number(row[valueKey]) || 0);
      });
    });
    var names = stages.map(function (stage, index) {
      var list = Object.keys(stage).sort(function (a, b) { return stage[b] - stage[a]; }).slice(0, 12);
      if (selected[columns[index]] && list.indexOf(selected[columns[index]]) < 0) list.push(selected[columns[index]]);
      rows.forEach(function (row) {
        if (!hotRow(row)) return;
        var name = row[columns[index]] || 'unknown';
        if (list.indexOf(name) < 0) list.push(name);
      });
      return list;
    });
    var height = Math.max.apply(null, names.map(function (list) { return list.length; })) * 28 + 46;
    var width = 960, colWidth = width / columns.length;
    var pos = names.map(function (list) {
      var map = {};
      list.forEach(function (name, index) { map[name] = 42 + index * 28; });
      return map;
    });
    function curve(stage, y1, y2) {
      return 'M ' + (colWidth * stage + 168) + ' ' + y1 + ' C ' + (colWidth * stage + colWidth / 2 + 80) + ' ' + y1
        + ', ' + (colWidth * (stage + 1) - colWidth / 2 + 8) + ' ' + y2 + ', ' + (colWidth * (stage + 1) + 8) + ' ' + y2;
    }
    function blurb(col, name, value) {
      var amount = Math.round(value).toLocaleString() + ' events in the last 24 hours';
      if (col === 'network' && /\/24$/.test(name)) return 'CIDR ' + name + '. ' + amount + '. Click to filter the panels below.';
      if (col === 'network') return name + ' is a host name, not an IP address, so it is not grouped into a CIDR. ' + amount + '. Click to filter the panels below.';
      if (col === 'category') return name + '. Click to expand its CIDR ranges and ingest paths. ' + amount + '.';
      return name + '. ' + amount + '. Click to filter the panels below.';
    }
    var svg = '<svg viewBox="0 0 ' + width + ' ' + height + '" width="100%">';
    for (var stage = 0; stage < columns.length - 1; stage++) {
      var links = {}, hotLinks = {};
      rows.forEach(function (row) {
        var from = row[columns[stage]] || 'unknown';
        var to = row[columns[stage + 1]] || 'unknown';
        if (pos[stage][from] === undefined || pos[stage + 1][to] === undefined) return;
        var key = from + '\n' + to;
        var amount = Number(row[valueKey]) || 0;
        links[key] = (links[key] || 0) + amount;
        if (hotRow(row)) hotLinks[key] = (hotLinks[key] || 0) + amount;
      });
      var amounts = Object.keys(links).map(function (key) { return links[key]; });
      var max = Math.max.apply(null, amounts.concat([1]));
      Object.keys(links).forEach(function (key) {
        var parts = key.split('\n');
        var hot = !!hotLinks[key];
        var opacity = !keys.length ? '0.45' : (hot ? '0.95' : '0.12');
        svg += '<path d="' + curve(stage, pos[stage][parts[0]], pos[stage + 1][parts[1]])
          + '" stroke="#58a6ff" stroke-opacity="' + opacity + '" stroke-width="'
          + Math.max(1.5, links[key] / max * 14) + '" fill="none"><title>'
          + esc(parts[0] + ' → ' + parts[1] + ', ' + Math.round(links[key]).toLocaleString() + ' events')
          + '</title></path>';
      });
    }
    names.forEach(function (list, stage) {
      svg += '<text x="' + (colWidth * stage + 8) + '" y="18" fill="#8b949e" font-size="11">' + esc(headers[stage] || columns[stage]) + '</text>';
      list.forEach(function (name) {
        var onPath = !keys.length || rows.some(function (row) {
          return hotRow(row) && (row[columns[stage]] || 'unknown') === name;
        });
        var chosen = selected[columns[stage]] === name;
        var fill = chosen ? '#58a6ff' : (onPath ? '#e6edf3' : '#6e7681');
        var shown = name.length > 28 ? name.slice(0, 26) + '…' : name;
        var tip = blurb(columns[stage], name, stages[stage][name] || 0);
        var attr = encodeURIComponent(columns[stage] + '\n' + name);
        svg += '<g data-node="' + attr + '">';
        svg += '<title>' + esc(tip) + '</title>';
        svg += '<text x="' + (colWidth * stage + 8) + '" y="' + (pos[stage][name] + 4) + '" fill="' + fill
          + '" font-size="12"' + (onPath && keys.length ? ' font-weight="700"' : '') + ' style="cursor:pointer">'
          + esc(shown) + '</text></g>';
      });
    });
    svg += '</svg>';
    el(node, svg);
    Array.prototype.forEach.call(node.querySelectorAll('g[data-node]'), function (group) {
      var parts = decodeURIComponent(group.getAttribute('data-node')).split('\n');
      var col = parts[0];
      var name = parts.slice(1).join('\n');
      var tip = group.querySelector('title');
      group.addEventListener('mouseover', function () { if (onHover && tip) onHover(tip.textContent); });
      group.addEventListener('click', function () { if (onPick) onPick(col, name); });
    });
  }

  function compact(value) {
    var n = Number(value) || 0;
    if (n >= 1000000) return (n / 1000000).toFixed(1).replace(/\.0$/, '') + 'M';
    if (n >= 10000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'K';
    return Math.round(n).toLocaleString();
  }

  function mono(name) {
    var parts = String(name).replace(/[^A-Za-z0-9 ]/g, ' ').trim().split(/\s+/);
    if (parts.length >= 2 && parts[1]) return (parts[0].charAt(0) + parts[1].charAt(0)).toUpperCase();
    var letters = String(name).replace(/[^A-Za-z0-9]/g, '');
    return (letters.slice(0, 2) || '•').toUpperCase();
  }

  function tint(name) {
    var palette = ['#3dd6c6', '#4c8dff', '#7c5cff', '#3fb950', '#d29922', '#f778ba', '#79c0ff', '#ff7b72'];
    var hash = 0;
    for (var i = 0; i < name.length; i++) hash = (hash + name.charCodeAt(i) * (i + 1)) % palette.length;
    return palette[hash];
  }

  function rollup(rows, key) {
    var map = {};
    rows.forEach(function (row) {
      var name = row[key] || 'unknown';
      if (!map[name]) map[name] = 0;
      map[name] += Number(row.events) || 0;
    });
    return Object.keys(map).map(function (name) { return { name: name, events: map[name] }; })
      .sort(function (a, b) { return b.events - a.events; });
  }

  function flowFan(node, rows, selected, onPick, onHover) {
    if (!rows.length) { node.innerHTML = '<p class="note">No sources sent data in this window.</p>'; return; }
    selected = selected || {};
    var hosts = rollup(rows, 'data_source');
    var sources = rollup(rows, 'endpoint');
    var indexes = rollup(rows, 'splunk_index');
    var methods = rollup(rows, 'ingest_method');
    var methodOrder = ['UF', 'HF', 'HEC', 'SC4S', 'Edge Processor', 'Syslog', 'NetFlow / IPFIX', 'Other TCP', 'Other'];
    methods.sort(function (a, b) {
      var ia = methodOrder.indexOf(a.name); if (ia < 0) ia = 20;
      var ib = methodOrder.indexOf(b.name); if (ib < 0) ib = 20;
      if (ia !== ib) return ia - ib;
      return b.events - a.events;
    });
    var showHosts = hosts.slice(0, 8);
    var hostExtra = hosts.length - showHosts.length;
    var hostNames = showHosts.map(function (item) { return item.name; });
    if (selected.host && selected.host !== '__more__' && hostNames.indexOf(selected.host) < 0) {
      showHosts = showHosts.concat([{ name: selected.host, events: 0 }]);
    }
    var showSources = sources.slice(0, 8);
    var sourceExtra = sources.length - showSources.length;
    var sourceNames = showSources.map(function (item) { return item.name; });
    if (selected.endpoint && selected.endpoint !== '__more__' && sourceNames.indexOf(selected.endpoint) < 0) {
      showSources = showSources.concat([{ name: selected.endpoint, events: 0 }]);
    }
    var right = indexes.slice(0, 5);
    if (selected.index && !right.some(function (item) { return item.name === selected.index; })) {
      right = right.concat([{ name: selected.index, events: 0 }]);
    }
    var rowH = 46;
    var nHost = showHosts.length + (hostExtra > 0 ? 1 : 0);
    var nSource = showSources.length + (sourceExtra > 0 ? 1 : 0);
    var body = Math.max(nHost, methods.length, nSource, right.length, 4) * rowH;
    var height = 96 + body;
    var listTop = 100;
    var gutter = 64;
    var hostRoom = 96;
    showHosts.forEach(function (item) { hostRoom = Math.max(hostRoom, labelPx(item.name) + 8); });
    if (hostExtra > 0) hostRoom = Math.max(hostRoom, labelPx('+' + hostExtra) + 8);
    hostRoom = Math.min(hostRoom, 320);
    var methodRoom = 88;
    methods.forEach(function (item) { methodRoom = Math.max(methodRoom, labelPx(item.name) + 8); });
    methodRoom = Math.min(methodRoom, 220);
    var sourceRoom = 96;
    showSources.forEach(function (item) { sourceRoom = Math.max(sourceRoom, labelPx(item.name) + 8); });
    if (sourceExtra > 0) sourceRoom = Math.max(sourceRoom, labelPx('+' + sourceExtra) + 8);
    sourceRoom = Math.min(sourceRoom, 320);
    var indexRoom = 88;
    right.forEach(function (item) { indexRoom = Math.max(indexRoom, labelPx(item.name) + 8); });
    indexRoom = Math.min(indexRoom, 280);
    var hostLabelX = 42;
    var methX = hostLabelX + hostRoom + gutter;
    var methLabelX = methX + 16;
    var srcX = methLabelX + methodRoom + gutter;
    var srcLabelX = srcX + 34;
    var idxX = srcLabelX + sourceRoom + gutter;
    var idxLabelX = idxX + 16;
    var width = Math.max(1100, idxLabelX + indexRoom + 24);
    function yAt(i, count) {
      var start = listTop + Math.max(0, body - count * rowH) / 2;
      return start + i * rowH + 10;
    }
    var hostY = {}, methY = {}, srcY = {}, idxY = {};
    showHosts.forEach(function (item, i) { hostY[item.name] = yAt(i, nHost); });
    methods.forEach(function (item, i) { methY[item.name] = yAt(i, methods.length); });
    showSources.forEach(function (item, i) { srcY[item.name] = yAt(i, nSource); });
    right.forEach(function (item, i) { idxY[item.name] = yAt(i, right.length); });
    function choosing() { return !!(selected.endpoint || selected.ingest || selected.index || selected.network || selected.host); }
    function hotRow(row) {
      if (!choosing()) return true;
      var source = row.endpoint || 'unknown';
      var host = row.data_source || 'unknown';
      if (selected.endpoint === '__more__') return sourceNames.indexOf(source) < 0;
      if (selected.host === '__more__') return hostNames.indexOf(host) < 0;
      if (selected.endpoint && source !== selected.endpoint) return false;
      if (selected.host && host !== selected.host) return false;
      if (selected.network && (row.network || 'unknown') !== selected.network) return false;
      if (selected.ingest && (row.ingest_method || 'Other') !== selected.ingest) return false;
      if (selected.index && (row.splunk_index || 'unknown') !== selected.index) return false;
      return true;
    }
    function addLink(bucket, key, amount, hot) {
      if (!bucket[key]) bucket[key] = { events: 0, hot: 0 };
      bucket[key].events += amount;
      if (hot) bucket[key].hot += amount;
    }
    var hostLinks = {}, methodLinks = {}, indexLinks = {};
    rows.forEach(function (row) {
      var host = row.data_source || 'unknown';
      var method = row.ingest_method || 'Other';
      var source = row.endpoint || 'unknown';
      var index = row.splunk_index || 'unknown';
      var amount = Number(row.events) || 0;
      var hot = hotRow(row);
      if (hostY[host] !== undefined && methY[method] !== undefined) addLink(hostLinks, host + '\n' + method, amount, hot);
      if (methY[method] !== undefined && srcY[source] !== undefined) addLink(methodLinks, method + '\n' + source, amount, hot);
      if (srcY[source] !== undefined && idxY[index] !== undefined) addLink(indexLinks, source + '\n' + index, amount, hot);
    });
    function linkMax(links) {
      var max = 1;
      Object.keys(links).forEach(function (key) { if (links[key].events > max) max = links[key].events; });
      return max;
    }
    function curve(x1, y1, x2, y2) {
      var mid = (x1 + x2) / 2;
      return 'M ' + x1 + ' ' + y1 + ' C ' + mid + ' ' + y1 + ', ' + mid + ' ' + y2 + ', ' + x2 + ' ' + y2;
    }
    function drawLinks(links, y1, y2, x1, x2, color) {
      var max = linkMax(links);
      Object.keys(links).forEach(function (key) {
        var parts = key.split('\n');
        var hot = links[key].hot > 0;
        var dim = choosing() && !hot;
        svg += '<path d="' + curve(x1, y1[parts[0]], x2, y2[parts[1]])
          + '" stroke="' + (hot && choosing() ? '#3dd6c6' : color) + '" stroke-width="'
          + Math.max(1.2, links[key].events / max * 4).toFixed(2)
          + '" stroke-opacity="' + (dim ? '0.1' : '0.7') + '" fill="none"/>';
      });
    }
    var svg = '<svg viewBox="0 0 ' + width + ' ' + height + '" width="100%" style="min-width:' + width + 'px" role="img">';
    svg += '<defs><linearGradient id="fanIn" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#4c8dff"/><stop offset="1" stop-color="#3dd6c6"/></linearGradient></defs>';
    svg += '<text x="8" y="42" fill="#e6edf3" font-size="32" font-weight="700">' + esc(compact(hosts.length)) + '</text>';
    svg += '<text x="8" y="62" fill="#8b949e" font-size="11">HOSTS</text>';
    svg += '<text x="' + methLabelX + '" y="62" fill="#8b949e" font-size="11">INGESTION PATH</text>';
    svg += '<text x="' + srcLabelX + '" y="62" fill="#8b949e" font-size="11">SOURCETYPE</text>';
    svg += '<text x="' + idxLabelX + '" y="62" fill="#8b949e" font-size="11">INDEX</text>';
    drawLinks(hostLinks, hostY, methY, hostLabelX + hostRoom + 6, methX - 12, 'url(#fanIn)');
    drawLinks(methodLinks, methY, srcY, methLabelX + methodRoom + 6, srcX - 12, '#3dd6c6');
    drawLinks(indexLinks, srcY, idxY, srcLabelX + sourceRoom + 6, idxX - 12, '#3dd6c6');
    showHosts.forEach(function (item) {
      var y = hostY[item.name];
      var color = tint(item.name);
      var on = selected.host === item.name;
      var fitted = fitText(item.name, hostRoom);
      svg += '<g data-node="' + encodeURIComponent('host\n' + item.name) + '" style="cursor:pointer">';
      svg += '<title>' + esc('Host ' + item.name + '. ' + Math.round(item.events).toLocaleString() + ' events in the last 24 hours. Click to follow this host through its ingestion path.') + '</title>';
      svg += '<rect x="8" y="' + (y - 14) + '" width="26" height="26" rx="6" fill="' + color + '" fill-opacity="0.18" stroke="' + color + '"/>';
      svg += '<text x="21" y="' + (y + 4) + '" text-anchor="middle" fill="' + color + '" font-size="10" font-weight="700">' + esc(mono(item.name)) + '</text>';
      svg += '<text x="' + hostLabelX + '" y="' + (y + 4) + '" fill="' + (on ? '#3dd6c6' : '#e6edf3') + '" font-size="' + fitted.size + '"' + (on ? ' font-weight="700"' : '') + '>' + esc(fitted.text) + '</text>';
      svg += '</g>';
    });
    if (hostExtra > 0) {
      var yHostMore = yAt(showHosts.length, nHost);
      var moreHost = fitText('+' + hostExtra, hostRoom);
      svg += '<g data-node="' + encodeURIComponent('host\n__more__') + '" style="cursor:pointer">';
      svg += '<title>' + esc('+' + hostExtra + ' hosts are not drawn. Click to load them below.') + '</title>';
      svg += '<text x="' + hostLabelX + '" y="' + (yHostMore + 4) + '" fill="' + (selected.host === '__more__' ? '#3dd6c6' : '#8b949e') + '" font-size="' + moreHost.size + '" font-weight="700">' + esc(moreHost.text) + '</text>';
      svg += '</g>';
    }
    methods.forEach(function (item) {
      var y = methY[item.name];
      var on = selected.ingest === item.name;
      var fitted = fitText(item.name, methodRoom);
      svg += '<g data-node="' + encodeURIComponent('ingest_method\n' + item.name) + '" style="cursor:pointer">';
      svg += '<title>' + esc('Ingestion path ' + item.name + '. ' + Math.round(item.events).toLocaleString() + ' events. Click to filter this path.') + '</title>';
      svg += '<circle cx="' + methX + '" cy="' + y + '" r="5" fill="' + (on ? '#3dd6c6' : '#8b949e') + '"/>';
      svg += '<text x="' + methLabelX + '" y="' + (y - 2) + '" fill="' + (on ? '#3dd6c6' : '#e6edf3') + '" font-size="' + fitted.size + '"' + (on ? ' font-weight="700"' : '') + '>' + esc(fitted.text) + '</text>';
      svg += '<text x="' + methLabelX + '" y="' + (y + 16) + '" fill="#8b949e" font-size="11">' + esc(compact(item.events)) + '</text>';
      svg += '</g>';
    });
    showSources.forEach(function (item) {
      var y = srcY[item.name];
      var on = selected.endpoint === item.name;
      var color = tint(item.name);
      var fitted = fitText(item.name, sourceRoom);
      svg += '<g data-node="' + encodeURIComponent('endpoint\n' + item.name) + '" style="cursor:pointer">';
      svg += '<title>' + esc(item.name + '. ' + Math.round(item.events).toLocaleString() + ' events. A known product keeps its name; otherwise this is the sourcetype. Click to follow it to the index.') + '</title>';
      svg += '<rect x="' + srcX + '" y="' + (y - 14) + '" width="26" height="26" rx="6" fill="' + color + '" fill-opacity="0.18" stroke="' + color + '"/>';
      svg += '<text x="' + (srcX + 13) + '" y="' + (y + 4) + '" text-anchor="middle" fill="' + color + '" font-size="10" font-weight="700">' + esc(mono(item.name)) + '</text>';
      svg += '<text x="' + srcLabelX + '" y="' + (y + 4) + '" fill="' + (on ? '#3dd6c6' : '#e6edf3') + '" font-size="' + fitted.size + '"' + (on ? ' font-weight="700"' : '') + '>' + esc(fitted.text) + '</text>';
      svg += '</g>';
    });
    if (sourceExtra > 0) {
      var ySourceMore = yAt(showSources.length, nSource);
      var moreSource = fitText('+' + sourceExtra, sourceRoom);
      svg += '<g data-node="' + encodeURIComponent('endpoint\n__more__') + '" style="cursor:pointer">';
      svg += '<title>' + esc('+' + sourceExtra + ' sourcetypes are not drawn. Click to load them below.') + '</title>';
      svg += '<text x="' + srcLabelX + '" y="' + (ySourceMore + 4) + '" fill="' + (selected.endpoint === '__more__' ? '#3dd6c6' : '#8b949e') + '" font-size="' + moreSource.size + '" font-weight="700">' + esc(moreSource.text) + '</text>';
      svg += '</g>';
    }
    right.forEach(function (item) {
      var y = idxY[item.name];
      var on = selected.index === item.name;
      var fitted = fitText(item.name, indexRoom);
      svg += '<g data-node="' + encodeURIComponent('splunk_index\n' + item.name) + '" style="cursor:pointer">';
      svg += '<title>' + esc('Index ' + item.name + '. ' + Math.round(item.events).toLocaleString() + ' events. Click to filter the flow.') + '</title>';
      svg += '<circle cx="' + idxX + '" cy="' + y + '" r="5" fill="' + (on ? '#3dd6c6' : '#8b949e') + '"/>';
      svg += '<text x="' + idxLabelX + '" y="' + (y - 2) + '" fill="' + (on ? '#3dd6c6' : '#e6edf3') + '" font-size="' + fitted.size + '"' + (on ? ' font-weight="700"' : '') + '>' + esc(fitted.text) + '</text>';
      svg += '<text x="' + idxLabelX + '" y="' + (y + 16) + '" fill="#8b949e" font-size="11">' + esc(compact(item.events)) + '</text>';
      svg += '</g>';
    });
    svg += '</svg>';
    node.innerHTML = '<div class="chart fan">' + svg + '</div>';
    Array.prototype.forEach.call(node.querySelectorAll('g[data-node]'), function (group) {
      var parts = decodeURIComponent(group.getAttribute('data-node')).split('\n');
      var col = parts[0];
      var name = parts.slice(1).join('\n');
      var tip = group.querySelector('title');
      group.addEventListener('mouseover', function () { if (onHover && tip) onHover(tip.textContent); });
      group.addEventListener('click', function () { if (onPick) onPick(col, name); });
    });
  }

  return { line: line, pie: pie, flow: flow, topology: topology, sourceFan: flowFan };
})();

/* Estate map: site and host → ingestion path → family and sourcetype → index.
   Drawn on a canvas so thousands of hosts stay smooth. The scroll wheel zooms toward
   the pointer, dragging pans, and double-click zooms to a node. A site opens into its
   hosts, and a family into its sourcetypes, once there is room on screen to label them.
   Every row is drawn; nothing is folded into an Other node. */
(function (global) {
  'use strict';

  var COLS = [
    { title: 'SITE → HOST', group: 'site', leaf: 'host' },
    { title: 'INGESTION PATH', leaf: 'ingest_method' },
    { title: 'FAMILY → SOURCETYPE', group: 'family', leaf: 'endpoint' },
    { title: 'INDEX', leaf: 'splunk_index' }
  ];
  var METHOD_ORDER = ['UF', 'HF', 'HEC', 'SC4S', 'Edge Processor', 'Syslog', 'NetFlow / IPFIX', 'Other TCP', 'Other'];
  var PALETTE = ['#3dd6c6', '#4c8dff', '#7c5cff', '#3fb950', '#d29922', '#f778ba', '#79c0ff', '#ff7b72', '#a5d6ff', '#e3b341'];
  var NODE_W = 10;
  var MIN_H = 3;
  var GAP = 2;
  var OPEN_SLOT = 13;
  var LABEL_MIN = 11;
  var MINIMAP_W = 52;
  var PAD = 14;
  var FONT = '12px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
  var FONT_SMALL = '11px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';

  function tint(name) {
    var hash = 0;
    var text = String(name);
    for (var i = 0; i < text.length; i++) hash = (hash * 31 + text.charCodeAt(i)) >>> 0;
    return PALETTE[hash % PALETTE.length];
  }

  function compact(value) {
    var n = Number(value) || 0;
    if (n >= 1e9) return (n / 1e9).toFixed(1).replace(/\.0$/, '') + 'B';
    if (n >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, '') + 'M';
    if (n >= 1e4) return (n / 1e3).toFixed(1).replace(/\.0$/, '') + 'K';
    return Math.round(n).toLocaleString();
  }

  function clamp(value, low, high) { return Math.max(low, Math.min(high, value)); }

// Volume still decides the order and the thickness, but a square-root-like scale
// plus a cap keeps the largest flow from filling the column and hiding the rest.
function share(values) {
  var weights = values.map(function (value) { return Math.pow(Math.max(Number(value) || 0, 1), 0.4); });
  var sum = 0;
  weights.forEach(function (weight) { sum += weight; });
  if (!sum) return values.map(function () { return values.length ? 1 / values.length : 0; });
  var parts = weights.map(function (weight) { return weight / sum; });
  var cap = 0.42;
  for (var guard = 0; guard < 6 && parts.length > 1; guard++) {
    var overflow = 0;
    var room = 0;
    parts.forEach(function (part) {
      if (part > cap) overflow += part - cap;
      else room += part;
    });
    if (overflow < 1e-6 || room <= 0) break;
    parts = parts.map(function (part) {
      return part > cap ? cap : part + overflow * (part / room);
    });
    cap = Math.min(0.7, cap + 0.1);
  }
  return parts;
}

  // Builds every node once. Leaves are hosts, paths, sourcetypes, and indexes; groups
  // are sites and families. Links are kept at leaf level and folded per frame.
  function build(rows) {
    var units = [];
    var leaves = [[], [], [], []];
    var groups = [[], null, [], null];
    var leafByKey = [{}, {}, {}, {}];
    var groupByKey = [{}, null, {}, null];
    var data = [];
    function unit(col, key, name, group) {
      var item = { id: units.length, col: col, key: key, name: name, ev: 0, y: 0, h: 0, group: group || null, leaves: null, open: false };
      units.push(item);
      return item;
    }
    function groupOf(col, name) {
      var found = groupByKey[col][name];
      if (!found) {
        found = unit(col, name, name, null);
        found.leaves = [];
        groupByKey[col][name] = found;
        groups[col].push(found);
      }
      return found;
    }
    function leafOf(col, key, name, group) {
      var found = leafByKey[col][key];
      if (!found) {
        found = unit(col, key, name, group);
        leafByKey[col][key] = found;
        leaves[col].push(found);
        if (group) group.leaves.push(found);
      }
      return found;
    }
    rows.forEach(function (row) {
      var ev = Number(row.events) || 0;
      if (ev <= 0) return;
      var site = row.environment || 'unknown';
      var host = row.data_source || 'unknown';
      var family = row.family || 'unknown';
      var st = row.endpoint || 'unknown';
      var siteGroup = groupOf(0, site);
      var famGroup = groupOf(2, family);
      var path = [
        leafOf(0, site + '\u0001' + host, host, siteGroup),
        leafOf(1, row.ingest_method || 'Other', row.ingest_method || 'Other', null),
        leafOf(2, family + '\u0001' + st, st, famGroup),
        leafOf(3, row.splunk_index || 'unknown', row.splunk_index || 'unknown', null)
      ];
      path.forEach(function (leaf) {
        leaf.ev += ev;
        if (leaf.group) leaf.group.ev += ev;
      });
      data.push({ ev: ev, path: path, row: row });
    });
    var links = [{}, {}, {}];
    data.forEach(function (item, i) {
      for (var c = 0; c < 3; c++) {
        var a = item.path[c];
        var b = item.path[c + 1];
        var key = a.id + '>' + b.id;
        var link = links[c][key];
        if (!link) link = links[c][key] = { a: a, b: b, ev: 0, rows: [] };
        link.ev += item.ev;
        link.rows.push(i);
      }
    });
    var linkList = links.map(function (bag) { return Object.keys(bag).map(function (key) { return bag[key]; }); });
    data.forEach(function (item) { item.links = []; });
    linkList.forEach(function (list, c) {
      list.forEach(function (link) {
        link.rows.forEach(function (i) { data[i].links[c] = link; });
        link.rows = null;
      });
    });
    return { units: units, leaves: leaves, groups: groups, links: linkList, data: data };
  }

  // Places every leaf in world space. Columns share one world height so they zoom
  // together. Heights follow volume, with a floor so the smallest host is still a bar.
  function layout(model, viewH) {
    function weightedY(list, col) {
      var sums = {};
      model.links[col].forEach(function (link) {
        var target = link.b;
        var mid = link.a.y + link.a.h / 2;
        var bag = sums[target.id] || (sums[target.id] = { w: 0, y: 0 });
        bag.w += link.ev;
        bag.y += mid * link.ev;
      });
      return function (item) {
        var bag = sums[item.id];
        return bag && bag.w ? bag.y / bag.w : 0;
      };
    }
    var counts = model.leaves.map(function (list) { return list.length; });
    var groupCounts = [model.groups[0].length, 0, model.groups[2].length, 0];
    var need = 0;
    for (var c = 0; c < 4; c++) need = Math.max(need, counts[c] * (MIN_H + GAP) + groupCounts[c] * 8);
    var H = Math.max(viewH, need * 2.2);
    model.H = H;

    function place(col, ordered, grouped) {
      var n = ordered.length;
      var g = grouped ? model.groups[col].length : 0;
      var leafGap = grouped ? GAP : Math.min(H * 0.04, Math.max(GAP, H * 0.25 / Math.max(1, n)));
      var groupGap = grouped ? Math.min(H * 0.03, Math.max(8, H * 0.18 / Math.max(1, g))) : 0;
      var free = Math.max(0, H - n * (MIN_H + leafGap) - g * groupGap);
      var y = groupGap / 2;
      var last = null;
      var parts = share(ordered.map(function (leaf) { return leaf.ev; }));
      ordered.forEach(function (leaf, index) {
        if (grouped && leaf.group !== last) {
          if (last) { last.h = y - last.y - leafGap; y += groupGap; }
          last = leaf.group;
          last.y = y;
        }
        leaf.y = y;
        leaf.h = MIN_H + free * (parts[index] || 0);
        y += leaf.h + leafGap;
      });
      if (last) last.h = y - last.y - leafGap;
      var used = y - leafGap + groupGap / 2;
      var shift = (H - used) / 2;
      ordered.forEach(function (leaf) { leaf.y += shift; });
      if (grouped) model.groups[col].forEach(function (group) { group.y += shift; });
    }

    var sites = model.groups[0].slice().sort(function (a, b) { return b.ev - a.ev; });
    var col0 = [];
    sites.forEach(function (site) {
      site.leaves.sort(function (a, b) { return b.ev - a.ev; });
      col0 = col0.concat(site.leaves);
    });
    place(0, col0, true);

    var col1 = model.leaves[1].slice().sort(function (a, b) {
      var ia = METHOD_ORDER.indexOf(a.name); if (ia < 0) ia = 99;
      var ib = METHOD_ORDER.indexOf(b.name); if (ib < 0) ib = 99;
      return ia - ib || b.ev - a.ev;
    });
    place(1, col1, false);

    var famY = weightedY(model.leaves[2], 1);
    model.groups[2].forEach(function (family) {
      var w = 0, y = 0;
      family.leaves.forEach(function (leaf) { w += leaf.ev; y += famY(leaf) * leaf.ev; });
      family.order = w ? y / w : 0;
      family.leaves.sort(function (a, b) { return b.ev - a.ev; });
    });
    var col2 = [];
    model.groups[2].slice().sort(function (a, b) { return a.order - b.order; }).forEach(function (family) {
      col2 = col2.concat(family.leaves);
    });
    place(2, col2, true);

    var idxY = weightedY(model.leaves[3], 2);
    var col3 = model.leaves[3].slice().sort(function (a, b) { return idxY(a) - idxY(b); });
    place(3, col3, false);
    model.order = [col0, col1, col2, col3];
  }

  function truncate(ctx, text, room) {
    if (ctx.measureText(text).width <= room) return text;
    var low = 0, high = text.length;
    while (low < high) {
      var mid = (low + high + 1) >> 1;
      if (ctx.measureText(text.slice(0, mid) + '…').width <= room) low = mid; else high = mid - 1;
    }
    return low > 0 ? text.slice(0, low) + '…' : '';
  }

  function create(host, options) {
    options = options || {};
    var onPick = options.onPick || function () {};
    var onHover = options.onHover || function () {};
    host.innerHTML = '';
    var wrap = document.createElement('div');
    wrap.className = 'topomap';
    wrap.innerHTML = '<div class="topomap-bar">'
      + '<button type="button" class="btn secondary" data-act="out" title="Zoom out (-)">−</button>'
      + '<button type="button" class="btn secondary" data-act="in" title="Zoom in (+)">+</button>'
      + '<button type="button" class="btn secondary" data-act="fit" title="Fit the whole estate (0)">Fit</button>'
      + '<button type="button" class="btn secondary" data-act="full" title="Full screen (F)">Full screen</button>'
      + '<button type="button" class="btn secondary" data-act="estate" hidden>Whole estate</button>'
      + '<span class="topomap-looking">Whole estate</span>'
      + '<span class="topomap-zoom"></span>'
      + '</div>'
      + '<div class="topomap-heads"></div>'
      + '<canvas class="topomap-canvas" tabindex="0" aria-label="Estate map. Scroll to zoom, drag to pan."></canvas>';
    host.appendChild(wrap);
    var canvas = wrap.querySelector('canvas');
    var heads = wrap.querySelector('.topomap-heads');
    var zoomLabel = wrap.querySelector('.topomap-zoom');
    var ctx = canvas.getContext('2d');
    var model = null;
    var allRows = [];
    var cssW = 0, cssH = 0, dpr = 1;
    var view = { k: 1, oy: 0 };
    var fitK = 1, maxK = 1;
    var cols = [];
    var frame = null;
    var hover = null;
    var focus = null;
    var hotLinks = null;
    var anim = null;
    var minimap = null;
    var drawPending = false;

    function sizeCanvas() {
      var full = wrap.classList.contains('full');
      cssW = Math.max(480, wrap.clientWidth);
      var top = wrap.querySelector('.topomap-bar').offsetHeight + heads.offsetHeight;
      cssH = full ? Math.max(320, window.innerHeight - top - 8) : Math.round(clamp(window.innerHeight * 0.72, 520, 860));
      dpr = global.devicePixelRatio || 1;
      canvas.style.width = cssW + 'px';
      canvas.style.height = cssH + 'px';
      canvas.width = Math.round(cssW * dpr);
      canvas.height = Math.round(cssH * dpr);
      var usable = cssW - MINIMAP_W - PAD * 2;
      var labelRoom = clamp(usable * 0.13, 90, 210);
      var linkW = Math.max(40, (usable - 4 * NODE_W - 4 * labelRoom) / 3);
      if (linkW === 40) labelRoom = Math.max(60, (usable - 4 * NODE_W - 3 * linkW) / 4);
      cols = [];
      for (var c = 0; c < 4; c++) {
        var x = PAD + c * (NODE_W + labelRoom + linkW);
        cols.push({ x: x, labelX: x + NODE_W + 6, labelRoom: labelRoom - 10, out: x + NODE_W + labelRoom });
      }
      heads.innerHTML = '';
      COLS.forEach(function (col, c) {
        var span = document.createElement('span');
        span.textContent = col.title;
        span.style.left = cols[c].x + 'px';
        heads.appendChild(span);
      });
    }

    function setLimits() {
      if (!model) return;
      fitK = cssH / model.H;
      maxK = Math.max(fitK * 4, 26 / (MIN_H + GAP));
    }

    function clampView(v) {
      var k = clamp(v.k, fitK, maxK);
      var span = cssH / k;
      var oy = model.H <= span ? (model.H - span) / 2 : clamp(v.oy, -span * 0.05, model.H - span * 0.95);
      return { k: k, oy: oy };
    }

    function fit() { view = clampView({ k: fitK, oy: 0 }); }

    function toScreen(y) { return (y - view.oy) * view.k; }

    function isOpen(group) {
      if (!group) return true;
      if (group.forced) return true;
      // A family stays one bar until it is clicked, then it shows its sourcetypes.
      if (group.col === 2) return !!group.userOpen;
      return group.h * view.k / group.leaves.length >= OPEN_SLOT;
    }

    // Folds leaves into the sites and families that are still closed at this zoom.
    function buildFrame() {
      model.groups.forEach(function (list) { if (list) list.forEach(function (group) { group.open = isOpen(group); }); });
      function shown(leaf) { return leaf.group && !leaf.group.open ? leaf.group : leaf; }
      var visible = [[], [], [], []];
      var seen = {};
      model.order.forEach(function (list, c) {
        list.forEach(function (leaf) {
          var item = shown(leaf);
          if (!seen[item.id]) { seen[item.id] = 1; visible[c].push(item); }
        });
      });
      var links = [];
      model.links.forEach(function (list, c) {
        var bag = {};
        list.forEach(function (link) {
          var a = shown(link.a), b = shown(link.b);
          var key = a.id + '>' + b.id;
          var item = bag[key];
          if (!item) { item = bag[key] = { a: a, b: b, ev: 0, hot: 0, layer: c }; links.push(item); }
          item.ev += link.ev;
          if (hotLinks) item.hot += hotLinks[c].get(link) || 0;
        });
      });
      var outs = {}, ins = {};
      links.forEach(function (link) {
        (outs[link.a.id] || (outs[link.a.id] = [])).push(link);
        (ins[link.b.id] || (ins[link.b.id] = [])).push(link);
      });
      function stack(bag, end, other) {
        Object.keys(bag).forEach(function (id) {
          var list = bag[id];
          var owner = list[0][end];
          list.sort(function (p, q) { return (p[other].y + p[other].h / 2) - (q[other].y + q[other].h / 2); });
          var parts = share(list.map(function (link) { return link.ev; }));
          var y = owner.y;
          list.forEach(function (link, index) {
            var h = owner.h * (parts[index] || 0);
            link[end + '0'] = y;
            link[end + '1'] = y + h;
            y += h;
          });
        });
      }
      stack(outs, 'a', 'b');
      stack(ins, 'b', 'a');
      var hotUnits = {};
      links.forEach(function (link) {
        if (link.hot > 0) { hotUnits[link.a.id] = 1; hotUnits[link.b.id] = 1; }
      });
      return { visible: visible, links: links, hotUnits: hotUnits };
    }

    function color(item) {
      if (item.col === 0) return tint(item.group ? item.group.name : item.name);
      if (item.col === 2) return tint(item.group ? item.group.name : item.name);
      return tint(item.name);
    }

    function selected(item) {
      var target = hover || focus;
      if (!target) return false;
      if (target.unit === item) return true;
      return !!(target.unit && target.unit.leaves && item.group === target.unit);
    }

    function draw() {
      drawPending = false;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, cssW, cssH);
      if (!model || !model.data.length) {
        ctx.fillStyle = '#8b949e';
        ctx.font = FONT;
        ctx.fillText((model && model.note) || 'No events in the last 24 hours.', PAD, 28);
        return;
      }
      frame = buildFrame();
      var lit = !!hotLinks;
      frame.links.forEach(function (link) {
        var y0 = toScreen(link.a0), y1 = toScreen(link.a1), t0 = toScreen(link.b0), t1 = toScreen(link.b1);
        if (Math.max(y1, t1) < 0 || Math.min(y0, t0) > cssH) return;
        var x0 = cols[link.layer].out, x1 = cols[link.layer + 1].x;
        var mid = (x0 + x1) / 2;
        if (y1 - y0 < 0.6) { var c0 = (y0 + y1) / 2; y0 = c0 - 0.3; y1 = c0 + 0.3; }
        if (t1 - t0 < 0.6) { var c1 = (t0 + t1) / 2; t0 = c1 - 0.3; t1 = c1 + 0.3; }
        var hot = lit && link.hot > 0;
        ctx.globalAlpha = lit ? (hot ? 0.82 : 0.06) : 0.34;
        ctx.fillStyle = lit && !hot ? '#6e7681' : color(link.layer === 0 ? link.a : (link.layer === 1 ? link.b : link.a));
        ctx.beginPath();
        ctx.moveTo(x0, y0);
        ctx.bezierCurveTo(mid, y0, mid, t0, x1, t0);
        ctx.lineTo(x1, t1);
        ctx.bezierCurveTo(mid, t1, mid, y1, x0, y1);
        ctx.closePath();
        ctx.fill();
      });
      ctx.globalAlpha = 1;
      frame.visible.forEach(function (list, c) {
        var col = cols[c];
        list.forEach(function (item) {
          var top = toScreen(item.y), h = Math.max(1, item.h * view.k);
          if (top + h < 0 || top > cssH) return;
          var on = selected(item);
          var dim = lit && !on && !frame.hotUnits[item.id];
          ctx.globalAlpha = dim ? 0.3 : 1;
          ctx.fillStyle = color(item);
          ctx.fillRect(col.x, top, NODE_W, h);
          if (item.leaves) {
            ctx.globalAlpha = dim ? 0.15 : 0.5;
            ctx.fillRect(col.x - 3, top, 2, h);
          }
          if (on) {
            ctx.globalAlpha = 1;
            ctx.strokeStyle = '#e6edf3';
            ctx.lineWidth = 1.5;
            ctx.strokeRect(col.x - 1.5, top - 1.5, NODE_W + 3, h + 3);
          }
          ctx.globalAlpha = dim ? 0.45 : 1;
          if (h >= LABEL_MIN) drawLabel(item, col, top, h);
        });
        if (c === 0 || c === 2) drawGroupHeads(c, col);
      });
      ctx.globalAlpha = 1;
      drawMinimap();
      zoomLabel.textContent = (view.k / fitK).toFixed(view.k / fitK < 10 ? 1 : 0) + '×';
    }

    function drawLabel(item, col, top, h) {
      var visTop = Math.max(top, 0), visBottom = Math.min(top + h, cssH);
      if (visBottom - visTop < LABEL_MIN) return;
      var name = item.name;
      var detail = compact(item.ev) + (item.leaves ? ' · ' + item.leaves.length + (item.col === 0 ? (item.leaves.length === 1 ? ' host' : ' hosts') : (item.leaves.length === 1 ? ' sourcetype' : ' sourcetypes')) : '');
      var two = visBottom - visTop >= 28;
      var y = two ? clamp(top + h / 2 - 7, visTop + 10, visBottom - 18) : clamp(top + h / 2 + 4, visTop + 10, visBottom - 2);
      ctx.font = FONT;
      ctx.fillStyle = '#e6edf3';
      var text = two ? name : name + '  ' + detail;
      ctx.fillText(truncate(ctx, text, col.labelRoom), col.labelX, y);
      if (two) {
        ctx.font = FONT_SMALL;
        ctx.fillStyle = '#8b949e';
        ctx.fillText(truncate(ctx, detail, col.labelRoom), col.labelX, y + 15);
      }
    }

    // An open site or family keeps its name above its hosts or sourcetypes.
    function drawGroupHeads(c, col) {
      model.groups[c].forEach(function (group) {
        if (!group.open) return;
        var top = toScreen(group.y), h = group.h * view.k;
        if (top + h < 0 || top > cssH) return;
        var y = Math.max(top - 4, 12);
        if (y > top + h - 4) return;
        ctx.globalAlpha = 0.9;
        ctx.fillStyle = tint(group.name);
        ctx.fillRect(col.x - 3, top, 2, h);
        ctx.font = 'bold ' + FONT_SMALL;
        var text = truncate(ctx, group.name + ' · ' + group.leaves.length, col.labelRoom + NODE_W);
        ctx.globalAlpha = 0.92;
        ctx.fillStyle = '#070b10';
        ctx.fillRect(col.x - 4, y - 11, ctx.measureText(text).width + 6, 14);
        ctx.globalAlpha = 1;
        ctx.fillStyle = tint(group.name);
        ctx.fillText(text, col.x - 3, y);
      });
      ctx.globalAlpha = 1;
    }

    function buildMinimap() {
      minimap = document.createElement('canvas');
      minimap.width = Math.round(MINIMAP_W * dpr);
      minimap.height = Math.round(cssH * dpr);
      var m = minimap.getContext('2d');
      m.setTransform(dpr, 0, 0, dpr, 0, 0);
      m.fillStyle = '#0b1118';
      m.fillRect(0, 0, MINIMAP_W, cssH);
      if (!model) return;
      var scale = cssH / model.H;
      var barW = (MINIMAP_W - 10) / 4;
      model.order.forEach(function (list, c) {
        list.forEach(function (leaf) {
          m.fillStyle = color(leaf);
          m.fillRect(5 + c * barW, leaf.y * scale, barW - 3, Math.max(0.5, leaf.h * scale));
        });
      });
    }

    function drawMinimap() {
      var x = cssW - MINIMAP_W;
      if (minimap) ctx.drawImage(minimap, x, 0, MINIMAP_W, cssH);
      var scale = cssH / model.H;
      var top = view.oy * scale, h = (cssH / view.k) * scale;
      ctx.strokeStyle = '#58a6ff';
      ctx.lineWidth = 1.5;
      ctx.fillStyle = 'rgba(88,166,255,0.12)';
      ctx.fillRect(x + 1, top, MINIMAP_W - 2, Math.max(3, h));
      ctx.strokeRect(x + 1, top, MINIMAP_W - 2, Math.max(3, h));
    }

    function schedule() {
      if (drawPending) return;
      drawPending = true;
      global.requestAnimationFrame(draw);
    }

    function animateTo(target) {
      target = clampView(target);
      var start = { k: view.k, oy: view.oy };
      var began = null;
      if (anim) global.cancelAnimationFrame(anim);
      function step(now) {
        if (began === null) began = now;
        var t = Math.min(1, (now - began) / 260);
        var e = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
        var k = Math.exp(Math.log(start.k) + (Math.log(target.k) - Math.log(start.k)) * e);
        var centerStart = start.oy + cssH / start.k / 2;
        var centerEnd = target.oy + cssH / target.k / 2;
        var center = centerStart + (centerEnd - centerStart) * e;
        view = { k: k, oy: center - cssH / k / 2 };
        draw();
        anim = t < 1 ? global.requestAnimationFrame(step) : null;
      }
      anim = global.requestAnimationFrame(step);
    }

    function zoomAt(factor, screenY) {
      var wy = view.oy + screenY / view.k;
      var k = clamp(view.k * factor, fitK, maxK);
      view = clampView({ k: k, oy: wy - screenY / k });
      schedule();
    }

    function zoomToUnit(item) {
      var k;
      if (item.leaves && !item.open) k = Math.max(OPEN_SLOT * item.leaves.length * 1.25 / item.h, cssH * 0.3 / item.h);
      else k = Math.max(cssH * 0.25 / item.h, view.k * 1.6);
      k = clamp(k, fitK, maxK);
      var center = item.y + item.h / 2;
      animateTo({ k: k, oy: center - cssH / k / 2 });
    }

    function unitAt(px, py) {
      if (!frame) return null;
      for (var c = 0; c < 4; c++) {
        var col = cols[c];
        if (px < col.x - 4 || px > col.out) continue;
        var wy = view.oy + py / view.k;
        var list = frame.visible[c];
        var best = null, bestGap = Infinity;
        for (var i = 0; i < list.length; i++) {
          var item = list[i];
          var gap = wy < item.y ? item.y - wy : (wy > item.y + item.h ? wy - item.y - item.h : 0);
          if (gap < bestGap) { bestGap = gap; best = item; }
        }
        if (best && bestGap * view.k <= 4) return best;
        return null;
      }
      return null;
    }

    function describe(item) {
      if (!item) return '';
      var events = Math.round(item.ev).toLocaleString() + ' events in the last 24 hours';
      if (item.leaves) {
        var kind = item.col === 0 ? 'Site ' : 'Sourcetype family ';
        var inside = item.leaves.length + (item.col === 0 ? ' hosts' : ' sourcetypes');
        if (item.col === 2) {
          return kind + item.name + ' · ' + inside + ' · ' + events + '. Click to redraw the map around this family and list its sourcetypes.';
        }
        return kind + item.name + ' · ' + inside + ' · ' + events + '. ' + (item.open ? 'Click to select it.' : 'Scroll or double-click to open it. Click to select it.');
      }
      var label = ['Host ', 'Ingestion path ', 'Sourcetype ', 'Index '][item.col];
      var parent = item.group ? (item.col === 0 ? ' in site ' : ' in family ') + item.group.name : '';
      return label + item.name + parent + ' · ' + events + '. Click to select it.';
    }

    function descriptor(item) {
      if (!item) return null;
      if (item.leaves) return { col: item.col === 0 ? 'site' : 'family', name: item.name };
      if (item.col === 0) return { col: 'host', name: item.name, site: item.group && item.group.name };
      if (item.col === 1) return { col: 'ingest_method', name: item.name };
      if (item.col === 2) return { col: 'endpoint', name: item.name, family: item.group && item.group.name };
      return { col: 'splunk_index', name: item.name };
    }

    function findUnit(desc) {
      if (!model || !desc) return null;
      var hit = null;
      model.units.forEach(function (item) {
        if (hit) return;
        var d = descriptor(item);
        if (d.col !== desc.col || d.name !== desc.name) return;
        if (desc.site && d.site && desc.site !== d.site) return;
        if (desc.family && d.family && desc.family !== d.family) return;
        hit = item;
      });
      return hit;
    }

    // Every leaf link that carries rows through the chosen node, with the share of
    // events that pass through it.
    function computeHot(item) {
      if (!item) return null;
      var hot = [new Map(), new Map(), new Map()];
      model.data.forEach(function (row) {
        var through = row.path[item.col] === item || (item.leaves && row.path[item.col].group === item);
        if (!through) return;
        for (var c = 0; c < 3; c++) {
          var link = row.links[c];
          hot[c].set(link, (hot[c].get(link) || 0) + row.ev);
        }
      });
      return hot;
    }

    function setHighlight() {
      var target = hover || focus;
      hotLinks = target && target.unit ? computeHot(target.unit) : null;
      schedule();
    }

    function setForced() {
      model.groups.forEach(function (list) { if (list) list.forEach(function (group) { group.forced = false; }); });
      if (focus && focus.unit && focus.unit.group) focus.unit.group.forced = true;
    }

    // Events
    canvas.addEventListener('wheel', function (event) {
      if (!model) return;
      var rect = canvas.getBoundingClientRect();
      var dy = event.deltaY * (event.deltaMode === 1 ? 16 : (event.deltaMode === 2 ? cssH : 1));
      var zoomingOut = dy > 0;
      if (zoomingOut && view.k <= fitK * 1.0001) return;
      event.preventDefault();
      if (anim) { global.cancelAnimationFrame(anim); anim = null; }
      zoomAt(Math.exp(-dy * (event.ctrlKey ? 0.01 : 0.0018)), event.clientY - rect.top);
    }, { passive: false });

    var drag = null;
    canvas.addEventListener('pointerdown', function (event) {
      if (!model) return;
      var rect = canvas.getBoundingClientRect();
      var px = event.clientX - rect.left, py = event.clientY - rect.top;
      if (px >= cssW - MINIMAP_W) {
        drag = { minimap: true };
        moveMinimap(py);
      } else {
        drag = { y: event.clientY, oy: view.oy, moved: false };
      }
      canvas.setPointerCapture(event.pointerId);
    });
    canvas.addEventListener('pointermove', function (event) {
      var rect = canvas.getBoundingClientRect();
      var px = event.clientX - rect.left, py = event.clientY - rect.top;
      if (drag && drag.minimap) { moveMinimap(py); return; }
      if (drag) {
        var dy = event.clientY - drag.y;
        if (Math.abs(dy) > 3) drag.moved = true;
        if (drag.moved) {
          view = clampView({ k: view.k, oy: drag.oy - dy / view.k });
          canvas.style.cursor = 'grabbing';
          schedule();
        }
        return;
      }
      var item = unitAt(px, py);
      var current = hover && hover.unit;
      if (item !== current) {
        hover = item ? { unit: item } : null;
        canvas.style.cursor = item ? 'pointer' : 'grab';
        onHover(item ? describe(item) : '');
        setHighlight();
      }
    });
    // A click waits briefly so a double-click zooms without also selecting twice.
    var clickTimer = null;
    canvas.addEventListener('pointerup', function (event) {
      var was = drag;
      drag = null;
      canvas.style.cursor = 'grab';
      if (!was || was.minimap || was.moved) return;
      if (clickTimer) { global.clearTimeout(clickTimer); clickTimer = null; return; }
      var rect = canvas.getBoundingClientRect();
      var item = unitAt(event.clientX - rect.left, event.clientY - rect.top);
      clickTimer = global.setTimeout(function () {
        clickTimer = null;
        onPick(item ? descriptor(item) : null);
      }, 240);
    });
    canvas.addEventListener('pointerleave', function () {
      if (drag) return;
      if (hover) { hover = null; onHover(''); setHighlight(); }
    });
    canvas.addEventListener('dblclick', function (event) {
      var rect = canvas.getBoundingClientRect();
      var item = unitAt(event.clientX - rect.left, event.clientY - rect.top);
      if (item) zoomToUnit(item);
      else animateTo({ k: view.k * 2, oy: view.oy + (event.clientY - rect.top) / view.k - cssH / (view.k * 2) / 2 });
    });
    canvas.addEventListener('keydown', function (event) {
      if (event.key === '+' || event.key === '=') { zoomAt(1.4, cssH / 2); event.preventDefault(); }
      else if (event.key === '-' || event.key === '_') { zoomAt(1 / 1.4, cssH / 2); event.preventDefault(); }
      else if (event.key === '0') { animateTo({ k: fitK, oy: 0 }); event.preventDefault(); }
      else if (event.key === 'f' || event.key === 'F') { toggleFull(); event.preventDefault(); }
      else if (event.key === 'ArrowDown') { view = clampView({ k: view.k, oy: view.oy + cssH * 0.2 / view.k }); schedule(); event.preventDefault(); }
      else if (event.key === 'ArrowUp') { view = clampView({ k: view.k, oy: view.oy - cssH * 0.2 / view.k }); schedule(); event.preventDefault(); }
    });

    function moveMinimap(py) {
      var wy = py / cssH * model.H;
      view = clampView({ k: view.k, oy: wy - cssH / view.k / 2 });
      schedule();
    }

    function toggleFull() {
      var center = model ? view.oy + cssH / view.k / 2 : 0;
      var ratio = model ? view.k / fitK : 1;
      wrap.classList.toggle('full');
      document.body.classList.toggle('topomap-lock', wrap.classList.contains('full'));
      wrap.querySelector('[data-act="full"]').textContent = wrap.classList.contains('full') ? 'Exit full screen' : 'Full screen';
      relayout();
      if (model) {
        var k = clamp(fitK * ratio, fitK, maxK);
        view = clampView({ k: k, oy: center - cssH / k / 2 });
        draw();
      }
      canvas.focus();
    }

    wrap.querySelector('.topomap-bar').addEventListener('click', function (event) {
      var button = event.target.closest('button');
      if (!button || !model) return;
      var act = button.getAttribute('data-act');
      if (act === 'in') animateTo({ k: view.k * 1.8, oy: view.oy + cssH / view.k / 2 - cssH / (view.k * 1.8) / 2 });
      else if (act === 'out') animateTo({ k: view.k / 1.8, oy: view.oy + cssH / view.k / 2 - cssH / (view.k / 1.8) / 2 });
      else if (act === 'fit') animateTo({ k: fitK, oy: 0 });
      else if (act === 'full') toggleFull();
      else if (act === 'estate') onPick(null);
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && wrap.classList.contains('full')) toggleFull();
    });

    function relayout() {
      sizeCanvas();
      if (!model) return;
      layout(model, cssH);
      setLimits();
      buildMinimap();
    }

    var lastWidth = 0;
    function onResize() {
      var width = wrap.clientWidth;
      if (width === lastWidth && !wrap.classList.contains('full')) return;
      lastWidth = width;
      var ratio = model ? view.k / fitK : 1;
      var center = model ? (view.oy + cssH / view.k / 2) / model.H : 0.5;
      relayout();
      if (model) {
        var k = clamp(fitK * ratio, fitK, maxK);
        view = clampView({ k: k, oy: center * model.H - cssH / k / 2 });
      }
      schedule();
    }
    if (global.ResizeObserver) new global.ResizeObserver(onResize).observe(wrap);
    else global.addEventListener('resize', onResize);

    canvas.style.cursor = 'grab';
    sizeCanvas();

    // A click keeps only the rows that pass through that host, path, sourcetype,
    // site, family, or index, then lays the map out again so they fill the view.
    function rowsFor(desc) {
      if (!desc) return allRows;
      return allRows.filter(function (row) {
        if (desc.col === 'site') return (row.environment || 'unknown') === desc.name;
        if (desc.col === 'host') return (row.data_source || 'unknown') === desc.name;
        if (desc.col === 'ingest_method') return (row.ingest_method || 'Other') === desc.name;
        if (desc.col === 'family') return (row.family || 'unknown') === desc.name;
        if (desc.col === 'endpoint') {
          return (row.endpoint || 'unknown') === desc.name && (!desc.family || (row.family || 'unknown') === desc.family);
        }
        if (desc.col === 'splunk_index') return (row.splunk_index || 'unknown') === desc.name;
        return true;
      });
    }
    var LOOKING = { site: 'site', host: 'host', ingest_method: 'ingestion path', family: 'sourcetype family', endpoint: 'sourcetype', splunk_index: 'index' };
    function show(desc) {
      var kept = rowsFor(desc);
      model = build(kept);
      model.note = desc && !kept.length ? 'Nothing flows through this selection.' : '';
      if (desc && (desc.col === 'family' || desc.col === 'endpoint') && model.groups[2]) {
        model.groups[2].forEach(function (group) {
          if (group.name === (desc.col === 'family' ? desc.name : desc.family)) group.userOpen = true;
        });
      }
      relayout();
      fit();
      hover = null;
      focus = desc ? { desc: desc, unit: findUnit(desc) } : null;
      if (model) setForced();
      var looking = wrap.querySelector('.topomap-looking');
      var back = wrap.querySelector('[data-act="estate"]');
      if (looking) {
        looking.textContent = desc
          ? 'Looking at ' + (LOOKING[desc.col] || desc.col) + ' ' + desc.name
          : 'Whole estate';
      }
      if (back) back.hidden = !desc;
      setHighlight();
      draw();
    }

    return {
      setData: function (rows) {
        allRows = rows || [];
        show(focus && focus.desc);
      },
      setFocus: function (desc) {
        show(desc || null);
      },
      fit: function () { if (model) animateTo({ k: fitK, oy: 0 }); }
    };
  }

  global.TopoMap = { create: create };
})(window);

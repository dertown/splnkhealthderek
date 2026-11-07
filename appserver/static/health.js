/* Shared helpers for the Splunk Health Derek+ HTML pages. */
var Health = (function () {
  var PILL_GOOD = ['GREEN', 'OK', 'ok', 'Healthy', 'approved', 'replied', 'PASS', 'LOCAL', 'READY', 'PROVIDER', 'Approve', 'SET', 'no', 'Turned off on purpose', 'ON PATTERN'];
  var PILL_BAD = ['RED', 'ALERT', 'HOST DOWN', 'DATA SILENT', 'HEARTBEAT ONLY', 'HIGH', 'CLOCK AHEAD', 'FAILED', 'failed', 'FAIL', 'MISCONFIG', 'STALLED', 'MISSING', 'Gone quiet', 'No events in 30 days', 'Wrong sourcetype', 'QUIET', 'BELOW'];
  var PILL_WARN = ['YELLOW', 'DELAYED', 'WARMUP', 'N/A', 'open', 'TESTING', 'WAITING', 'RECURRING', 'Source gone quiet', 'New this week', 'In the catch-all', 'LEARNING'];

  function root() {
    var path = window.location.pathname || '';
    var at = path.indexOf('/app/');
    return at >= 0 ? path.substring(0, at) : '';
  }

  function appName() {
    var match = (window.location.pathname || '').match(/\/app\/([^/]+)/);
    return match ? match[1] : 'splunk_exec_health';
  }

  function page(name) {
    return root() + '/app/' + appName() + '/' + name;
  }

  function api(kind) {
    return window.location.origin + root() + '/splunkd/__raw/servicesNS/nobody/splunk_exec_health/data/healthdash/' + kind;
  }

  function csrf() {
    var port = window.location.port || '8000';
    var cookies = (document.cookie || '').split(';');
    for (var i = 0; i < cookies.length; i++) {
      var parts = cookies[i].trim().split('=');
      if (parts[0].indexOf('splunkweb_csrf_token_') === 0 && (parts[0] === 'splunkweb_csrf_token_' + port || parts[0].indexOf('splunkweb_csrf_token_') === 0)) {
        return decodeURIComponent((parts.slice(1).join('=') || '').replace(/^"|"$/g, ''));
      }
    }
    return '';
  }

  function headers() {
    var out = { 'X-Requested-With': 'XMLHttpRequest' };
    var key = csrf();
    if (key) out['X-Splunk-Form-Key'] = key;
    return out;
  }

  function handle(response) {
    return response.text().then(function (text) {
      var data;
      try { data = JSON.parse(text); } catch (e) {
        var snippet = text.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 180);
        throw new Error('The server did not return JSON (HTTP ' + response.status + '). ' + (snippet || 'Empty response. Restart Splunk so the new endpoint loads.'));
      }
      var body = data.payload !== undefined ? (typeof data.payload === 'string' ? JSON.parse(data.payload) : data.payload) : data;
      if (!response.ok || body.success === false) throw new Error(body.error || ('Request failed (' + response.status + ')'));
      return body.rows || [];
    });
  }

  function query(name, params) {
    var qs = 'name=' + encodeURIComponent(name);
    Object.keys(params || {}).forEach(function (key) {
      qs += '&' + encodeURIComponent(key) + '=' + encodeURIComponent(params[key]);
    });
    return fetch(api('query') + '?' + qs, { credentials: 'same-origin', headers: headers() }).then(handle);
  }

  function act(name, params) {
    return fetch(api('act'), {
      method: 'POST', credentials: 'same-origin',
      headers: Object.assign({ 'Content-Type': 'application/json' }, headers()),
      body: JSON.stringify({ name: name, params: params || {} })
    }).then(handle);
  }

  function esc(value) {
    return String(value === undefined || value === null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function pill(value) {
    var text = String(value === undefined || value === null ? '' : value);
    var kind = 'neutral';
    if (PILL_GOOD.indexOf(text) >= 0) kind = 'good';
    else if (PILL_BAD.indexOf(text) >= 0) kind = 'bad';
    else if (PILL_WARN.indexOf(text) >= 0) kind = 'warn';
    else if (text === 'Approve' || text === 'Dismiss' || text === 'Fix') kind = 'link';
    if (!text) return '';
    return '<span class="pill ' + kind + '">' + esc(text) + '</span>';
  }

  var PILL_COLUMNS = ['severity', 'status', 'state', 'baseline_state', 'latency_state', 'hec_state', 'decision', 'recurring', 'approve', 'dismiss', 'key_state', 'conn_status', 'ai_status', 'tile_status', 'overall_status', 'agent_status', 'heartbeat_band', 'season_state'];

  function table(el, rows, columns, onClick) {
    columns = columns || Object.keys((rows[0] || {})).filter(function (key) { return key.charAt(0) !== '_' && key !== 'api_key'; })
      .map(function (key) { return { key: key, label: key.replace(/_/g, ' ') }; });
    if (!rows.length) { el.innerHTML = '<p class="note">Nothing to show.</p>'; return; }
    var html = '<div class="table-wrap"><table><thead><tr>';
    columns.forEach(function (col) { html += '<th>' + esc(col.label) + '</th>'; });
    html += '</tr></thead><tbody>';
    rows.forEach(function (row, index) {
      html += '<tr' + (onClick ? ' class="clickable" data-row="' + index + '"' : '') + '>';
      columns.forEach(function (col) {
        var value = row[col.key];
        html += '<td data-col="' + esc(col.key) + '">' + (PILL_COLUMNS.indexOf(col.key) >= 0 || col.pill ? pill(value) : esc(value)) + '</td>';
      });
      html += '</tr>';
    });
    html += '</tbody></table></div>';
    el.innerHTML = html;
    if (onClick) {
      Array.prototype.forEach.call(el.querySelectorAll('tr.clickable'), function (tr) {
        tr.addEventListener('click', function (event) {
          var cell = event.target.closest('td');
          onClick(rows[Number(tr.getAttribute('data-row'))], cell ? cell.getAttribute('data-col') : '');
        });
      });
    }
  }

  function stats(el, items) {
    el.innerHTML = items.map(function (item) {
      return '<div class="stat"><div class="val ' + (item.kind || '') + '">' + esc(item.val) + '</div><div class="lbl">' + esc(item.lbl) + '</div></div>';
    }).join('');
  }

  function num(value) {
    var parsed = Number(value);
    return isNaN(parsed) ? 0 : parsed;
  }

  function fail(el, error) {
    el.innerHTML = '<p class="note error">' + esc(error && error.message ? error.message : error) + '</p>';
  }

  function link(id, view) {
    var el = document.getElementById(id);
    if (el) el.href = page(view);
  }

  function inlineHtml(text) {
    var bits = String(text || '').split('`');
    return bits.map(function (bit, index) {
      return index % 2 === 1 ? '<code>' + esc(bit) + '</code>' : esc(bit);
    }).join('');
  }

  function stepList(body) {
    var parts = String(body || '').split(/\s+(?=\d{1,2}[.)]\s+)/);
    var intro = '';
    var items = [];
    parts.forEach(function (part) {
      var match = part.match(/^(\d{1,2})[.)]\s+([\s\S]*)$/);
      if (match) items.push(match[2].trim());
      else if (!items.length) intro = part.trim();
      else if (items.length) items[items.length - 1] += ' ' + part.trim();
    });
    if (items.length < 2) return null;
    return { intro: intro, items: items };
  }

  function sections(text) {
    var cleaned = String(text || '').split('\n').filter(function (line) {
      return !/^(SAMPLE_CHECK|FIX_CHECK|SUPPORT_TICKET):/i.test(line.trim());
    }).join('\n').trim();
    if (!cleaned) return [];
    var found = [];
    var match;
    var bold = /\*\*([^*]+?)\*\*\s*:?\s*/g;
    while ((match = bold.exec(cleaned))) {
      found.push({ title: match[1].replace(/\s*:\s*$/, '').trim(), at: match.index, after: bold.lastIndex });
    }
    if (!found.length) {
      var lines = /(?:^|\n)\s*(?:#{1,3}\s+)?([A-Za-z][^:\n]{2,80})\s*:\s+/g;
      while ((match = lines.exec(cleaned))) {
        var title = match[1].trim();
        var at = match.index + (match[0].charAt(0) === '\n' ? 1 : 0);
        found.push({ title: title, at: at, after: lines.lastIndex });
      }
    }
    if (!found.length) return [{ title: 'Suggested fix', body: cleaned }];
    var out = [];
    if (found[0].at > 0) {
      var lead = cleaned.slice(0, found[0].at).trim();
      if (lead) out.push({ title: 'Summary', body: lead });
    }
    found.forEach(function (item, index) {
      var end = index + 1 < found.length ? found[index + 1].at : cleaned.length;
      out.push({ title: item.title, body: cleaned.slice(item.after, end).trim() });
    });
    return out.filter(function (item) { return item.title || item.body; });
  }

  function sectionBody(body) {
    var steps = stepList(body);
    if (!steps) return '<p>' + inlineHtml(body) + '</p>';
    var html = steps.intro ? '<p>' + inlineHtml(steps.intro) + '</p>' : '';
    html += '<ol>' + steps.items.map(function (item) { return '<li>' + inlineHtml(item) + '</li>'; }).join('') + '</ol>';
    return html;
  }

  function reply(text, meta) {
    var parts = sections(text);
    meta = meta || {};
    if (!parts.length) return '<p class="note">No suggestion yet.</p>';
    if (parts.length === 1 && parts[0].title === 'Suggested fix' && parts[0].body.length < 320 && parts[0].body.indexOf('\n') < 0) {
      return '<p class="note">' + inlineHtml(parts[0].body) + '</p>';
    }
    var html = '<div class="table-wrap"><table class="reply-table"><thead><tr><th>Section</th><th>Detail</th></tr></thead><tbody>';
    parts.forEach(function (part) {
      html += '<tr><td>' + esc(part.title) + '</td><td>' + sectionBody(part.body) + '</td></tr>';
    });
    html += '</tbody></table></div>';
    var note = [];
    if (meta.from_ai && meta.from_ai !== 'none') note.push(meta.from_ai);
    if (meta.requested_at && meta.requested_at !== 'none') note.push(meta.requested_at);
    if (note.length) html += '<p class="note">' + esc(note.join(' · ')) + '</p>';
    if (meta.earlier_ai_suggestion && meta.earlier_ai_suggestion !== 'none') {
      html += '<p class="note">Earlier suggestion: ' + esc(meta.earlier_ai_suggestion) + '</p>';
    }
    return html;
  }

  var helpPop = null;
  var helpBtn = null;
  function closeHelp() {
    if (!helpPop) return;
    helpPop.hidden = true;
    if (helpBtn) helpBtn.setAttribute('aria-expanded', 'false');
    helpBtn = null;
  }
  function placeHelp(btn) {
    var rect = btn.getBoundingClientRect();
    var width = Math.min(360, window.innerWidth - 24);
    var left = rect.right - width;
    if (left < 8) left = 8;
    helpPop.style.width = width + 'px';
    helpPop.style.top = (window.scrollY + rect.bottom + 6) + 'px';
    helpPop.style.left = (window.scrollX + left) + 'px';
  }
  function openHelp(btn, text) {
    if (!helpPop) {
      helpPop = document.createElement('div');
      helpPop.className = 'help-pop';
      helpPop.setAttribute('role', 'dialog');
      helpPop.hidden = true;
      document.body.appendChild(helpPop);
      document.addEventListener('click', function (event) {
        if (helpPop.hidden) return;
        if (event.target.closest && (event.target.closest('.help-pop') || event.target.closest('.help-btn'))) return;
        closeHelp();
      });
      document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') closeHelp();
      });
      window.addEventListener('resize', closeHelp);
    }
    if (helpBtn === btn && !helpPop.hidden) { closeHelp(); return; }
    closeHelp();
    helpPop.textContent = text;
    helpPop.hidden = false;
    helpBtn = btn;
    btn.setAttribute('aria-expanded', 'true');
    placeHelp(btn);
  }
  function help(root) {
    if (helpBtn && helpBtn.ownerDocument && !document.body.contains(helpBtn)) closeHelp();
    var scope = root && root.querySelectorAll ? root : document;
    Array.prototype.forEach.call(scope.querySelectorAll('h2.section-title[data-help]'), function (heading) {
      if (heading.querySelector('.help-btn')) return;
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'help-btn';
      btn.setAttribute('aria-expanded', 'false');
      btn.setAttribute('aria-label', 'What this panel shows');
      btn.textContent = '?';
      heading.appendChild(btn);
      btn.addEventListener('click', function (event) {
        event.preventDefault();
        event.stopPropagation();
        openHelp(btn, heading.getAttribute('data-help'));
      });
    });
  }

  function chromeTop() {
    var top = 0;
    var selectors = ['#header', '.shared-header', 'header', '#appbar', '.app-bar', '.navbar'];
    selectors.forEach(function (sel) {
      Array.prototype.forEach.call(document.querySelectorAll(sel), function (el) {
        if (el.closest && el.closest('.sidenav, .page')) return;
        var rect = el.getBoundingClientRect();
        if (rect.width > 400 && rect.height >= 24 && rect.height <= 140 && rect.top < 160 && rect.bottom > top) top = rect.bottom;
      });
    });
    return top;
  }

  function mountNav(attempt) {
    if (document.querySelector('.sidenav')) return;
    if (!document.querySelector('.page')) {
      if ((attempt || 0) < 25) window.setTimeout(function () { mountNav((attempt || 0) + 1); }, 80);
      return;
    }
    var current = ((window.location.pathname || '').split('/').pop() || '').split('?')[0];
    var items = [
      { external: true, label: 'Splunk home' },
      { group: 'Health' },
      { view: 'executive_overview', label: 'Executive overview' },
      { view: 'host_heartbeat', label: 'Host Heartbeat' },
      { view: 'hec_performance', label: 'HEC Tokens' },
      { view: 'sc4s_edge', label: 'SC4S & Edge' },
      { view: 'data_topology', label: 'Data Topology' },
      { group: 'Agent' },
      { view: 'data_quality_agent', label: 'Data Quality Agent' },
      { view: 'health_reports', label: 'Reports' },
      { group: 'Configure' },
      { view: 'ai_provider_setup', label: 'AI provider' },
      { group: 'Help' },
      { view: 'readme', label: 'README' },
      { view: 'about', label: 'About' }
    ];
    var nav = document.createElement('div');
    nav.className = 'sidenav';
    nav.setAttribute('role', 'navigation');
    nav.setAttribute('aria-label', 'Splunk Health Derek+');
    var brand = document.createElement('div');
    brand.className = 'nav-brand';
    brand.textContent = 'Splunk Health Derek+';
    nav.appendChild(brand);
    items.forEach(function (item) {
      if (item.group) {
        var group = document.createElement('div');
        group.className = 'nav-group';
        group.textContent = item.group;
        nav.appendChild(group);
        return;
      }
      var linkEl = document.createElement('a');
      linkEl.textContent = item.label;
      if (item.external) {
        linkEl.className = 'nav-home';
        linkEl.href = root() + '/app/launcher/home';
      } else {
        linkEl.href = page(item.view);
        if (item.view === current) {
          linkEl.className = 'current';
          linkEl.setAttribute('aria-current', 'page');
        }
      }
      nav.appendChild(linkEl);
    });
    document.body.appendChild(nav);
    document.body.classList.add('has-nav');
    function pin() { nav.style.top = chromeTop() + 'px'; }
    pin();
    window.addEventListener('resize', pin);
  }

  mountNav(0);
  help(document);
  return { query: query, act: act, table: table, stats: stats, num: num, fail: fail, link: link, esc: esc, page: page, help: help, sections: sections, reply: reply };
})();

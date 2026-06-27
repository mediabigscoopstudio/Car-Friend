/* Car Friend Inspector — resilient online-first sync (§5.11)
   - online/offline banner + body state
   - GPS coords cached once for photo watermarking
   - photo upload queue with exponential backoff + flush on reconnect
   - localStorage draft cache (never lose an in-progress sheet on refresh/crash)
   No service worker / IndexedDB — this is the resilient-online-first tier. */
(function () {
  // ---- online / offline ----
  function paint() {
    var off = !navigator.onLine;
    document.body.classList.toggle('is-offline', off);
    var bar = document.getElementById('cf-offline');
    if (bar) bar.classList.toggle('show', off);
    updateSyncLine();
  }
  window.addEventListener('online', paint);
  window.addEventListener('offline', paint);

  // ---- GPS (best-effort, shared by all photo captures) ----
  window.__cfCoords = null;
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(function (p) {
      window.__cfCoords = { lat: p.coords.latitude, lng: p.coords.longitude };
    }, function () {}, { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 });
  }

  // ---- pending photo counter (for the sync line) ----
  var pending = 0;
  function bump(n) { pending = Math.max(0, pending + n); updateSyncLine(); }
  function updateSyncLine() {
    var el = document.getElementById('cf-sync-line');
    if (!el) return;
    if (!navigator.onLine) { el.className = 'sync-line pending'; el.innerHTML = '<span class="pulse"></span> Offline — saved on this device'; }
    else if (pending > 0) { el.className = 'sync-line pending'; el.innerHTML = '<span class="pulse"></span> ' + pending + ' photo' + (pending > 1 ? 's' : '') + ' uploading'; }
    else { el.className = 'sync-line ok'; el.innerHTML = '<span class="pulse"></span> All synced'; }
  }

  // ---- photo upload with retry/backoff ----
  // onState(state, data): 'uploading' | 'done'(data=json) | 'retry'(data=attempt) | 'failed'
  window.cfUploadPhoto = function (file, key, opts) {
    var csrf = opts.csrf, rid = opts.rid, onState = opts.onState || function () {};
    var crid = 'ph_' + Date.now() + '_' + Math.random().toString(36).slice(2);
    var attempts = 0;
    bump(1);
    function attempt() {
      onState(attempts === 0 ? 'uploading' : 'retry', attempts);
      var fd = new FormData();
      fd.append('file', file); fd.append('key', key);
      fd.append('csrfmiddlewaretoken', csrf); fd.append('crid', crid);
      if (window.__cfCoords) { fd.append('lat', window.__cfCoords.lat); fd.append('lng', window.__cfCoords.lng); }
      fetch('/inspect/' + rid + '/photo', { method: 'POST', body: fd, headers: { 'X-Requested-With': 'fetch' } })
        .then(function (r) { if (!r.ok) throw new Error('http'); return r.json(); })
        .then(function (j) { if (!j.ok) throw new Error('app'); bump(-1); onState('done', j); })
        .catch(function () {
          attempts++;
          if (attempts > 6) { bump(-1); onState('failed'); return; }
          onState('retry', attempts);
          var delay = Math.min(30000, 1000 * Math.pow(2, attempts));
          var timer = setTimeout(function () { if (navigator.onLine) attempt(); }, delay);
          window.addEventListener('online', function once() {
            window.removeEventListener('online', once); clearTimeout(timer); attempt();
          });
        });
    }
    attempt();
  };

  // ---- localStorage draft cache ----
  window.cfDraft = {
    k: function (rid, key) { return 'cfd_' + rid + '_' + key; },
    save: function (rid, key, obj) { try { localStorage.setItem(this.k(rid, key), JSON.stringify(obj)); } catch (e) {} },
    load: function (rid, key) { try { return JSON.parse(localStorage.getItem(this.k(rid, key)) || 'null'); } catch (e) { return null; } },
    clear: function (rid, key) { try { localStorage.removeItem(this.k(rid, key)); } catch (e) {} }
  };

  // ---- block checkpoint submits while offline (online-first), keep the draft ----
  document.addEventListener('submit', function (e) {
    if (!navigator.onLine && e.target.matches('[data-needs-online]')) {
      e.preventDefault();
      window.cfToast && cfToast('Offline — reconnect to save. Your input is kept.');
    }
  }, true);

  paint();
})();

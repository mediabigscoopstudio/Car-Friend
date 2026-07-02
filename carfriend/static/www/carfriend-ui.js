/* Car Friend — www dashboard helpers: journey carousel, live countdowns,
   filter-drawer clone. Baseline content is visible without JS. */
(function () {
  "use strict";

  // ── §7.7 journey: center on current step, drag to peek (no auto-scroll) ──
  function initJourney() {
    var wrap = document.querySelector('.cf-carousel'); if (!wrap) return;
    var track = wrap.querySelector('.cf-carousel-track');
    var chips = track.querySelectorAll('.cf-chip-step'); if (!chips.length) return;
    var cur = track.querySelector('.cf-chip-step.is-current') || chips[0];
    var t = 0, cx = function (el) { return el.offsetLeft + el.offsetWidth / 2; };
    function limits() { var w = wrap.clientWidth; return { max: w / 2 - cx(chips[0]), min: w / 2 - cx(chips[chips.length - 1]), w: w }; }
    function set(x) { var L = limits(); x = L.min < L.max ? Math.min(L.max, Math.max(L.min, x)) : L.max; t = x; track.style.transform = 'translateX(' + Math.round(x) + 'px)'; }
    function center() { set(limits().w / 2 - cx(cur)); }
    center(); window.addEventListener('resize', center); window.addEventListener('load', center); setTimeout(center, 250);
    var down = false, sx = 0, st = 0, moved = false;
    wrap.addEventListener('pointerdown', function (e) { down = true; moved = false; sx = e.clientX; st = t; wrap.classList.add('grabbing'); });
    wrap.addEventListener('pointermove', function (e) { if (!down) return; if (Math.abs(e.clientX - sx) > 3) moved = true; set(st + (e.clientX - sx)); });
    ['pointerup', 'pointercancel', 'pointerleave'].forEach(function (ev) { wrap.addEventListener(ev, function () { down = false; wrap.classList.remove('grabbing'); }); });
    wrap.addEventListener('click', function (e) { if (moved) { e.preventDefault(); e.stopPropagation(); } }, true);
  }

  // ── §7.9 live countdowns ──
  function initTimers() {
    document.querySelectorAll('.cf-timer[data-secs]').forEach(function (el) {
      var s = +el.dataset.secs, out = el.querySelector('.t'); if (!out) return;
      function p() { var m = Math.floor(s / 60), x = s % 60; out.textContent = (m < 10 ? '0' : '') + m + ':' + (x < 10 ? '0' : '') + x; if (s <= 90) el.classList.add('low'); }
      p(); var id = setInterval(function () { if (s > 0) { s--; p(); } else { clearInterval(id); } }, 1000);
    });
  }

  // ── §7.8 filter drawer: clone desktop filters into the mobile drawer; toggle chips ──
  function initFilters() {
    var src = document.getElementById('filterContent'), dst = document.getElementById('drawerBody');
    if (src && dst && !dst.querySelector('#filterContentMobile')) {
      var c = src.cloneNode(true); c.id = 'filterContentMobile'; dst.appendChild(c);
    }
    document.addEventListener('click', function (e) {
      var chip = e.target.closest('.cf-fchip'); if (chip) { e.preventDefault(); chip.classList.toggle('is-on'); }
    });
  }

  function boot() { initJourney(); initTimers(); initFilters(); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();

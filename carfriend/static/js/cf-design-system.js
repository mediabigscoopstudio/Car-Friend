/* Car Friend — green design system JS (public www site).
   Class toggles + counters + smooth scroll. Touches no links, forms, or
   the hero plate-lookup handlers (binds by class/data-attr only). */
(function () {
  // navbar frost on scroll (the real bar is .cf-nav)
  var nav = document.querySelector('.cf-nav');
  if (nav) window.addEventListener('scroll', function () {
    nav.classList.toggle('cf-scrolled', window.scrollY > 48);
  }, { passive: true });

  // stat counter animation — opt-in via data-target="2500" on a .stat-num
  if ('IntersectionObserver' in window) {
    var cObs = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        var el = e.target, target = +el.dataset.target;
        if (!target) return;
        var suffix = el.querySelector('em') ? el.querySelector('em').outerHTML : '';
        var cur = 0, step = target / 55;
        var tick = setInterval(function () {
          cur = Math.min(cur + step, target);
          el.innerHTML = Math.floor(cur).toLocaleString('en-IN') + suffix;
          if (cur >= target) clearInterval(tick);
        }, 28);
        cObs.unobserve(el);
      });
    }, { threshold: 0.5 });
    document.querySelectorAll('.stat-num[data-target]').forEach(function (el) { cObs.observe(el); });
  }

  // smooth scroll for in-page anchors (ignores bare href="#", so it never
  // hijacks reset links like the hero's "Check another car")
  document.querySelectorAll('a[href^="#"]').forEach(function (a) {
    a.addEventListener('click', function (e) {
      var hash = a.getAttribute('href');
      if (hash === '#' || hash.length < 2) return;
      var t = document.querySelector(hash);
      if (t) { e.preventDefault(); t.scrollIntoView({ behavior: 'smooth' }); }
    });
  });
})();

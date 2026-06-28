/* CarFriend brand kit — scroll reveal + navbar frost
   Loaded at body end in www/base.html. Pure presentation; adds/removes
   classes only, never touches links, forms, or existing handlers. */
(function () {
  var rm = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // ---- scroll reveal ----
  var els = document.querySelectorAll('section, .cf-reveal, .reveal-target, [data-cf-reveal]');
  if (rm || !('IntersectionObserver' in window)) {
    els.forEach(function (el) { el.classList.add('cf-reveal', 'cf-in'); });
  } else {
    els.forEach(function (el) { el.classList.add('cf-reveal'); });
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add('cf-in'); io.unobserve(e.target); }
      });
    }, { threshold: 0.07 });
    els.forEach(function (el) { io.observe(el); });
  }

  // ---- navbar frost on scroll ----
  var nav = document.querySelector('.cf-nav, [data-hook="header"], header, nav, #SITE_HEADER');
  function frost() { if (nav) nav.classList.toggle('cf-scrolled', window.scrollY > 40); }
  window.addEventListener('scroll', frost, { passive: true });
  frost();
})();

/* =====================================================================
   CBN Sierra Leone — LITE site script
   ---------------------------------------------------------------------
   Everything the shared header/footer and pages need, with no backend
   calls except on donate.html (which has its own script):

     • mobile hamburger + mega-menu accordions
     • full-screen site search (Ctrl+K)          — hard-coded index below
     • EN / KR / FR language switcher             — stored in localStorage
     • animated impact counters, scroll reveal, progress bars
     • category filter tabs (projects / blog)
     • footer year

   The site supports both the local Python server and static Vercel hosting.
   Header/footer partials are loaded here when the page is served statically.
   ===================================================================== */
(function () {
  'use strict';

  function normalizeStaticPaths(html) {
    return html.replace(/(href|src)="(?!https?:|\/|#|mailto:|tel:|data:)([^"]+)"/g, '$1="/$2"');
  }

  async function includePartials() {
    var placeholders = document.querySelectorAll('[data-include]');
    if (!placeholders.length) return;

    var entries = Array.from(placeholders);
    for (var i = 0; i < entries.length; i++) {
      var placeholder = entries[i];
      var name = placeholder.dataset.include;
      var url = '/partials/' + name + '.html';

      try {
        var response = await fetch(url, { cache: 'no-store' });
        if (!response.ok) continue;
        var html = await response.text();
        html = normalizeStaticPaths(html);
        placeholder.insertAdjacentHTML('afterend', html);
        placeholder.remove();
      } catch (error) {
        console.warn('Unable to load partial:', name, error);
      }
    }
  }

  function markCurrentNav() {
    var path = (window.location.pathname || '/').replace(/\/+$/, '') || '/';
    var key = 'index';

    if (path === '/' || /\/index\.html?$/.test(path)) {
      key = 'index';
    } else if (/\/about\.html?$/.test(path)) {
      key = 'about';
    } else if (/\/projects(?:\.html|\/|$)/.test(path)) {
      key = 'projects';
    } else if (/\/get-involved\.html?$/.test(path)) {
      key = 'get-involved';
    } else if (/\/contact\.html?$/.test(path)) {
      key = 'contact';
    } else if (/\/donate\.html?$/.test(path)) {
      key = 'donate';
    } else if (/\/news\.html?$/.test(path) || /\/blog(?:\/|$)/.test(path)) {
      key = 'news';
    }

    document.querySelectorAll('.nav-list a[data-nav]').forEach(function (link) {
      var isActive = link.dataset.nav === key;
      link.classList.toggle('active', isActive);
      if (link.parentElement) {
        link.parentElement.classList.toggle('active', isActive);
      }
    });
  }

  async function initSite() {
    await includePartials();
    markCurrentNav();

    /* ------------------------------------------------------------------
       Mobile menu
       ------------------------------------------------------------------ */
    var toggle  = document.querySelector('.menu-toggle');
    var navList = document.querySelector('.nav-list');

    if (toggle && navList) {
      toggle.addEventListener('click', function () {
        toggle.classList.toggle('is-active');
        navList.classList.toggle('is-open');
        toggle.setAttribute('aria-expanded', toggle.classList.contains('is-active'));
      });
    }
    document.querySelectorAll('.nav-list > li.has-mega > a').forEach(function (link) {
      link.addEventListener('click', function (e) {
        if (window.innerWidth <= 860) {
          e.preventDefault();
          var li = link.parentElement;
          li.parentElement.querySelectorAll('li.has-mega').forEach(function (o) { if (o !== li) o.classList.remove('is-open'); });
          li.classList.toggle('is-open');
        }
      });
    });
    document.querySelectorAll('.nav-list a').forEach(function (a) {
      a.addEventListener('click', function () {
        if (window.innerWidth <= 860 && !a.parentElement.classList.contains('has-mega')) {
          if (toggle) toggle.classList.remove('is-active');
          if (navList) navList.classList.remove('is-open');
        }
      });
    });
    var rt;
    window.addEventListener('resize', function () {
      clearTimeout(rt);
      rt = setTimeout(function () {
        if (window.innerWidth > 860) {
          if (toggle) toggle.classList.remove('is-active');
          if (navList) navList.classList.remove('is-open');
          document.querySelectorAll('.nav-list > li.is-open').forEach(function (li) { li.classList.remove('is-open'); });
        }
      }, 150);
    });

    /* ------------------------------------------------------------------
       Site search (hard-coded index — add a line when you add a page)
       ------------------------------------------------------------------ */
    var INDEX = [
      { t: 'Home',                               s: 'Page',             u: '/index.html',              k: 'home community builders network sierra leone' },
      { t: 'Donate',                             s: 'Page',             u: '/donate.html',             k: 'donate donation give orange money africell card monime' },
      { t: 'About Us',                           s: 'Page',             u: '/about.html',              k: 'about who we are' },
      { t: 'Mission & Vision',                   s: 'About Us',         u: '/about.html#mission',      k: 'mission vision purpose' },
      { t: 'Our Team',                           s: 'About Us',         u: '/about.html#team',         k: 'team staff aminata ibrahim fatmata isata' },
      { t: 'History & Achievements',             s: 'About Us',         u: '/about.html#history',      k: 'history founded milestones ebola' },
      { t: 'Core Values',                        s: 'About Us',         u: '/about.html#values',       k: 'values integrity compassion empowerment inclusion' },
      { t: 'Our Partners',                       s: 'About Us',         u: '/about.html#partners',     k: 'partners unicef usaid undp wateraid' },
      { t: 'All Projects',                       s: 'Page',             u: '/projects.html',           k: 'projects work programmes' },
      { t: 'Safe Water for Kono District',       s: 'Current Projects', u: '/projects/safe-water-kono-district.html',          k: 'water borehole kono solar wash' },
      { t: "Girls' Education Initiative",        s: 'Current Projects', u: '/projects/girls-education-initiative.html',        k: 'girls education scholarship school bombali bo' },
      { t: "Women's Farming Cooperatives",       s: 'Current Projects', u: '/projects/womens-farming-cooperatives.html',       k: 'women farming cooperatives agriculture northern' },
      { t: 'Rebuilding Rural Primary Schools',   s: 'Current Projects', u: '/projects/rebuilding-rural-primary-schools.html',  k: 'school rebuild primary kailahun' },
      { t: 'Maternal & Child Health Outreach',   s: 'Current Projects', u: '/projects/maternal-child-health-outreach.html',    k: 'maternal child health pujehun clinic nurse' },
      { t: 'Youth Vocational Skills Programme',  s: 'Current Projects', u: '/projects/youth-vocational-skills-programme.html', k: 'youth vocational skills carpentry tailoring ict bo kenema' },
      { t: 'Ebola Community Response',           s: 'Past Projects',    u: '/projects/ebola-community-response.html',          k: 'ebola response health mobilisers 2014' },
      { t: 'Get Involved',                       s: 'Page',             u: '/get-involved.html',       k: 'get involved volunteer partner' },
      { t: 'Volunteer Opportunities',            s: 'Get Involved',     u: '/get-involved.html#volunteer', k: 'volunteer roles apply' },
      { t: 'Partner with CBN',                   s: 'Get Involved',     u: '/get-involved.html#partner',   k: 'partner corporate sponsorship' },
      { t: 'News & Updates',                     s: 'Page',             u: '/news.html',               k: 'news blog events stories' },
      { t: 'Youth Skills Programme Launches in Bo',      s: 'Blog',     u: '/blog/youth-skills-programme-bo.html', k: 'blog youth skills bo' },
      { t: 'What 24 Boreholes Really Mean for Kono',     s: 'Blog',     u: '/blog/boreholes-kono.html',            k: 'blog boreholes kono water' },
      { t: 'Why Sierra Leone Needs Locally-Led Development', s: 'Blog', u: '/blog/locally-led-development.html',   k: 'blog policy localisation donors' },
      { t: 'Upcoming Events',                    s: 'News & Updates',   u: '/news.html#events',        k: 'events gala open day run 2026' },
      { t: 'Success Stories',                    s: 'News & Updates',   u: '/news.html#stories',       k: 'success stories mariama isata mohamed' },
      { t: 'Newsletter',                         s: 'News & Updates',   u: '/news.html#newsletter',    k: 'newsletter subscribe email' },
      { t: 'Contact Us',                         s: 'Page',             u: '/contact.html',            k: 'contact freetown phone email address' }
    ];

    function search(q) {
      var terms = q.toLowerCase().trim().split(/\s+/).filter(Boolean);
      if (!terms.length) return [];
      return INDEX.map(function (i) {
        var hay = (i.t + ' ' + i.s + ' ' + i.k).toLowerCase(), score = 0;
        terms.forEach(function (t) { if (i.t.toLowerCase().indexOf(t) !== -1) score += 10; if (i.s.toLowerCase().indexOf(t) !== -1) score += 5; if (hay.indexOf(t) !== -1) score += 2; });
        return { i: i, score: score };
      }).filter(function (r) { return r.score > 0; }).sort(function (a, b) { return b.score - a.score; }).slice(0, 7).map(function (r) { return r.i; });
    }

    function buildOverlay() {
      if (document.getElementById('searchOverlay')) return;
      var o = document.createElement('div');
      o.id = 'searchOverlay'; o.className = 'search-overlay'; o.setAttribute('role', 'dialog');
      o.innerHTML =
        '<button class="so-close" id="soClose" aria-label="Close search">✕</button>' +
        '<div class="so-inner"><p class="so-label">Search Community Builders Network</p>' +
        '<div class="so-field"><input type="search" id="soInput" placeholder="e.g. water project, volunteer, donate…" autocomplete="off">' +
        '<button class="so-submit" id="soSubmit" aria-label="Search"><svg viewBox="0 0 24 24" style="width:18px;height:18px;stroke:#fff;fill:none;stroke-width:2.5;stroke-linecap:round;"><circle cx="11" cy="11" r="7"/><line x1="16.5" y1="16.5" x2="21" y2="21"/></svg></button></div>' +
        '<div class="so-results" id="soResults"><p class="so-no-results">No results found. Try a different search term.</p></div>' +
        '<div class="so-quick"><span>Quick links:</span><a href="/projects.html">Projects</a><a href="/donate.html">Donate</a><a href="/get-involved.html#volunteer">Volunteer</a><a href="/news.html#events">Events</a><a href="/contact.html">Contact</a></div></div>';
      document.body.appendChild(o);
      var input = document.getElementById('soInput'), results = document.getElementById('soResults');
      function render() {
        var hits = search(input.value);
        results.querySelectorAll('.so-result-item').forEach(function (el) { el.remove(); });
        results.classList.remove('has-results', 'no-match');
        if (!input.value.trim()) return;
        if (!hits.length) { results.classList.add('has-results', 'no-match'); return; }
        results.classList.add('has-results');
        hits.forEach(function (h) {
          var a = document.createElement('a'); a.href = h.u; a.className = 'so-result-item';
          a.innerHTML = '<div class="r-title">' + h.t + '</div><div class="r-section">' + h.s + '</div>';
          results.insertBefore(a, results.firstChild);
        });
      }
      var tmr; input.addEventListener('input', function () { clearTimeout(tmr); tmr = setTimeout(render, 150); });
      input.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); render(); } if (e.key === 'Escape') closeSearch(); });
      document.getElementById('soSubmit').addEventListener('click', render);
      document.getElementById('soClose').addEventListener('click', closeSearch);
      o.addEventListener('click', function (e) { if (e.target === o) closeSearch(); });
    }
    function openSearch() { buildOverlay(); document.getElementById('searchOverlay').classList.add('is-open'); document.body.style.overflow = 'hidden'; setTimeout(function () { document.getElementById('soInput').focus(); }, 80); }
    function closeSearch() { var o = document.getElementById('searchOverlay'); if (o) o.classList.remove('is-open'); document.body.style.overflow = ''; }
    var sBtn = document.querySelector('.util-search-btn, #searchToggle');
    if (sBtn) sBtn.addEventListener('click', openSearch);
    document.addEventListener('keydown', function (e) { if ((e.ctrlKey || e.metaKey) && e.key === 'k') { e.preventDefault(); openSearch(); } if (e.key === 'Escape') closeSearch(); });

    /* ------------------------------------------------------------------
       Language switcher — EN / KR (Krio) / FR
       ------------------------------------------------------------------ */
    var TR = {
      KR: {
        'Building Stronger Communities, One Village at a Time.': 'Wi de Bil Kominiti Bɛtɛ, Wan Vɪlej fɔ Wan Tɛm.',
        'Donate Now': 'Gɪv Mɔni Na', 'Become a Volunteer': 'Kɔmɔt Na Vɔlɔntia', 'Volunteer with CBN': 'Wok Wit CBN',
        'View All Projects': 'Luk Ɔl Di Projɛkt', 'Read full article →': 'Rid Di Ful Atikul →',
        'Your Time Can Transform a Village.': 'Yu Tɛm Kin Chenjam Di Vɪlej.',
        'Contact': 'Kontakt', 'Donate': 'Gɪv', 'Home': 'Ɔm', 'About Us': 'Ɔbawt Wi', 'Projects': 'Projɛkt',
        'Get Involved': 'Jɔyn Wi', 'News & Updates': 'Nius & Nyuz',
        'Safe Water for Kono District': 'Klin Wata fɔ Kono', "Girls' Education Initiative": 'Pikin Gyal Skul Projɛkt', "Women's Farming Cooperatives": 'Umon Fam Grup'
      },
      FR: {
        'Building Stronger Communities, One Village at a Time.': 'Construire des Communautés plus Fortes, un Village à la Fois.',
        'Donate Now': 'Faire un Don', 'Become a Volunteer': 'Devenir Bénévole', 'Volunteer with CBN': 'Bénévolat avec CBN',
        'View All Projects': 'Voir tous les Projets', 'Read full article →': "Lire l'article complet →",
        'Your Time Can Transform a Village.': 'Votre Temps Peut Transformer un Village.',
        'Contact': 'Contact', 'Donate': 'Donner', 'Home': 'Accueil', 'About Us': 'À Propos', 'Projects': 'Projets',
        'Get Involved': "S'impliquer", 'News & Updates': 'Actualités',
        'Safe Water for Kono District': 'Eau Potable pour le District de Kono', "Girls' Education Initiative": "Initiative pour l'Éducation des Filles", "Women's Farming Cooperatives": 'Coopératives Agricoles des Femmes'
      }
    };
    var originals = new Map();
    function textNodes() {
      var w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, { acceptNode: function (n) {
        var p = n.parentElement; if (!p || /^(SCRIPT|STYLE|INPUT|TEXTAREA|NOSCRIPT)$/.test(p.tagName) || !n.nodeValue.trim()) return NodeFilter.FILTER_REJECT; return NodeFilter.FILTER_ACCEPT; } });
      var out = [], n; while ((n = w.nextNode())) out.push(n); return out;
    }
    function applyLang(lang) {
      originals.forEach(function (orig, node) { if (node.parentNode) node.nodeValue = orig; });
      var dict = TR[lang]; if (!dict) return;
      textNodes().forEach(function (node) {
        var text = node.nodeValue; if (!originals.has(node)) originals.set(node, text);
        Object.keys(dict).forEach(function (k) { if (text.indexOf(k) !== -1) text = text.replace(k, dict[k]); });
        node.nodeValue = text;
      });
    }
    function banner(lang) {
      var b = document.getElementById('translateBanner');
      if (lang === 'EN') { if (b) b.classList.remove('show'); return; }
      var names = { KR: 'Krio', FR: 'Français' };
      if (!b) {
        b = document.createElement('div'); b.id = 'translateBanner'; b.className = 'translate-banner';
        b.innerHTML = '<p></p><button class="tb-close" aria-label="Close">✕</button>';
        document.body.appendChild(b);
        b.querySelector('.tb-close').addEventListener('click', function () { setLang('EN'); });
      }
      b.querySelector('p').innerHTML = '🌐 Viewing in <strong>' + names[lang] + '</strong>. Some content may not be fully translated. <a href="#" style="color:var(--cbn-gold);">Switch to English</a>';
      b.querySelector('a').addEventListener('click', function (e) { e.preventDefault(); setLang('EN'); });
      setTimeout(function () { b.classList.add('show'); }, 100);
    }
    function setLang(lang) {
      localStorage.setItem('cbn_lang', lang);
      document.querySelectorAll('.lang-btn').forEach(function (b) { var on = b.dataset.lang === lang; b.classList.toggle('active', on); b.setAttribute('aria-pressed', on); });
      document.documentElement.lang = { EN: 'en', KR: 'kri', FR: 'fr' }[lang] || 'en';
      applyLang(lang); banner(lang);
    }
    document.querySelectorAll('.lang-btn').forEach(function (b) { b.addEventListener('click', function () { setLang(b.dataset.lang); }); });
    var saved = localStorage.getItem('cbn_lang') || 'EN';
    if (saved !== 'EN') setTimeout(function () { setLang(saved); }, 120);

    /* ------------------------------------------------------------------
       Counters, reveal, progress bars, filter tabs, year
       ------------------------------------------------------------------ */
    if ('IntersectionObserver' in window) {
      var counters = document.querySelectorAll('[data-count]');
      var io = new IntersectionObserver(function (es) {
        es.forEach(function (e) {
          if (!e.isIntersecting) return;
          var el = e.target, target = parseInt(el.dataset.count, 10), suffix = el.dataset.suffix || '', start = performance.now();
          (function step(now) {
            var p = Math.min((now - start) / 1600, 1), v = Math.floor(target * (1 - Math.pow(1 - p, 3)));
            el.textContent = v.toLocaleString() + suffix; if (p < 1) requestAnimationFrame(step); else el.textContent = target.toLocaleString() + suffix;
          })(start);
          io.unobserve(el);
        });
      }, { threshold: 0.4 });
      counters.forEach(function (c) { io.observe(c); });

      var reveal = document.querySelectorAll('.project-card, .value-card, .team-card, .mv-card, .tl-item, .blog-card, .success-card, .opp-card, .tier-card');
      reveal.forEach(function (el) { el.style.opacity = '0'; el.style.transform = 'translateY(18px)'; el.style.transition = 'opacity .55s ease, transform .55s ease'; });
      var io2 = new IntersectionObserver(function (es) { es.forEach(function (e) { if (e.isIntersecting) { e.target.style.opacity = '1'; e.target.style.transform = 'none'; io2.unobserve(e.target); } }); }, { threshold: 0.12 });
      reveal.forEach(function (el) { io2.observe(el); });

      var bars = document.querySelectorAll('.progress > span');
      bars.forEach(function (b) { b.dataset.target = b.style.width || '0%'; b.style.width = '0%'; });
      var io3 = new IntersectionObserver(function (es) { es.forEach(function (e) { if (e.isIntersecting) { var b = e.target; setTimeout(function () { b.style.width = b.dataset.target; }, 120); io3.unobserve(b); } }); }, { threshold: 0.4 });
      bars.forEach(function (b) { io3.observe(b); });
    }

    document.querySelectorAll('.filter-tabs').forEach(function (bar) {
      var grid = document.getElementById(bar.dataset.target || '') || bar.nextElementSibling;
      bar.querySelectorAll('button[data-filter]').forEach(function (btn) {
        btn.addEventListener('click', function () {
          bar.querySelectorAll('button').forEach(function (b) { b.classList.remove('is-active'); }); btn.classList.add('is-active');
          var f = btn.dataset.filter;
          if (grid) grid.querySelectorAll('[data-category]').forEach(function (c) { c.classList.toggle('is-hidden', !(f === 'all' || (c.dataset.category || '').split(/\s+/).indexOf(f) !== -1)); });
        });
      });
    });

    var y = document.getElementById('year'); if (y) y.textContent = new Date().getFullYear();
  }

  initSite();
})();

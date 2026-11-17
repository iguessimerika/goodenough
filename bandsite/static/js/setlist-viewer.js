// Setlist sheet-music view: shows every PDF of a set one after another in the running order,
// with the band's notes on top (read-only). Made for stage use on a tablet or laptop:
// page-turn keys (also Bluetooth foot pedals), tap zones, song jump, full screen,
// and the screen stays on.
(() => {
  'use strict';

  const bar = document.getElementById('vw-bar');
  const pagesEl = document.getElementById('vw-pages');
  const jump = document.getElementById('vw-jump');
  const prevButton = document.getElementById('vw-prev');
  const nextButton = document.getElementById('vw-next');
  const fitButton = document.getElementById('vw-fit');
  const fullscreenButton = document.getElementById('vw-fullscreen');
  const songs = Array.from(document.querySelectorAll('.vw-song'));
  const docs = Array.from(document.querySelectorAll('.vw-doc'));

  let annotations = {};
  try { annotations = JSON.parse(document.getElementById('vw-annotations').textContent) || {}; } catch (e) { /* none */ }

  const state = { zoom: 1, fit: 'width' };
  try { if (localStorage.getItem('vw-fit') === 'page') state.fit = 'page'; } catch (e) { /* private mode */ }

  const pages = []; // { frame, pdfCanvas, ink, notes, pdfPage, base, docId, n, rendered, task }

  // ---------------------------------------------------------------- layout

  function barHeight() { return bar.offsetHeight; }

  function updateBarHeight() {
    document.documentElement.style.setProperty('--vw-bar', barHeight() + 'px');
  }

  function cssScale(base) {
    const width = Math.max(260, pagesEl.clientWidth - 24) / base.width;
    if (state.fit === 'page') {
      // Leave room for a song title above the first page, so a song's start fits on one screen too.
      const head = document.querySelector('.vw-song-head');
      const docHead = document.querySelector('.vw-doc-head');
      const headRoom = (head ? head.offsetHeight + 16 : 0) + (docHead ? docHead.offsetHeight + 16 : 0);
      const height = Math.max(200, window.innerHeight - barHeight() - headRoom - 24) / base.height;
      return Math.min(width, height) * state.zoom;
    }
    return width * state.zoom;
  }

  function size(p) {
    const scale = cssScale(p.base);
    p.w = p.base.width * scale;
    p.h = p.base.height * scale;
    p.frame.style.width = p.w + 'px';
    p.frame.style.height = p.h + 'px';
  }

  // ---------------------------------------------------------------- notes (read-only)

  function pageNotes(p) {
    const doc = annotations[p.docId];
    const page = doc && doc.pages && doc.pages[String(p.n)];
    return {
      strokes: page && Array.isArray(page.strokes) ? page.strokes : [],
      texts: page && Array.isArray(page.texts) ? page.texts : [],
    };
  }

  function drawInk(p) {
    const ctx = p.ink.getContext('2d');
    const W = p.ink.width;
    const H = p.ink.height;
    ctx.clearRect(0, 0, W, H);
    for (const s of pageNotes(p).strokes) {
      if (!Array.isArray(s.points) || !s.points.length) continue;
      ctx.save();
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.strokeStyle = s.color;
      ctx.globalAlpha = s.tool === 'marker' ? 0.35 : 1;
      ctx.lineWidth = s.width * W;
      ctx.beginPath();
      s.points.forEach(([x, y], i) => { if (i === 0) ctx.moveTo(x * W, y * H); else ctx.lineTo(x * W, y * H); });
      if (s.points.length === 1) ctx.lineTo(s.points[0][0] * W + 0.01, s.points[0][1] * H);
      ctx.stroke();
      ctx.restore();
    }
  }

  function buildNotes(p) {
    p.notes.replaceChildren();
    for (const t of pageNotes(p).texts) {
      const el = document.createElement('div');
      el.className = 'note';
      el.textContent = t.text;
      el.style.left = t.x * 100 + '%';
      el.style.top = t.y * 100 + '%';
      el.style.color = t.color;
      el.style.fontSize = Math.max(8, t.size * p.w) + 'px';
      p.notes.append(el);
    }
  }

  // ---------------------------------------------------------------- rendering (only pages near the screen)

  async function render(p) {
    if (p.rendered) return;
    p.rendered = true;
    const dpr = window.devicePixelRatio || 1;
    const viewport = p.pdfPage.getViewport({ scale: (p.w / p.base.width) * dpr });
    for (const c of [p.pdfCanvas, p.ink]) {
      c.width = Math.round(viewport.width);
      c.height = Math.round(viewport.height);
      c.style.width = p.w + 'px';
      c.style.height = p.h + 'px';
    }
    if (p.task) { try { p.task.cancel(); } catch (e) { /* ignore */ } }
    p.task = p.pdfPage.render({ canvasContext: p.pdfCanvas.getContext('2d'), viewport });
    try {
      await p.task.promise;
    } catch (e) {
      if (!e || e.name !== 'RenderingCancelledException') console.error(e);
      p.rendered = false;
      return;
    }
    drawInk(p);
    buildNotes(p);
  }

  function release(p) {
    // Frees memory of pages far away; a whole gig can have a lot of pages.
    if (!p.rendered) return;
    if (p.task) { try { p.task.cancel(); } catch (e) { /* ignore */ } }
    p.rendered = false;
    p.pdfCanvas.width = p.pdfCanvas.height = 0;
    p.ink.width = p.ink.height = 0;
    p.notes.replaceChildren();
  }

  const byFrame = new Map();
  const nearObserver = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      const p = byFrame.get(entry.target);
      if (entry.isIntersecting) render(p);
    }
  }, { rootMargin: '150% 0px' });
  const farObserver = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) release(byFrame.get(entry.target));
    }
  }, { rootMargin: '600% 0px' });

  function addPage(container, pdfPage, docId, n) {
    const frame = document.createElement('div');
    frame.className = 'page';
    const pdfCanvas = document.createElement('canvas');
    const ink = document.createElement('canvas');
    ink.className = 'ink';
    const notes = document.createElement('div');
    notes.className = 'text-layer';
    frame.append(pdfCanvas, ink, notes);
    container.append(frame);
    const base = pdfPage.getViewport({ scale: 1 });
    const p = { frame, pdfCanvas, ink, notes, pdfPage, base, docId, n, rendered: false, task: null };
    size(p);
    pages.push(p);
    byFrame.set(frame, p);
    nearObserver.observe(frame);
    farObserver.observe(frame);
  }

  async function loadAll() {
    pdfjsLib.GlobalWorkerOptions.workerSrc =
      'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
    // One shared PDF.js worker; download a few PDFs ahead, but build the pages strictly in running order.
    const worker = new pdfjsLib.PDFWorker();
    const loading = [];
    const AHEAD = 3;
    const start = (i) => {
      if (i < docs.length && !loading[i]) {
        loading[i] = pdfjsLib.getDocument({ url: docs[i].dataset.file, withCredentials: true, worker }).promise;
        loading[i].catch(() => {}); // handled below, in order
      }
    };
    for (let i = 0; i < docs.length; i++) {
      for (let k = i; k <= i + AHEAD; k++) start(k);
      const el = docs[i];
      const message = el.querySelector('.vw-loading');
      try {
        const pdf = await loading[i];
        const anchor = currentAnchor();
        for (let n = 1; n <= pdf.numPages; n++) addPage(el, await pdf.getPage(n), el.dataset.doc, n);
        message.remove();
        restoreAnchor(anchor);
      } catch (e) {
        console.error(e);
        message.textContent = 'This PDF could not be loaded.';
        message.classList.add('vw-error');
      }
    }
  }

  // ---------------------------------------------------------------- where are we?

  function stops() {
    // Each song starts at its title; further pages are their own stops.
    const result = [];
    for (const song of songs) {
      result.push(song);
      song.querySelectorAll('.page').forEach((frame, i) => { if (i > 0) result.push(frame); });
    }
    return result;
  }

  function top(el) { return el.getBoundingClientRect().top - barHeight(); }

  function currentSongIndex() {
    let index = 0;
    songs.forEach((song, i) => { if (top(song) <= 8) index = i; });
    return index;
  }

  function currentAnchor() {
    // The element at the top of the screen and how far into it we are, to keep the place when sizes change.
    const all = stops();
    let el = null;
    for (const s of all) { if (top(s) <= 8) el = s; }
    if (!el) return null;
    return { el, ratio: -top(el) / Math.max(1, el.getBoundingClientRect().height) };
  }

  function restoreAnchor(anchor) {
    if (!anchor || window.scrollY === 0) return;
    const rect = anchor.el.getBoundingClientRect();
    window.scrollBy(0, rect.top - barHeight() + anchor.ratio * rect.height);
  }

  function scrollTo(el) {
    window.scrollBy(0, top(el));
  }

  function updateNav() {
    if (!songs.length) return;
    const i = currentSongIndex();
    jump.value = songs[i].id;
    prevButton.disabled = i === 0 && top(songs[0]) >= -8;
    nextButton.disabled = i === songs.length - 1;
  }

  // ---------------------------------------------------------------- moving around

  function nextPage() {
    // Skip what is already right at the top, so every press really turns the page.
    const target = stops().find((s) => top(s) > 120);
    if (target) scrollTo(target);
    else window.scrollTo(0, document.body.scrollHeight);
  }

  function previousPage() {
    const before = stops().filter((s) => top(s) < -8);
    if (before.length) scrollTo(before[before.length - 1]);
    else window.scrollTo(0, 0);
  }

  function nextSong() {
    const i = currentSongIndex();
    if (i < songs.length - 1) scrollTo(songs[i + 1]);
  }

  function previousSong() {
    const i = currentSongIndex();
    // Like a CD player: first back to the start of this song, then to the one before.
    if (top(songs[i]) < -8) scrollTo(songs[i]);
    else if (i > 0) scrollTo(songs[i - 1]);
  }

  prevButton.addEventListener('click', previousSong);
  nextButton.addEventListener('click', nextSong);
  jump.addEventListener('change', () => {
    const el = document.getElementById(jump.value);
    if (el) scrollTo(el);
    jump.blur(); // so the page-turn keys work again right away
  });

  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.target.closest && e.target.closest('select, input, textarea')) return;
    switch (e.key) {
      case 'PageDown': case 'ArrowRight': case ' ':
        e.preventDefault(); if (e.shiftKey && e.key === ' ') previousPage(); else nextPage(); break;
      case 'PageUp': case 'ArrowLeft':
        e.preventDefault(); previousPage(); break;
      case 'n': case 'N': nextSong(); break;
      case 'p': case 'P': previousSong(); break;
      default:
    }
  });

  // Tap the right third of a page for the next page, the left third for the previous one.
  pagesEl.addEventListener('click', (e) => {
    const frame = e.target.closest('.page');
    if (!frame || window.getSelection().toString()) return;
    const r = frame.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width;
    if (x > 2 / 3) nextPage();
    else if (x < 1 / 3) previousPage();
  });

  let ticking = false;
  window.addEventListener('scroll', () => {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => { ticking = false; updateNav(); });
  }, { passive: true });

  // ---------------------------------------------------------------- zoom and fit

  function relayout() {
    const anchor = currentAnchor();
    updateBarHeight();
    for (const p of pages) {
      size(p);
      release(p);
    }
    restoreAnchor(anchor);
    // The observers only report changes, so render what is on screen now ourselves.
    const limit = window.innerHeight * 2.5;
    for (const p of pages) {
      const r = p.frame.getBoundingClientRect();
      if (r.bottom > -limit && r.top < limit) render(p);
    }
  }

  function setFit(fit) {
    state.fit = fit;
    fitButton.setAttribute('aria-pressed', String(fit === 'page'));
    try { localStorage.setItem('vw-fit', fit); } catch (e) { /* ignore */ }
  }

  fitButton.addEventListener('click', () => {
    setFit(state.fit === 'page' ? 'width' : 'page');
    state.zoom = 1;
    relayout();
  });
  document.getElementById('vw-zoom-in').addEventListener('click', () => {
    state.zoom = Math.min(2.5, Math.round((state.zoom + 0.15) * 100) / 100);
    relayout();
  });
  document.getElementById('vw-zoom-out').addEventListener('click', () => {
    state.zoom = Math.max(0.4, Math.round((state.zoom - 0.15) * 100) / 100);
    relayout();
  });

  let lastWidth = window.innerWidth;
  let lastHeight = window.innerHeight;
  let resizeTimer = null;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      // Mobile browsers change the height while scrolling (address bar); only react to real changes.
      const widthChanged = window.innerWidth !== lastWidth;
      const heightChanged = Math.abs(window.innerHeight - lastHeight) > 120;
      if (widthChanged || (state.fit === 'page' && heightChanged)) relayout();
      lastWidth = window.innerWidth;
      lastHeight = window.innerHeight;
    }, 250);
  });

  // ---------------------------------------------------------------- full screen and screen lock

  const root = document.documentElement;
  const requestFullscreen = root.requestFullscreen || root.webkitRequestFullscreen;
  const exitFullscreen = document.exitFullscreen || document.webkitExitFullscreen;
  const fullscreenElement = () => document.fullscreenElement || document.webkitFullscreenElement;
  if (requestFullscreen) {
    fullscreenButton.hidden = false;
    fullscreenButton.addEventListener('click', () => {
      if (fullscreenElement()) exitFullscreen.call(document);
      else requestFullscreen.call(root);
    });
    const onChange = () => {
      fullscreenButton.textContent = fullscreenElement() ? 'Exit full screen' : 'Full screen';
      setTimeout(relayout, 150);
    };
    document.addEventListener('fullscreenchange', onChange);
    document.addEventListener('webkitfullscreenchange', onChange);
  }

  // Keep the screen on while the sheet music is open (where the browser allows it).
  let wakeLock = null;
  async function keepAwake() {
    if (!('wakeLock' in navigator) || document.visibilityState !== 'visible') return;
    try {
      wakeLock = await navigator.wakeLock.request('screen');
      wakeLock.addEventListener('release', () => { wakeLock = null; });
    } catch (e) { wakeLock = null; }
  }
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && !wakeLock) keepAwake();
    if (document.visibilityState !== 'visible') wakeLock = null;
  });

  // ---------------------------------------------------------------- start

  setFit(state.fit);
  updateBarHeight();
  updateNav();
  keepAwake();
  if (docs.length) {
    if (typeof pdfjsLib === 'undefined') {
      docs.forEach((el) => { el.querySelector('.vw-loading').textContent = 'The PDF viewer could not be loaded. Check the internet connection.'; });
    } else {
      loadAll();
    }
  }
})();

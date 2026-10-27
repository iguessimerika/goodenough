// Sheet music editor: shows the PDF (PDF.js) and lets the band draw and write on it together.
// All coordinates are normalised to the page (0 to 1), so they fit at any zoom level.
(() => {
  'use strict';

  const root = document.getElementById('editor');
  const pagesEl = document.getElementById('pages');
  const messageEl = document.getElementById('ed-message');
  const statusEl = document.getElementById('ed-status');
  const saveButton = document.getElementById('ed-save');
  const fileUrl = root.dataset.file;
  const saveUrl = root.dataset.save;
  const csrf = root.dataset.csrf;
  let version = parseInt(root.dataset.version, 10) || 0;

  let data;
  try { data = JSON.parse(document.getElementById('annot-data').textContent); } catch (e) { data = null; }
  if (!data || typeof data !== 'object' || typeof data.pages !== 'object' || !data.pages) data = { pages: {} };

  const state = { tool: 'hand', color: '#d62828', zoom: 1, dirty: false, saving: false };
  const pages = {};
  const history = [];
  let pdf = null;

  const PEN_WIDTH = 0.0028;
  const MARKER_WIDTH = 0.02;
  const TEXT_SIZE = 0.022;

  function pageData(n) {
    const key = String(n);
    if (!data.pages[key]) data.pages[key] = { strokes: [], texts: [] };
    const p = data.pages[key];
    if (!Array.isArray(p.strokes)) p.strokes = [];
    if (!Array.isArray(p.texts)) p.texts = [];
    return p;
  }

  function setStatus(text, isError) {
    statusEl.textContent = text;
    statusEl.style.color = isError ? '#ff9aa8' : '';
  }

  function markDirty() {
    state.dirty = true;
    setStatus('Not saved');
  }

  // ---------------------------------------------------------------- tools

  function setTool(tool) {
    state.tool = tool;
    root.dataset.tool = tool;
    document.querySelectorAll('button[data-tool]').forEach((b) =>
      b.setAttribute('aria-pressed', String(b.dataset.tool === tool)));
  }
  document.querySelectorAll('button[data-tool]').forEach((b) =>
    b.addEventListener('click', () => setTool(b.dataset.tool)));

  document.querySelectorAll('button[data-color]').forEach((b) =>
    b.addEventListener('click', () => {
      state.color = b.dataset.color;
      document.querySelectorAll('button[data-color]').forEach((x) =>
        x.setAttribute('aria-pressed', String(x === b)));
    }));

  document.getElementById('ed-undo').addEventListener('click', undo);
  document.getElementById('ed-zoom-in').addEventListener('click', () => zoom(0.15));
  document.getElementById('ed-zoom-out').addEventListener('click', () => zoom(-0.15));
  saveButton.addEventListener('click', save);

  function zoom(step) {
    state.zoom = Math.min(2.5, Math.max(0.5, Math.round((state.zoom + step) * 100) / 100));
    renderAll();
  }

  // ---------------------------------------------------------------- pages

  function createPage(n) {
    const frame = document.createElement('div');
    frame.className = 'page';
    const pdfCanvas = document.createElement('canvas');
    const ink = document.createElement('canvas');
    ink.className = 'ink';
    const textLayer = document.createElement('div');
    textLayer.className = 'text-layer';
    frame.append(pdfCanvas, ink, textLayer);
    pagesEl.append(frame);
    pages[n] = { frame, pdfCanvas, ink, textLayer, w: 0, h: 0, dpr: 1, task: null };
    bindDrawing(n);
    bindText(n);
  }

  async function renderPage(n) {
    const p = pages[n];
    const page = await pdf.getPage(n);
    const base = page.getViewport({ scale: 1 });
    const available = Math.max(280, pagesEl.clientWidth - 24);
    const cssScale = (available / base.width) * state.zoom;
    const dpr = window.devicePixelRatio || 1;
    const viewport = page.getViewport({ scale: cssScale * dpr });
    p.dpr = dpr;
    p.w = viewport.width / dpr;
    p.h = viewport.height / dpr;

    for (const c of [p.pdfCanvas, p.ink]) {
      c.width = Math.round(viewport.width);
      c.height = Math.round(viewport.height);
      c.style.width = p.w + 'px';
      c.style.height = p.h + 'px';
    }
    p.frame.style.width = p.w + 'px';
    p.frame.style.height = p.h + 'px';

    if (p.task) { try { p.task.cancel(); } catch (e) { /* ignore */ } }
    p.task = page.render({ canvasContext: p.pdfCanvas.getContext('2d'), viewport });
    try {
      await p.task.promise;
    } catch (e) {
      if (!e || e.name !== 'RenderingCancelledException') throw e;
      return;
    }
    drawInk(n);
    buildNotes(n);
  }

  async function renderAll() {
    for (const n of Object.keys(pages)) await renderPage(Number(n));
  }

  // ---------------------------------------------------------------- drawing

  function paintStroke(ctx, stroke, p) {
    const W = p.ink.width;
    const H = p.ink.height;
    if (!stroke.points.length) return;
    ctx.save();
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.strokeStyle = stroke.color;
    ctx.globalAlpha = stroke.tool === 'marker' ? 0.35 : 1;
    ctx.lineWidth = stroke.width * W;
    ctx.beginPath();
    stroke.points.forEach(([x, y], i) => {
      if (i === 0) ctx.moveTo(x * W, y * H); else ctx.lineTo(x * W, y * H);
    });
    if (stroke.points.length === 1) {
      const [x, y] = stroke.points[0];
      ctx.lineTo(x * W + 0.01, y * H);
    }
    ctx.stroke();
    ctx.restore();
  }

  function drawInk(n) {
    const p = pages[n];
    const ctx = p.ink.getContext('2d');
    ctx.clearRect(0, 0, p.ink.width, p.ink.height);
    for (const stroke of pageData(n).strokes) paintStroke(ctx, stroke, p);
  }

  function pointFrom(e, canvas) {
    const r = canvas.getBoundingClientRect();
    return [(e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height];
  }

  function distanceToSegment(px, py, ax, ay, bx, by) {
    const dx = bx - ax;
    const dy = by - ay;
    const l2 = dx * dx + dy * dy;
    let t = l2 ? ((px - ax) * dx + (py - ay) * dy) / l2 : 0;
    t = Math.max(0, Math.min(1, t));
    return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
  }

  function hits(stroke, px, py, radius, p) {
    const pts = stroke.points.map(([x, y]) => [x * p.w, y * p.h]);
    const r = radius + (stroke.width * p.w) / 2;
    if (pts.length === 1) return Math.hypot(pts[0][0] - px, pts[0][1] - py) <= r;
    for (let i = 1; i < pts.length; i++) {
      if (distanceToSegment(px, py, pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1]) <= r) return true;
    }
    return false;
  }

  function dropFromHistory(obj) {
    const i = history.findIndex((h) => h.obj === obj);
    if (i >= 0) history.splice(i, 1);
  }

  function erase(n, pt) {
    const p = pages[n];
    const strokes = pageData(n).strokes;
    const px = pt[0] * p.w;
    const py = pt[1] * p.h;
    for (let i = strokes.length - 1; i >= 0; i--) {
      if (hits(strokes[i], px, py, 10, p)) {
        const [removed] = strokes.splice(i, 1);
        dropFromHistory(removed);
        drawInk(n);
        markDirty();
        return;
      }
    }
  }

  function bindDrawing(n) {
    const canvas = pages[n].ink;
    let current = null;
    let erasing = false;

    canvas.addEventListener('pointerdown', (e) => {
      const tool = state.tool;
      if (tool !== 'pen' && tool !== 'marker' && tool !== 'eraser') return;
      if (e.pointerType === 'mouse' && e.button !== 0) return;
      e.preventDefault();
      canvas.setPointerCapture(e.pointerId);
      const pt = pointFrom(e, canvas);
      if (tool === 'eraser') { erasing = true; erase(n, pt); return; }
      current = {
        tool,
        color: state.color,
        width: tool === 'marker' ? MARKER_WIDTH : PEN_WIDTH,
        points: [pt],
      };
      pageData(n).strokes.push(current);
      drawInk(n);
    });

    canvas.addEventListener('pointermove', (e) => {
      if (state.tool === 'eraser') { if (erasing) erase(n, pointFrom(e, canvas)); return; }
      if (!current) return;
      current.points.push(pointFrom(e, canvas));
      drawInk(n);
    });

    const finish = () => {
      if (current) {
        history.push({ n, kind: 'stroke', obj: current });
        markDirty();
        current = null;
      }
      erasing = false;
    };
    canvas.addEventListener('pointerup', finish);
    canvas.addEventListener('pointercancel', finish);
  }

  // ---------------------------------------------------------------- text notes

  function removeNote(n, t, el) {
    const list = pageData(n).texts;
    const i = list.indexOf(t);
    if (i >= 0) list.splice(i, 1);
    dropFromHistory(t);
    el.remove();
  }

  function createNote(n, t) {
    const el = document.createElement('div');
    el.className = 'note';
    el.contentEditable = 'true';
    el.spellcheck = false;
    el.textContent = t.text;
    el.style.left = t.x * 100 + '%';
    el.style.top = t.y * 100 + '%';
    el.style.color = t.color;
    el.style.fontSize = Math.max(8, t.size * pages[n].w) + 'px';
    el.addEventListener('input', () => { t.text = el.innerText.slice(0, 1000); markDirty(); });
    el.addEventListener('blur', () => {
      if (!el.innerText.trim()) { removeNote(n, t, el); markDirty(); }
    });
    el.addEventListener('click', () => {
      if (state.tool === 'eraser') { removeNote(n, t, el); markDirty(); }
    });
    return el;
  }

  function buildNotes(n) {
    const p = pages[n];
    p.textLayer.replaceChildren();
    for (const t of pageData(n).texts) p.textLayer.append(createNote(n, t));
  }

  function bindText(n) {
    const layer = pages[n].textLayer;
    layer.addEventListener('click', (e) => {
      if (state.tool !== 'text' || e.target !== layer) return;
      const r = layer.getBoundingClientRect();
      const t = {
        x: (e.clientX - r.left) / r.width,
        y: (e.clientY - r.top) / r.height,
        text: '',
        color: state.color,
        size: TEXT_SIZE,
      };
      pageData(n).texts.push(t);
      history.push({ n, kind: 'text', obj: t });
      const el = createNote(n, t);
      layer.append(el);
      el.focus();
    });
  }

  function undo() {
    const h = history.pop();
    if (!h) return;
    const pd = pageData(h.n);
    if (h.kind === 'stroke') {
      const i = pd.strokes.indexOf(h.obj);
      if (i >= 0) pd.strokes.splice(i, 1);
      drawInk(h.n);
    } else {
      const i = pd.texts.indexOf(h.obj);
      if (i >= 0) pd.texts.splice(i, 1);
      buildNotes(h.n);
    }
    markDirty();
  }

  // ---------------------------------------------------------------- saving

  async function save() {
    if (state.saving) return;
    state.saving = true;
    saveButton.disabled = true;
    setStatus('Saving …');
    try {
      const response = await fetch(saveUrl, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: JSON.stringify({ version, annotations: data }),
      });
      if (response.status === 409) {
        setStatus('Someone else saved in the meantime. Reload the page; your changes are not saved yet.', true);
        return;
      }
      if (!response.ok) {
        const failure = await response.json().catch(() => ({}));
        setStatus('Saving failed: ' + (failure.error || response.status), true);
        return;
      }
      const result = await response.json();
      version = result.version;
      state.dirty = false;
      setStatus('Saved');
    } catch (e) {
      setStatus('Saving failed. Check your connection.', true);
    } finally {
      state.saving = false;
      saveButton.disabled = false;
    }
  }

  window.addEventListener('beforeunload', (e) => {
    if (state.dirty) { e.preventDefault(); e.returnValue = ''; }
  });

  document.addEventListener('keydown', (e) => {
    const mod = e.ctrlKey || e.metaKey;
    if (!mod) return;
    if (e.key === 's' || e.key === 'S') { e.preventDefault(); save(); return; }
    const typing = document.activeElement && document.activeElement.isContentEditable;
    if ((e.key === 'z' || e.key === 'Z') && !typing) { e.preventDefault(); undo(); }
  });

  let lastWidth = pagesEl.clientWidth;
  let resizeTimer = null;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      if (pdf && pagesEl.clientWidth !== lastWidth) {
        lastWidth = pagesEl.clientWidth;
        renderAll();
      }
    }, 250);
  });

  // ---------------------------------------------------------------- start

  async function start() {
    try {
      pdfjsLib.GlobalWorkerOptions.workerSrc =
        'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
      pdf = await pdfjsLib.getDocument({ url: fileUrl, withCredentials: true }).promise;
    } catch (e) {
      console.error(e);
      messageEl.textContent = 'The sheet music could not be loaded. Reload the page or download the PDF instead.';
      return;
    }
    messageEl.hidden = true;
    for (let n = 1; n <= pdf.numPages; n++) createPage(n);
    await renderAll();
  }

  start();
})();

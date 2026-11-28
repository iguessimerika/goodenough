"""Draws the band's notes (pen, marker, text) into the pages of a PDF, for downloads.

The notes are stored with coordinates from 0 to 1 relative to the page as the browser shows it
(PDF.js: crop box, page rotation applied, origin top left). Here they become real PDF drawing
commands on top of each page, so they show up in every PDF app (forScore, Acrobat, Preview …)
and print with the sheet. Only pypdf is needed: lines are plain PDF paths, text uses the built-in
Helvetica Bold font, so nothing has to be embedded.
"""

import json
from io import BytesIO

from pypdf import PageObject, PdfReader, PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    RectangleObject,
)

MARKER_ALPHA = 0.35   # same as in editor.js
LINE_HEIGHT = 1.25    # .note { line-height } in style.css
FONT = "/GEnF1"
ALPHA = "/GEnGS1"


def parse(raw):
    """Annotation JSON from the database -> {"pages": {...}}; anything broken counts as no notes."""
    try:
        data = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
    except ValueError:
        return {"pages": {}}
    if not isinstance(data, dict) or not isinstance(data.get("pages"), dict):
        return {"pages": {}}
    return data


def has_notes(annotations):
    return any(
        isinstance(p, dict) and (p.get("strokes") or p.get("texts"))
        for p in parse(annotations)["pages"].values()
    )


# ---------------------------------------------------------------- geometry

def _view_box(page):
    """The visible area like PDF.js uses it: crop box clipped to the media box."""
    media, crop = page.mediabox, page.cropbox
    x0 = max(min(crop.left, crop.right), min(media.left, media.right))
    y0 = max(min(crop.bottom, crop.top), min(media.bottom, media.top))
    x1 = min(max(crop.left, crop.right), max(media.left, media.right))
    y1 = min(max(crop.bottom, crop.top), max(media.bottom, media.top))
    if x1 <= x0 or y1 <= y0:  # odd boxes: fall back to the media box
        x0, y0, x1, y1 = (float(v) for v in (media.left, media.bottom, media.right, media.top))
    return float(x0), float(y0), float(x1), float(y1)


def _view_transform(page):
    """(width, height, matrix) of the page as shown on screen.

    The matrix maps screen-like coordinates (points, origin top left, y downwards) to the
    PDF's own coordinates, for the four possible page rotations.
    """
    x0, y0, x1, y1 = _view_box(page)
    w, h = x1 - x0, y1 - y0
    rotation = (page.get("/Rotate", 0) or 0) % 360
    if rotation == 90:
        return h, w, (0, 1, 1, 0, x0, y0)
    if rotation == 180:
        return w, h, (-1, 0, 0, 1, x1, y0)
    if rotation == 270:
        return h, w, (0, -1, -1, 0, x1, y1)
    return w, h, (1, 0, 0, -1, x0, y1)


# ---------------------------------------------------------------- content stream

def _n(value):
    return f"{value:.3f}".rstrip("0").rstrip(".") or "0"


def _rgb(color):
    try:
        r, g, b = (int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    except (TypeError, ValueError, IndexError):
        r = g = b = 0
    return f"{_n(r)} {_n(g)} {_n(b)}"


def _pdf_string(text):
    raw = text.encode("cp1252", errors="replace")  # WinAnsi: umlauts and ß work, emoji become ?
    raw = raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
    return b"(" + raw.replace(b"\r", b"").replace(b"\t", b" ") + b")"


def _number(value, default=0.0):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def _page_stream(page_notes, width, height, matrix):
    out = [b"q", " ".join(_n(v) for v in matrix).encode() + b" cm"]

    for s in page_notes.get("strokes") or []:
        points = [p for p in (s.get("points") or []) if isinstance(p, (list, tuple)) and len(p) == 2]
        if not points:
            continue
        marker = s.get("tool") == "marker"
        out.append(b"q")
        if marker:
            out.append(ALPHA.encode() + b" gs")
        out.append(f"{_rgb(s.get('color'))} RG 1 J 1 j {_n(_number(s.get('width'), 0.003) * width)} w".encode())
        coords = [(_number(x) * width, _number(y) * height) for x, y in points]
        path = [f"{_n(coords[0][0])} {_n(coords[0][1])} m"]
        if len(coords) == 1:  # a single tap: a dot
            coords.append((coords[0][0] + 0.01, coords[0][1]))
        path += [f"{_n(x)} {_n(y)} l" for x, y in coords[1:]]
        out.append(" ".join(path).encode() + b" S")
        out.append(b"Q")

    for t in page_notes.get("texts") or []:
        text = t.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        size = max(_number(t.get("size"), 0.022) * width, 4)
        x = _number(t.get("x")) * width + size * 0.12  # small padding like the note box on screen
        y = _number(t.get("y")) * height
        lead = size * LINE_HEIGHT
        out.append(f"BT {FONT} {_n(size)} Tf {_rgb(t.get('color'))} rg {_n(lead)} TL".encode())
        # y points down here, so the text matrix flips the letters back upright.
        first_baseline = y + (lead - size) / 2 + size * 0.8
        out.append(f"1 0 0 -1 {_n(x)} {_n(first_baseline)} Tm".encode())
        for i, line in enumerate(text.split("\n")):
            if i:
                out.append(b"T*")
            out.append(_pdf_string(line) + b" Tj")
        out.append(b"ET")

    out.append(b"Q")
    return b"\n".join(out)


def _overlay_for(page, page_notes):
    width, height, matrix = _view_transform(page)
    overlay = PageObject.create_blank_page(width=float(page.mediabox.width), height=float(page.mediabox.height))
    overlay.mediabox = RectangleObject(page.mediabox)
    stream = DecodedStreamObject()
    stream.set_data(_page_stream(page_notes, width, height, matrix))
    overlay[NameObject("/Contents")] = stream
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica-Bold"),
        NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
    })
    alpha = DictionaryObject({
        NameObject("/Type"): NameObject("/ExtGState"),
        NameObject("/ca"): FloatObject(MARKER_ALPHA),
        NameObject("/CA"): FloatObject(MARKER_ALPHA),
    })
    overlay[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject(FONT): font}),
        NameObject("/ExtGState"): DictionaryObject({NameObject(ALPHA): alpha}),
    })
    return overlay


def add_notes_to_page(page, page_notes):
    """Draws one page's notes onto a page that already belongs to a PdfWriter."""
    if not isinstance(page_notes, dict) or not (page_notes.get("strokes") or page_notes.get("texts")):
        return
    page.merge_page(_overlay_for(page, page_notes), over=True)


def add_notes_to_pages(pages, annotations):
    """pages: the writer pages of one PDF, in order (page 1 first)."""
    notes = parse(annotations)["pages"]
    for number, page in enumerate(pages, start=1):
        add_notes_to_page(page, notes.get(str(number)))


def with_notes(pdf_bytes, annotations):
    """The PDF with the notes drawn in, as bytes. Without notes the original comes back unchanged."""
    if not has_notes(annotations):
        return pdf_bytes
    reader = PdfReader(BytesIO(pdf_bytes))
    if reader.is_encrypted:
        reader.decrypt("")
    writer = PdfWriter(clone_from=reader)
    add_notes_to_pages(writer.pages, annotations)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()

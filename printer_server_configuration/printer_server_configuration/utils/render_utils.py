"""
ESC/POS and HTML rendering for Print Template.

Converts a Jinja template (with [TAG] syntax) to raw ESC/POS bytes
or to HTML for PDF preview.

Supported tags
--------------
  Alignment  : [C] [CENTER]  [R] [RIGHT]  [L] [LEFT]
               Two-column   : [L]left text[R]right text  (pads spaces between)
  Style      : [B] [BOLD]  [U]  [UU]  [INV] [FLIP]  [FB] [FONTB]
  Size       : [BIG]  [W2]  [H2]  [W:n]  [H:n]  (n = 1-8)
  Lines      : [LINE]  [SLINE]  [DLINE]  [RULE:char]
  Control    : [CUT]  [PCUT]  [FEED]  [FEED:n]  [DRAWER]
  Barcodes   : [BARCODE:value:TYPE:height]  [QR:value:size]
  Raw        : [HEX:1B40...]
"""

import re
import types

import frappe

CHARS_PER_LINE = {"80mm": 46, "58mm": 30}

# Print area width in dots at 203 DPI (8 dots/mm)
_PRINT_WIDTH_DOTS = {"80mm": 576, "58mm": 384}

_RESET = dict(
	align="left",
	bold=False,
	underline=0,
	double_width=False,
	double_height=False,
	normal_textsize=True,
	font="a",
	invert=False,
	flip=False,
)


# ---------------------------------------------------------------------------
# Context builder — wraps frappe doc in SimpleNamespace so doc.items
# returns the child-table list and NOT Python's dict.items() method.
# ---------------------------------------------------------------------------


def build_context(template_doc, document_name):
	"""Return Jinja context dict with doc wrapped in SimpleNamespace."""
	context = {"doc": types.SimpleNamespace(), "document_name": document_name or ""}
	if template_doc.document_type and document_name:
		d = frappe.get_doc(template_doc.document_type, document_name).as_dict()
		price_list = getattr(template_doc, "price_list", None)
		if price_list:
			_inject_price_list_rates(d, template_doc.document_type, price_list)
		context["doc"] = _ns(d)
	return context


def build_report_context(report_name, filters=None):
	"""Run a Frappe Report and return Jinja context dict.

	Context keys available in templates:
	  report.name     — report name
	  report.columns  — list of column dicts (label, fieldname, fieldtype, …)
	  report.result   — list of row dicts/lists as returned by the report
	  report.filters  — filters used when running the report
	"""
	from frappe.desk.query_report import run as _run_report

	filters = filters or {}
	try:
		data = _run_report(report_name, filters=filters)
	except Exception as exc:
		frappe.log_error(frappe.get_traceback(), f"PrintTemplate: run report {report_name}")
		data = {"result": [], "columns": [], "message": str(exc)}

	columns = data.get("columns") or []
	result = data.get("result") or []

	# Normalise rows: if rows are lists, zip them with column fieldnames so
	# templates can access values by name (row.qty) in addition to index.
	fieldnames = []
	for col in columns:
		if isinstance(col, dict):
			fieldnames.append(col.get("fieldname") or col.get("label", ""))
		else:
			fieldnames.append(str(col))

	normalised = []
	for row in result:
		if isinstance(row, (list, tuple)):
			ns = types.SimpleNamespace(**dict(zip(fieldnames, row)))
			ns._row = list(row)
			normalised.append(ns)
		elif isinstance(row, dict):
			normalised.append(_ns(row))
		else:
			normalised.append(row)

	report_ns = types.SimpleNamespace(
		name=report_name,
		columns=columns,
		result=normalised,
		raw_result=result,
		filters=filters,
	)

	return {
		"doc": types.SimpleNamespace(),
		"report": report_ns,
	}


def _get_item_price(item_code, price_list):
	return frappe.db.get_value(
		"Item Price",
		{"item_code": item_code, "price_list": price_list},
		"price_list_rate",
	) or 0


def _inject_price_list_rates(d, document_type, price_list):
	"""Inject price_list_rate into doc dict from Item Price."""
	if document_type == "Item":
		item_code = d.get("name") or d.get("item_code")
		if item_code:
			d["price_list_rate"] = _get_item_price(item_code, price_list)
		return

	items = d.get("items")
	if items and isinstance(items, list):
		for row in items:
			item_code = row.get("item_code")
			if item_code:
				row["price_list_rate"] = _get_item_price(item_code, price_list)


def _ns(d):
	"""Wrap a dict/frappe._dict in SimpleNamespace recursively for top level only."""
	return types.SimpleNamespace(**{k: v for k, v in d.items()})


# ---------------------------------------------------------------------------
# Shared style helpers
# ---------------------------------------------------------------------------


def _strip_alignment_tags(line):
	"""Remove all alignment tags ([L], [R], [C] and closing variants) from line."""
	return re.sub(r"\[/?(?:L(?:EFT)?|R(?:IGHT)?|C(?:ENTER)?)\]", "", line, flags=re.I)


def _parse_escpos_style(line):
	"""
	Strip all style tags from *line* and return (escpos_kw_dict, clean_line).
	Alignment tags must already be removed before calling this.
	"""
	underline = 0
	if "[UU]" in line:
		underline = 2
	elif "[U]" in line:
		underline = 1
	line = line.replace("[UU]", "").replace("[/UU]", "")
	line = line.replace("[U]", "").replace("[/U]", "")

	invert = bool(re.search(r"\[INV(?:ERT)?\]", line, re.I))
	line = re.sub(r"\[/?INV(?:ERT)?\]", "", line, flags=re.I)

	flip = "[FLIP]" in line
	line = line.replace("[FLIP]", "").replace("[/FLIP]", "")

	font = "b" if re.search(r"\[F(?:ONT)?B\]", line, re.I) else "a"
	line = re.sub(r"\[/?F(?:ONT)?B\]", "", line, flags=re.I)

	bold = dw = dh = False
	w = h = 1

	if "[BIG]" in line:
		bold = dw = dh = True
		w = h = 2
	line = line.replace("[BIG]", "").replace("[/BIG]", "")

	if m := re.search(r"\[W:([1-8])\]", line):
		w = int(m.group(1))
		dw = w >= 2
		line = re.sub(r"\[/?W:[1-8]\]", "", line)
	if m := re.search(r"\[H:([1-8])\]", line):
		h = int(m.group(1))
		dh = h >= 2
		line = re.sub(r"\[/?H:[1-8]\]", "", line)

	if "[W2]" in line:
		dw = True
		w = max(w, 2)
	line = line.replace("[W2]", "").replace("[/W2]", "")
	if "[H2]" in line:
		dh = True
		h = max(h, 2)
	line = line.replace("[H2]", "").replace("[/H2]", "")

	if re.search(r"\[B(?:OLD)?\]", line, re.I):
		bold = True
		line = re.sub(r"\[/?B(?:OLD)?\]", "", line, flags=re.I)

	kw = dict(align="left", bold=bold, underline=underline, double_width=dw,
		double_height=dh, font=font, invert=invert, flip=flip)
	if w > 2 or h > 2:
		kw.update(custom_size=True, width=w, height=h)

	return kw, line


def _parse_html_style(line):
	"""
	Strip all style tags from *line* and return (css_style_str, clean_line).
	Alignment tags must already be removed before calling this.
	"""
	import html as hl

	td = ""
	if "[UU]" in line:
		td = "text-decoration:underline double;"
	elif "[U]" in line:
		td = "text-decoration:underline;"
	line = line.replace("[UU]", "").replace("[/UU]", "")
	line = line.replace("[U]", "").replace("[/U]", "")

	invert = bool(re.search(r"\[INV(?:ERT)?\]", line, re.I))
	line = re.sub(r"\[/?INV(?:ERT)?\]", "", line, flags=re.I)

	flip = "[FLIP]" in line
	line = line.replace("[FLIP]", "").replace("[/FLIP]", "")

	font_s = ""
	if re.search(r"\[F(?:ONT)?B\]", line, re.I):
		font_s = "font-size:0.85em;"
	line = re.sub(r"\[/?F(?:ONT)?B\]", "", line, flags=re.I)

	bold_s = size_s = ""
	if "[BIG]" in line:
		bold_s = "font-weight:bold;"
		size_s = "font-size:1.5em;"
	line = line.replace("[BIG]", "").replace("[/BIG]", "")

	if m := re.search(r"\[W:([1-8])\]", line):
		size_s = f"font-size:{0.85 * int(m.group(1))}em;"
		line = re.sub(r"\[/?W:[1-8]\]", "", line)
	if m := re.search(r"\[H:([1-8])\]", line):
		size_s += f"line-height:{1.3 * int(m.group(1))}em;"
		line = re.sub(r"\[/?H:[1-8]\]", "", line)
	if "[W2]" in line:
		size_s = size_s or "font-size:1.4em;"
	line = line.replace("[W2]", "").replace("[/W2]", "")
	line = line.replace("[H2]", "").replace("[/H2]", "")

	if re.search(r"\[B(?:OLD)?\]", line, re.I):
		bold_s = "font-weight:bold;"
		line = re.sub(r"\[/?B(?:OLD)?\]", "", line, flags=re.I)

	extra = ""
	if invert:
		extra += "background:#000;color:#fff;"
	if flip:
		extra += "transform:rotate(180deg);display:inline-block;width:100%;"

	style = bold_s + size_s + td + font_s + extra
	return style, hl.escape(line)


# ---------------------------------------------------------------------------
# ESC/POS renderer
# ---------------------------------------------------------------------------


def render_to_escpos(template_doc, context):
	"""Render template to raw ESC/POS bytes using the Dummy printer."""
	try:
		from escpos.printer import Dummy
	except ImportError:
		frappe.throw("python-escpos is not installed. Run: bench pip install python-escpos")

	paper_width = getattr(template_doc, "paper_width", "80mm")
	chars = CHARS_PER_LINE.get(paper_width, 46)
	rendered = frappe.render_template(template_doc.template_content or "", context)

	p = Dummy()
	if getattr(template_doc, "open_cash_drawer", False):
		p.cashdraw(2)

	# Reset left margin to 0 (GS L 0 0) and set full print area width (GS W nL nH)
	width_dots = _PRINT_WIDTH_DOTS.get(paper_width, 576)
	p._raw(b"\x1d\x4c\x00\x00")
	p._raw(bytes([0x1D, 0x57, width_dots & 0xFF, width_dots >> 8]))

	_process_escpos(p, rendered, chars)

	if getattr(template_doc, "auto_cut", True):
		p.cut()

	return p.output


def _raster_line(p, width_dots=576, height_dots=1):
	"""Print a solid black horizontal line using GS v 0 (raster bit image)."""
	bytes_per_row = (width_dots + 7) // 8
	data = b"\xff" * bytes_per_row * height_dots
	# GS v 0  m  xL xH  yL yH  <data>
	p._raw(bytes([0x1D, 0x76, 0x30, 0x00,
		bytes_per_row & 0xFF, bytes_per_row >> 8,
		height_dots & 0xFF, height_dots >> 8]) + data)
	p.text("\n")


def _process_escpos(p, content, chars):
	for line in content.split("\n"):
		raw = line.rstrip()
		s = raw.strip()

		if not s:
			p.text("\n")
		elif s == "[CUT]":
			p.cut(feed=False)
		elif s == "[PCUT]":
			try:
				p.cut(mode="PART", feed=False)
			except Exception:
				p.cut(feed=False)
		elif s == "[DRAWER]":
			p.cashdraw(2)
		elif s == "[LINE]":
			p.set(**_RESET)
			_raster_line(p, width_dots=576)
		elif s == "[SLINE]":
			p.set(**_RESET)
			p.text("\u2500" * chars + "\n")
		elif s == "[DLINE]":
			p.set(**_RESET)
			p.text("=" * chars + "\n")
		elif m := re.fullmatch(r"\[RULE:(.)\]", s):
			p.set(**_RESET)
			p.text(m.group(1) * chars + "\n")
		elif m := re.fullmatch(r"\[FEED(?::(\d+))?\]", s):
			for _ in range(int(m.group(1) or 1)):
				p.text("\n")
		elif m := re.fullmatch(r"\[BARCODE:([^:\]]+)(?::([^:\]]+))?(?::(\d+))?\]", s):
			_barcode(p, m.group(1), m.group(2) or "CODE39", int(m.group(3) or 64))
		elif m := re.fullmatch(r"\[QR:(?:\x22([^\x22]*)\x22|([^\]:]+))(?::(\d+))?\]", s):
			val = m.group(1) if m.group(1) is not None else m.group(2)
			_qr(p, val, int(m.group(3) or 6))
		elif m := re.fullmatch(r"\[HEX:([0-9A-Fa-f]+)\]", s):
			h = m.group(1)
			if len(h) % 2 == 0:
				p._raw(bytes.fromhex(h))
		else:
			_print_styled_line(p, raw, chars)


def _barcode(p, value, bc_type, height):
	try:
		p.set(align="center")
		p.barcode(value, bc_type.upper(), height=height, function_type="B")
	except Exception:
		p.text(value + "\n")
	finally:
		p.set(**_RESET)


def _qr(p, value, size):
	try:
		p.set(align="center")
		p.qr(value, size=size)
	except Exception:
		p.text(value + "\n")
	finally:
		p.set(**_RESET)


def _print_styled_line(p, line, chars):
	"""Parse inline [TAGS], build p.set() kwargs, and print the line."""
	has_left = bool(re.search(r"\[L(?:EFT)?\]", line, re.I))
	has_right = bool(re.search(r"\[R(?:IGHT)?\]", line, re.I))

	# Two-column layout: [L]left text[R]right text — pad spaces between
	if has_left and has_right:
		parts = re.split(r"\[R(?:IGHT)?\]", line, 1, re.I)
		left_raw = _strip_alignment_tags(parts[0])
		right_raw = _strip_alignment_tags(parts[1] if len(parts) > 1 else "")
		kw, left_text = _parse_escpos_style(left_raw)
		_, right_text = _parse_escpos_style(right_raw)
		pad = max(0, chars - len(left_text) - len(right_text))
		kw["align"] = "left"
		p.set(**kw)
		p.text(left_text + " " * pad + right_text + "\n")
		p.set(**_RESET)
		return

	# Single alignment
	align = "left"
	if re.search(r"\[C(?:ENTER)?\]", line, re.I):
		align = "center"
		line = re.sub(r"\[/?C(?:ENTER)?\]", "", line, flags=re.I)
	elif has_right:
		align = "right"
		line = re.sub(r"\[/?R(?:IGHT)?\]", "", line, flags=re.I)
	elif has_left:
		line = re.sub(r"\[/?L(?:EFT)?\]", "", line, flags=re.I)

	kw, line = _parse_escpos_style(line)
	kw["align"] = align
	p.set(**kw)
	p.text(line + "\n")
	p.set(**_RESET)


# ---------------------------------------------------------------------------
# HTML renderer (for PDF preview of Thermal templates)
# ---------------------------------------------------------------------------


def render_to_html(rendered, paper_width="80mm"):
	"""Convert rendered template text (tags intact) to HTML receipt for PDF."""
	import html as hl

	chars = CHARS_PER_LINE.get(paper_width, 46)
	width_px = "302px" if paper_width == "80mm" else "220px"
	lines = []

	for line in rendered.split("\n"):
		raw = line.rstrip()
		s = raw.strip()

		if not s:
			lines.append('<div style="line-height:0.5em">&nbsp;</div>')
		elif s in ("[CUT]", "[PCUT]"):
			lines.append('<hr style="border:none;border-top:1px dashed #000;margin:3px 0">')
		elif s == "[DRAWER]":
			pass
		elif s == "[LINE]":
			lines.append('<hr style="border:none;border-top:1px dashed #000;margin:2px 0">')
		elif s == "[SLINE]":
			lines.append('<hr style="border:none;border-top:1px solid #000;margin:2px 0">')
		elif s == "[DLINE]":
			lines.append('<hr style="border:none;border-top:2px solid #000;margin:2px 0">')
		elif m := re.fullmatch(r"\[RULE:(.)\]", s):
			lines.append(f"<div>{hl.escape(m.group(1) * chars)}</div>")
		elif m := re.fullmatch(r"\[FEED(?::(\d+))?\]", s):
			for _ in range(int(m.group(1) or 1)):
				lines.append('<div style="line-height:0.5em">&nbsp;</div>')
		elif m := re.fullmatch(r"\[BARCODE:([^:\]]+)(?::([^:\]]+))?(?::(\d+))?\]", s):
			bc_type = (m.group(2) or "CODE39").upper()
			lines.append(
				f'<div style="text-align:center;font-size:0.8em;color:#555">'
				f"&#9646; Barcode: {hl.escape(m.group(1))} ({bc_type}) &#9646;</div>"
			)
		elif m := re.fullmatch(r"\[QR:(?:\x22([^\x22]*)\x22|([^\]:]+))(?::(\d+))?\]", s):
			val = m.group(1) if m.group(1) is not None else m.group(2)
			lines.append(
				f'<div style="text-align:center;font-size:0.8em;color:#555">'
				f"&#9646; QR: {hl.escape(val)} &#9646;</div>"
			)
		elif m := re.fullmatch(r"\[HEX:([0-9A-Fa-f]+)\]", s):
			lines.append(f'<div style="font-size:0.75em;color:#bbb">[HEX:{m.group(1)}]</div>')
		else:
			lines.append(_line_to_html(raw))

	body = "\n".join(lines)
	return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  body {{
    font-family: 'Courier New', Courier, monospace;
    font-size: 12px;
    width: {width_px};
    margin: 0 auto;
    padding: 8px 13px;
    line-height: 1.5;
  }}
  div {{ margin: 0; padding: 0; white-space: pre-wrap; word-break: break-all; }}
</style></head>
<body>{body}</body>
</html>"""


def _line_to_html(line):
	has_left = bool(re.search(r"\[L(?:EFT)?\]", line, re.I))
	has_right = bool(re.search(r"\[R(?:IGHT)?\]", line, re.I))

	# Two-column layout: [L]left text[R]right text
	if has_left and has_right:
		parts = re.split(r"\[R(?:IGHT)?\]", line, 1, re.I)
		left_raw = _strip_alignment_tags(parts[0])
		right_raw = _strip_alignment_tags(parts[1] if len(parts) > 1 else "")
		shared_style, left_text = _parse_html_style(left_raw)
		_, right_text = _parse_html_style(right_raw)
		return (
			f'<div style="display:flex;justify-content:space-between;{shared_style}">'
			f"<span>{left_text}</span><span>{right_text}</span></div>"
		)

	# Single alignment
	align = "left"
	if re.search(r"\[C(?:ENTER)?\]", line, re.I):
		align = "center"
		line = re.sub(r"\[/?C(?:ENTER)?\]", "", line, flags=re.I)
	elif has_right:
		align = "right"
		line = re.sub(r"\[/?R(?:IGHT)?\]", "", line, flags=re.I)
	elif has_left:
		line = re.sub(r"\[/?L(?:EFT)?\]", "", line, flags=re.I)

	style, escaped = _parse_html_style(line)
	return f'<div style="text-align:{align};{style}">{escaped}</div>'


def get_qr_code(data, scale=5):
	"""Generate a base64 encoded QR Code PNG image.

	Can be used directly inside HTML print templates:
	<img src="data:image/png;base64,{{ get_qr_code('text') }}" />
	"""
	import base64
	import io
	import qrcode

	if not data:
		return ""

	qr = qrcode.QRCode(version=1, box_size=scale, border=1)
	qr.add_data(data)
	qr.make(fit=True)
	img = qr.make_image(fill_color="black", back_color="white")

	buffered = io.BytesIO()
	img.save(buffered, format="PNG")
	return base64.b64encode(buffered.getvalue()).decode()


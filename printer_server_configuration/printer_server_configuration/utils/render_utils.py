"""
ESC/POS and HTML rendering for Print Template.

Converts a Jinja template (with [TAG] syntax) to raw ESC/POS bytes
or to HTML for PDF preview.

Supported tags
--------------
  Alignment  : [C] [CENTER]  [R] [RIGHT]  [L] [LEFT]
  Style      : [B] [BOLD]  [U]  [UU]  [INV] [FLIP]  [FB] [FONTB]
  Size       : [BIG]  [W2]  [H2]  [W:n]  [H:n]  (n = 1-8)
  Lines      : [LINE]  [DLINE]  [RULE:char]
  Control    : [CUT]  [PCUT]  [FEED]  [FEED:n]  [DRAWER]
  Barcodes   : [BARCODE:value:TYPE:height]  [QR:value:size]
  Raw        : [HEX:1B40...]
"""

import re
import types

import frappe

CHARS_PER_LINE = {"80mm": 48, "58mm": 32}

_RESET = dict(
	align="left",
	bold=False,
	underline=0,
	double_width=False,
	double_height=False,
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
	context = {"doc": types.SimpleNamespace()}
	if template_doc.document_type and document_name:
		d = frappe.get_doc(template_doc.document_type, document_name).as_dict()
		context["doc"] = _ns(d)
	return context


def _ns(d):
	"""Wrap a dict/frappe._dict in SimpleNamespace recursively for top level only."""
	return types.SimpleNamespace(**{k: v for k, v in d.items()})


# ---------------------------------------------------------------------------
# ESC/POS renderer
# ---------------------------------------------------------------------------


def render_to_escpos(template_doc, context):
	"""Render template to raw ESC/POS bytes using the Dummy printer."""
	try:
		from escpos.printer import Dummy
	except ImportError:
		frappe.throw("python-escpos is not installed. Run: bench pip install python-escpos")

	chars = CHARS_PER_LINE.get(getattr(template_doc, "paper_width", "80mm"), 48)
	rendered = frappe.render_template(template_doc.template_content or "", context)

	p = Dummy()
	if getattr(template_doc, "open_cash_drawer", False):
		p.cashdraw(2)

	_process_escpos(p, rendered, chars)

	if getattr(template_doc, "auto_cut", True):
		p.cut()

	return p.output


def _process_escpos(p, content, chars):
	for line in content.split("\n"):
		raw = line.rstrip()
		s = raw.strip()

		if not s:
			p.text("\n")
		elif s == "[CUT]":
			p.cut()
		elif s == "[PCUT]":
			try:
				p.cut(mode="PART")
			except Exception:
				p.cut()
		elif s == "[DRAWER]":
			p.cashdraw(2)
		elif s == "[LINE]":
			p.set(**_RESET)
			p.text("-" * chars + "\n")
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
		elif m := re.fullmatch(r"\[QR:([^\]:]+)(?::(\d+))?\]", s):
			_qr(p, m.group(1), int(m.group(2) or 6))
		elif m := re.fullmatch(r"\[HEX:([0-9A-Fa-f]+)\]", s):
			h = m.group(1)
			if len(h) % 2 == 0:
				p._raw(bytes.fromhex(h))
		else:
			_print_styled_line(p, raw)


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


def _print_styled_line(p, line):
	"""Parse inline [TAGS], build p.set() kwargs, and print the line."""
	# Alignment
	align = "left"
	if re.search(r"\[C(?:ENTER)?\]", line, re.I):
		align = "center"
		line = re.sub(r"\[/?C(?:ENTER)?\]", "", line, flags=re.I)
	elif re.search(r"\[R(?:IGHT)?\]", line, re.I):
		align = "right"
		line = re.sub(r"\[/?R(?:IGHT)?\]", "", line, flags=re.I)
	elif re.search(r"\[L(?:EFT)?\]", line, re.I):
		line = re.sub(r"\[/?L(?:EFT)?\]", "", line, flags=re.I)

	# Underline
	underline = 0
	if "[UU]" in line:
		underline = 2
		line = line.replace("[UU]", "").replace("[/UU]", "")
	elif "[U]" in line:
		underline = 1
		line = line.replace("[U]", "").replace("[/U]", "")

	# Invert / Flip / Font
	invert = bool(re.search(r"\[INV(?:ERT)?\]", line, re.I))
	if invert:
		line = re.sub(r"\[/?INV(?:ERT)?\]", "", line, flags=re.I)

	flip = "[FLIP]" in line
	if flip:
		line = line.replace("[FLIP]", "").replace("[/FLIP]", "")

	font = "b" if re.search(r"\[F(?:ONT)?B\]", line, re.I) else "a"
	if font == "b":
		line = re.sub(r"\[/?F(?:ONT)?B\]", "", line, flags=re.I)

	# Size
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

	kw = dict(align=align, bold=bold, underline=underline, double_width=dw,
		double_height=dh, font=font, invert=invert, flip=flip)
	if w > 2 or h > 2:
		kw.update(custom_size=True, width=w, height=h)

	p.set(**kw)
	p.text(line + "\n")
	p.set(**_RESET)


# ---------------------------------------------------------------------------
# HTML renderer (for PDF preview of Thermal templates)
# ---------------------------------------------------------------------------


def render_to_html(rendered, paper_width="80mm"):
	"""Convert rendered template text (tags intact) to HTML receipt for PDF."""
	import html as hl

	chars = CHARS_PER_LINE.get(paper_width, 48)
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
		elif m := re.fullmatch(r"\[QR:([^\]:]+)(?::(\d+))?\]", s):
			lines.append(
				f'<div style="text-align:center;font-size:0.8em;color:#555">'
				f"&#9646; QR: {hl.escape(m.group(1))} &#9646;</div>"
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
    padding: 8px;
    line-height: 1.5;
  }}
  div {{ margin: 0; padding: 0; white-space: pre-wrap; word-break: break-all; }}
</style></head>
<body>{body}</body>
</html>"""


def _line_to_html(line):
	import html as hl

	align = "left"
	if re.search(r"\[C(?:ENTER)?\]", line, re.I):
		align = "center"
		line = re.sub(r"\[/?C(?:ENTER)?\]", "", line, flags=re.I)
	elif re.search(r"\[R(?:IGHT)?\]", line, re.I):
		align = "right"
		line = re.sub(r"\[/?R(?:IGHT)?\]", "", line, flags=re.I)
	elif re.search(r"\[L(?:EFT)?\]", line, re.I):
		line = re.sub(r"\[/?L(?:EFT)?\]", "", line, flags=re.I)

	td = ""
	if "[UU]" in line:
		td = "text-decoration:underline double;"
		line = line.replace("[UU]", "").replace("[/UU]", "")
	elif "[U]" in line:
		td = "text-decoration:underline;"
		line = line.replace("[U]", "").replace("[/U]", "")

	invert = bool(re.search(r"\[INV(?:ERT)?\]", line, re.I))
	if invert:
		line = re.sub(r"\[/?INV(?:ERT)?\]", "", line, flags=re.I)

	flip = "[FLIP]" in line
	if flip:
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
	if "[H2]" in line:
		line = line.replace("[H2]", "").replace("[/H2]", "")

	if re.search(r"\[B(?:OLD)?\]", line, re.I):
		bold_s = "font-weight:bold;"
		line = re.sub(r"\[/?B(?:OLD)?\]", "", line, flags=re.I)

	style = f"text-align:{align};" + bold_s + size_s + td + font_s
	if invert:
		style += "background:#000;color:#fff;"
	if flip:
		style += "transform:rotate(180deg);display:inline-block;width:100%;"

	return f'<div style="{style}">{hl.escape(line)}</div>'

"""
ESC/POS template rendering for thermal printers.
Requires: bench pip install python-escpos
"""

import re

import frappe

CHARS_PER_LINE = {"80mm": 48, "58mm": 32}


def render_thermal_template(template_doc, context):
	"""
	Render a Thermal Print Template to raw ESC/POS bytes.

	:param template_doc: Thermal Print Template doc or name string
	:param context: dict passed to Jinja renderer
	:return: bytes
	"""
	try:
		from escpos.printer import Dummy
	except ImportError:
		frappe.throw("python-escpos is not installed. Run: bench pip install python-escpos")

	if isinstance(template_doc, str):
		template_doc = frappe.get_doc("Thermal Print Template", template_doc)

	chars = CHARS_PER_LINE.get(template_doc.paper_width, 48)

	rendered = frappe.render_template(template_doc.template_content, context)

	p = Dummy()

	if template_doc.open_cash_drawer:
		p.cashdraw(2)

	_process_content(p, rendered, chars)

	if template_doc.auto_cut:
		p.cut()

	return p.output


def _process_content(p, content, chars):
	"""Walk rendered content line by line and emit ESC/POS commands."""
	for line in content.split("\n"):
		raw = line.rstrip()
		stripped = raw.strip()

		# --- Block-level tags (must be alone on a line) ---
		if stripped == "[CUT]":
			p.cut()
		elif stripped == "[DRAWER]":
			p.cashdraw(2)
		elif stripped == "[LINE]":
			p.set(align="left", bold=False, double_width=False, double_height=False)
			p.text("-" * chars + "\n")
		elif stripped == "[DLINE]":
			p.set(align="left", bold=False, double_width=False, double_height=False)
			p.text("=" * chars + "\n")
		elif stripped.startswith("[BARCODE:"):
			m = re.match(r"\[BARCODE:([^:\]]+)(?::([^\]]+))?\]", stripped)
			if m:
				value, bc_type = m.group(1), (m.group(2) or "CODE39").upper()
				try:
					p.barcode(value, bc_type, function_type="B")
				except Exception:
					p.text(value + "\n")
		elif stripped.startswith("[QR:"):
			m = re.match(r"\[QR:(?:\x22([^\x22]*)\x22|([^\]]+))\]", stripped)
			if m:
				val = m.group(1) if m.group(1) is not None else m.group(2)
				try:
					p.qr(val, size=6)
				except Exception:
					p.text(val + "\n")
		else:
			# --- Inline formatting tags ---
			_print_line(p, raw)


def _print_line(p, line):
	"""Parse inline [CENTER], [BOLD], [BIG] tags and print the line."""
	align = "left"
	bold = False
	big = False

	if "[CENTER]" in line:
		align = "center"
		line = line.replace("[CENTER]", "").replace("[/CENTER]", "")
	elif "[RIGHT]" in line:
		align = "right"
		line = line.replace("[RIGHT]", "").replace("[/RIGHT]", "")

	if "[BOLD]" in line:
		bold = True
		line = line.replace("[BOLD]", "").replace("[/BOLD]", "")

	if "[BIG]" in line:
		big = True
		bold = True
		line = line.replace("[BIG]", "").replace("[/BIG]", "")

	p.set(
		align=align,
		bold=bold,
		double_width=big,
		double_height=big,
	)
	p.text(line + "\n")

	# Reset to defaults after each line
	p.set(align="left", bold=False, double_width=False, double_height=False)


def send_raw_to_cups(server_doc, cups_printer_name, raw_bytes, job_name="thermal-print"):
	"""Send raw ESC/POS bytes to a CUPS printer via IPP."""
	from printer_server_configuration.printer_server_configuration.utils.cups_utils import (
		OP_PRINT_JOB,
		TAG_MIMETYPE,
		TAG_NAME,
		TAG_JOB,
		_base_attrs,
		_make_printer_uri,
		_send,
	)

	uri = _make_printer_uri(server_doc, cups_printer_name)
	op_attrs = _base_attrs(server_doc, uri) + [
		(TAG_MIMETYPE, "document-format", "application/vnd.cups-raw"),
	]
	job_attrs = [(TAG_NAME, "job-name", job_name)]

	status, groups = _send(
		server_doc,
		f"/printers/{cups_printer_name}",
		OP_PRINT_JOB,
		op_attrs,
		extra_groups=[(TAG_JOB, job_attrs)],
		document=raw_bytes,
	)

	if status > 0x00FF:
		frappe.throw(f"CUPS error: 0x{status:04x}")

	return groups[0].get("job-id") if groups else None

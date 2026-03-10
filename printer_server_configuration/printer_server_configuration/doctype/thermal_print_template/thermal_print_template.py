import html as html_module
import re

import frappe
from frappe.model.document import Document


class ThermalPrintTemplate(Document):
	@frappe.whitelist()
	def preview(self, document_name=None):
		"""Return rendered template text (without ESC/POS bytes) for preview."""
		context = {"doc": {}}
		if self.document_type and document_name:
			context["doc"] = frappe.get_doc(self.document_type, document_name).as_dict()

		return frappe.render_template(self.template_content, context)

	@frappe.whitelist()
	def preview_pdf(self, document_name=None):
		"""Return base64-encoded PDF of the rendered template for browser preview."""
		import base64

		from frappe.utils.pdf import get_pdf

		context = {"doc": {}}
		if self.document_type and document_name:
			context["doc"] = frappe.get_doc(self.document_type, document_name).as_dict()

		rendered = frappe.render_template(self.template_content, context)
		html = _rendered_to_html(rendered, self.paper_width or "80mm")
		pdf_bytes = get_pdf(html)
		return base64.b64encode(pdf_bytes).decode()

	@frappe.whitelist()
	def print_test(self, printer, document_name=None):
		"""Send a test print to the given Printer."""
		from printer_server_configuration.printer_server_configuration.utils.escpos_utils import (
			render_thermal_template,
			send_raw_to_cups,
		)

		context = {"doc": {}}
		if self.document_type and document_name:
			context["doc"] = frappe.get_doc(self.document_type, document_name).as_dict()

		printer_doc = frappe.get_doc("Printer", printer)
		server_doc = frappe.get_doc("Printer Server", printer_doc.printer_server)

		raw_bytes = render_thermal_template(self, context)
		job_id = send_raw_to_cups(server_doc, printer_doc.cups_printer_name, raw_bytes, self.template_name)
		return {"success": True, "cups_job_id": job_id}


def _rendered_to_html(rendered, paper_width="80mm"):
	"""Convert rendered template text (with [TAGS]) to an HTML receipt for PDF generation."""
	width_px = "302px" if paper_width == "80mm" else "220px"

	lines_html = []
	for line in rendered.split("\n"):
		raw = line.rstrip()
		stripped = raw.strip()

		if stripped in ("[CUT]", "[DRAWER]"):
			pass
		elif stripped == "[LINE]":
			lines_html.append('<hr style="border:none;border-top:1px dashed #000;margin:2px 0">')
		elif stripped == "[DLINE]":
			lines_html.append('<hr style="border:none;border-top:2px solid #000;margin:2px 0">')
		elif stripped.startswith("[BARCODE:"):
			m = re.match(r"\[BARCODE:([^:\]]+)(?::([^\]]+))?\]", stripped)
			if m:
				lines_html.append(
					f'<div style="text-align:center;font-size:0.85em">[Barcode: {html_module.escape(m.group(1))}]</div>'
				)
		elif stripped.startswith("[QR:"):
			m = re.match(r"\[QR:([^\]]+)\]", stripped)
			if m:
				lines_html.append(
					f'<div style="text-align:center;font-size:0.85em">[QR: {html_module.escape(m.group(1))}]</div>'
				)
		else:
			lines_html.append(_line_to_html(raw))

	body = "\n".join(lines_html)
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
	"""Convert a single line with inline [TAGS] to an HTML div."""
	align = "left"

	if "[CENTER]" in line:
		align = "center"
		line = line.replace("[CENTER]", "").replace("[/CENTER]", "")
	elif "[RIGHT]" in line:
		align = "right"
		line = line.replace("[RIGHT]", "").replace("[/RIGHT]", "")

	big = "[BIG]" in line
	bold = "[BOLD]" in line or big
	line = line.replace("[BOLD]", "").replace("[/BOLD]", "")
	line = line.replace("[BIG]", "").replace("[/BIG]", "")

	text = html_module.escape(line)
	style = f"text-align:{align};"
	if big:
		style += "font-size:1.5em;font-weight:bold;"
	elif bold:
		style += "font-weight:bold;"

	return f'<div style="{style}">{text}</div>'

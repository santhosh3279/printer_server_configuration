import frappe
from frappe.model.document import Document

from printer_server_configuration.printer_server_configuration.utils.render_utils import (
	build_context,
	render_to_escpos,
	render_to_html,
)


def _inject_style(html, style):
	if "<head>" in html:
		return html.replace("<head>", f"<head>{style}", 1)
	if "<html>" in html:
		return html.replace("<html>", f"<html><head>{style}</head>", 1)
	return style + html


def _wrap_body(html, css_class):
	"""Wrap content inside <body>…</body> in a div; falls back to wrapping the whole string."""
	import re
	m = re.search(r"<body[^>]*>", html)
	close = html.rfind("</body>")
	if m and close != -1:
		return (
			html[: m.end()]
			+ f'<div class="{css_class}">'
			+ html[m.end() : close]
			+ "</div>"
			+ html[close:]
		)
	return f'<div class="{css_class}">{html}</div>'


def _build_custom_pdf(html, page_size, orientation):
	"""Prepare HTML and wkhtmltopdf options for Custom PDF.

	A5 always outputs on an A4 sheet (no paper change needed).
	- Landscape: content placed flat in the top half of portrait A4.
	  Top of content = top of page, bottom of content = middle of page.
	- Portrait: content rotated 90° CCW inside the top half of portrait A4.
	  Top edge of content → left edge of A4, bottom edge → right edge of A4.
	"""
	if page_size != "A5":
		return html, {"page-size": page_size, "orientation": orientation}

	if orientation == "Landscape":
		# A5 landscape (210 × 148 mm) fills the top half of portrait A4 — no rotation
		style = (
			"<style>"
			"@page{size:A4 portrait;margin:0}"
			"html,body{margin:0;padding:0;width:210mm;height:148mm;overflow:hidden}"
			"</style>"
		)
		html = _inject_style(html, style)
	else:
		# Portrait: rotate content -90° so top edge → left of A4, bottom edge → right of A4.
		# A 148 × 210 mm element at origin with transform: translateY(148mm) rotate(-90deg)
		# ends up occupying x=[0,210mm], y=[0,148mm] on the A4 sheet.
		style = (
			"<style>"
			"@page{size:A4 portrait;margin:0}"
			"html,body{margin:0;padding:0}"
			".a5-wrap{"
			"position:absolute;top:0;left:0;"
			"width:148mm;height:210mm;"
			"transform-origin:0 0;"
			"transform:translateY(148mm) rotate(-90deg)"
			"}"
			"</style>"
		)
		html = _inject_style(html, style)
		html = _wrap_body(html, "a5-wrap")

	return html, {"page-size": "A4", "orientation": "Portrait"}


class PrintTemplate(Document):
	@frappe.whitelist()
	def preview(self, document_name=None):
		"""Return rendered text for quick inspection."""
		ctx = build_context(self, document_name)
		if self.format_type == "Thermal":
			return frappe.render_template(self.template_content or "", ctx)
		elif self.format_type == "Barcode":
			return frappe.render_template(self.barcode_template or "", ctx)
		elif self.format_type == "PDF":
			if not document_name:
				frappe.throw("Document Name is required for PDF preview.")
			return frappe.get_print(
				self.document_type, document_name, self.print_format, letterhead=self.letter_head
			)
		elif self.format_type == "Custom PDF":
			return frappe.render_template(self.custom_pdf_template or "", ctx)

		elif self.format_type == "HTML":
			return frappe.render_template(self.template_content or "", ctx)

	@frappe.whitelist()
	def preview_pdf(self, document_name=None):
		"""Return base64-encoded PDF for browser preview."""
		import base64

		from frappe.utils.pdf import get_pdf

		if self.format_type == "PDF":
			if not document_name:
				frappe.throw("Document Name is required for PDF preview.")
			html = frappe.get_print(
				self.document_type, document_name, self.print_format, letterhead=self.letter_head
			)
			return base64.b64encode(get_pdf(html)).decode()

		elif self.format_type == "Thermal":
			ctx = build_context(self, document_name)
			rendered = frappe.render_template(self.template_content or "", ctx)
			html = render_to_html(rendered, self.paper_width or "80mm")
			return base64.b64encode(get_pdf(html)).decode()

		elif self.format_type == "Barcode":
			import html as html_module

			ctx = build_context(self, document_name)
			zpl = frappe.render_template(self.barcode_template or "", ctx)
			preview_html = f"""<html><head><meta charset='utf-8'>
<style>body{{font-family:monospace;font-size:12px;padding:16px}}
pre{{background:#f5f5f5;padding:12px;border:1px solid #ddd;white-space:pre-wrap}}</style>
</head><body>
<p style='color:#888;margin-bottom:8px'>ZPL Output — {self.label_width_mm or 50}mm × {self.label_height_mm or 30}mm</p>
<pre>{html_module.escape(zpl)}</pre>
</body></html>"""
			return base64.b64encode(get_pdf(preview_html)).decode()

		elif self.format_type == "Custom PDF":
			ctx = build_context(self, document_name)
			html = frappe.render_template(self.custom_pdf_template or "", ctx)
			if self.custom_pdf_letter_head:
				lh = frappe.get_doc("Letter Head", self.custom_pdf_letter_head)
				html = f"<div>{lh.content}</div>{html}"
			html, options = _build_custom_pdf(
				html, self.custom_pdf_page_size or "A4", self.custom_pdf_orientation or "Portrait"
			)
			return base64.b64encode(get_pdf(html, options=options)).decode()

		elif self.format_type == "HTML":
			ctx = build_context(self, document_name)
			html = frappe.render_template(self.template_content or "", ctx)
			return base64.b64encode(get_pdf(html)).decode()

	@frappe.whitelist()
	def print_doc(self, printer, document_name=None, copies=1):
		"""Render and send to the given Printer via CUPS."""
		from printer_server_configuration.printer_server_configuration.utils.cups_utils import (
			send_pdf_to_cups,
		)
		from printer_server_configuration.printer_server_configuration.utils.escpos_utils import (
			send_raw_to_cups,
		)

		printer_doc = frappe.get_doc("Printer", printer)
		server_doc = frappe.get_doc("Printer Server", printer_doc.printer_server)
		copies = int(copies or 1)

		if self.format_type == "Thermal":
			ctx = build_context(self, document_name)
			raw_bytes = render_to_escpos(self, ctx)
			job_id = send_raw_to_cups(
				server_doc, printer_doc.cups_printer_name, raw_bytes, self.template_name
			)
			return {"success": True, "cups_job_id": job_id}

		elif self.format_type == "PDF":
			from frappe.utils.pdf import get_pdf

			if not document_name:
				frappe.throw("Document Name is required for PDF printing.")
			html = frappe.get_print(
				self.document_type, document_name, self.print_format, letterhead=self.letter_head
			)
			pdf_bytes = get_pdf(html)
			job_id = None
			for _ in range(copies):
				job_id = send_pdf_to_cups(
					server_doc, printer_doc.cups_printer_name, pdf_bytes, document_name or self.template_name
				)
			return {"success": True, "cups_job_id": job_id}

		elif self.format_type == "Barcode":
			ctx = build_context(self, document_name)
			zpl = frappe.render_template(self.barcode_template or "", ctx)
			raw_bytes = zpl.encode("utf-8")
			total = copies * int(self.copies_per_doc or 1)
			job_id = None
			for _ in range(total):
				job_id = send_raw_to_cups(
					server_doc, printer_doc.cups_printer_name, raw_bytes, self.template_name
				)
			return {"success": True, "cups_job_id": job_id, "copies_sent": total}

		elif self.format_type == "Custom PDF":
			from frappe.utils.pdf import get_pdf

			ctx = build_context(self, document_name)
			html = frappe.render_template(self.custom_pdf_template or "", ctx)
			if self.custom_pdf_letter_head:
				lh = frappe.get_doc("Letter Head", self.custom_pdf_letter_head)
				html = f"<div>{lh.content}</div>{html}"
			html, options = _build_custom_pdf(
				html, self.custom_pdf_page_size or "A4", self.custom_pdf_orientation or "Portrait"
			)
			pdf_bytes = get_pdf(html, options=options)
			job_id = None
			for _ in range(copies):
				job_id = send_pdf_to_cups(
					server_doc, printer_doc.cups_printer_name, pdf_bytes, document_name or self.template_name
				)
			return {"success": True, "cups_job_id": job_id}

		elif self.format_type == "HTML":
			from frappe.utils.pdf import get_pdf

			ctx = build_context(self, document_name)
			html = frappe.render_template(self.template_content or "", ctx)
			pdf_bytes = get_pdf(html)
			job_id = None
			for _ in range(copies):
				job_id = send_pdf_to_cups(
					server_doc, printer_doc.cups_printer_name, pdf_bytes, document_name or self.template_name
				)
			return {"success": True, "cups_job_id": job_id}

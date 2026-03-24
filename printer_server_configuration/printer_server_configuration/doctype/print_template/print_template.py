import frappe
from frappe.model.document import Document

from printer_server_configuration.printer_server_configuration.utils.render_utils import (
	build_context,
	render_to_escpos,
	render_to_html,
)


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

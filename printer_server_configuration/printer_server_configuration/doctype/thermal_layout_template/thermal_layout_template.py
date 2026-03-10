import frappe
from frappe.model.document import Document


class ThermalLayoutTemplate(Document):
	@frappe.whitelist()
	def preview(self, document_name=None):
		"""Return rendered template text (tags intact) for inspection."""
		context = _build_context(self, document_name)
		return frappe.render_template(self.template_content, context)

	@frappe.whitelist()
	def preview_pdf(self, document_name=None):
		"""Return base64-encoded PDF receipt for browser preview."""
		import base64

		from frappe.utils.pdf import get_pdf
		from printer_server_configuration.printer_server_configuration.utils.layout_utils import (
			layout_to_html,
		)

		context = _build_context(self, document_name)
		rendered = frappe.render_template(self.template_content, context)
		html = layout_to_html(rendered, self.paper_width or "80mm")
		return base64.b64encode(get_pdf(html)).decode()

	@frappe.whitelist()
	def print_test(self, printer, document_name=None):
		"""Render and send directly to a Printer doc via CUPS."""
		from printer_server_configuration.printer_server_configuration.utils.escpos_utils import (
			send_raw_to_cups,
		)
		from printer_server_configuration.printer_server_configuration.utils.layout_utils import (
			render_layout_template,
		)

		context = _build_context(self, document_name)
		printer_doc = frappe.get_doc("Printer", printer)
		server_doc = frappe.get_doc("Printer Server", printer_doc.printer_server)
		raw_bytes = render_layout_template(self, context)
		job_id = send_raw_to_cups(server_doc, printer_doc.cups_printer_name, raw_bytes, self.template_name)
		return {"success": True, "cups_job_id": job_id}


def _build_context(template_doc, document_name):
	context = {"doc": {}}
	if template_doc.document_type and document_name:
		context["doc"] = frappe.get_doc(template_doc.document_type, document_name).as_dict()
	return context

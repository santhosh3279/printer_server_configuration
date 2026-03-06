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

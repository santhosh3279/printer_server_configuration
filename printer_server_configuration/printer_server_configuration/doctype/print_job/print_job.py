import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class PrintJob(Document):
	def before_insert(self):
		self.status = "Pending"
		self.submitted_at = now_datetime()

	def validate(self):
		if self.job_type == "File" and not self.file_url:
			frappe.throw("File URL is required for File job type.")
		if self.job_type == "Thermal" and not self.thermal_template:
			frappe.throw("Thermal Template is required for Thermal job type.")

	@frappe.whitelist()
	def submit_to_cups(self):
		if self.job_type == "Thermal":
			return self._submit_thermal()
		return self._submit_file()

	def _submit_file(self):
		from printer_server_configuration.printer_server_configuration.utils.cups_utils import (
			submit_print_job,
		)

		return submit_print_job(self)

	def _submit_thermal(self):
		from printer_server_configuration.printer_server_configuration.utils.escpos_utils import (
			render_thermal_template,
			send_raw_to_cups,
		)

		template_doc = frappe.get_doc("Thermal Print Template", self.thermal_template)

		context = {"doc": {}}
		if self.document_type and self.document_name:
			context["doc"] = frappe.get_doc(self.document_type, self.document_name).as_dict()

		raw_bytes = render_thermal_template(template_doc, context)

		printer_doc = frappe.get_doc("Printer", self.printer)
		server_doc = frappe.get_doc("Printer Server", printer_doc.printer_server)

		try:
			job_id = send_raw_to_cups(server_doc, printer_doc.cups_printer_name, raw_bytes, self.name)
			if job_id is not None:
				self.db_set("cups_job_id", job_id)
			self.db_set("status", "Sent")
			return {"success": True, "cups_job_id": job_id}
		except Exception as e:
			self.db_set("status", "Failed")
			self.db_set("error_message", str(e))
			frappe.throw(str(e))

	@frappe.whitelist()
	def refresh_status(self):
		from printer_server_configuration.printer_server_configuration.utils.cups_utils import (
			get_job_status,
		)

		if not self.cups_job_id:
			frappe.throw("No CUPS Job ID assigned yet.")
		return get_job_status(self)

	@frappe.whitelist()
	def cancel_job(self):
		from printer_server_configuration.printer_server_configuration.utils.cups_utils import (
			cancel_print_job,
		)

		return cancel_print_job(self)

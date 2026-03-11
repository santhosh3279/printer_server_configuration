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

	@frappe.whitelist()
	def submit_to_cups(self):
		return self._submit_file()

	def _submit_file(self):
		from printer_server_configuration.printer_server_configuration.utils.cups_utils import (
			submit_print_job,
		)

		return submit_print_job(self)

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

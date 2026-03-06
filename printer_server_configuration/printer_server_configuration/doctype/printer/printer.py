import frappe
from frappe.model.document import Document


class Printer(Document):
	def validate(self):
		if self.is_default:
			frappe.db.set_value(
				"Printer",
				{"name": ["!=", self.name], "is_default": 1},
				"is_default",
				0,
			)

	@frappe.whitelist()
	def refresh_status(self):
		from printer_server_configuration.printer_server_configuration.utils.cups_utils import (
			get_printer_status,
		)

		status = get_printer_status(self)
		self.db_set("status", status)
		return status

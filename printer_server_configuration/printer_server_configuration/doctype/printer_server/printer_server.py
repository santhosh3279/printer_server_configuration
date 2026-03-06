import frappe
from frappe.model.document import Document


class PrinterServer(Document):
	def validate(self):
		if self.is_default:
			frappe.db.set_value(
				"Printer Server",
				{"name": ["!=", self.name], "is_default": 1},
				"is_default",
				0,
			)

	@frappe.whitelist()
	def test_connection(self):
		from printer_server_configuration.printer_server_configuration.utils.cups_utils import (
			test_cups_connection,
		)

		return test_cups_connection(self)

	@frappe.whitelist()
	def sync_printers(self):
		from printer_server_configuration.printer_server_configuration.utils.cups_utils import (
			sync_printers_from_cups,
		)

		return sync_printers_from_cups(self)

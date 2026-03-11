import frappe


@frappe.whitelist()
def get_printers(printer_server=None):
	"""Return list of configured printers, optionally filtered by server."""
	filters = {}
	if printer_server:
		filters["printer_server"] = printer_server

	return frappe.get_all(
		"Printer",
		filters=filters,
		fields=["name", "printer_name", "printer_server", "cups_printer_name", "status", "is_default", "location"],
	)


@frappe.whitelist()
def get_default_printer():
	"""Return the default printer."""
	result = frappe.get_all(
		"Printer",
		filters={"is_default": 1},
		fields=["name", "printer_name", "printer_server", "cups_printer_name"],
		limit=1,
	)
	return result[0] if result else None


@frappe.whitelist()
def print_document(printer, print_template, document_type=None, document_name=None, copies=1, title=None):
	"""Render a Print Template (Thermal / PDF / Barcode) and send to CUPS."""
	template_doc = frappe.get_doc("Print Template", print_template)
	return template_doc.print_doc(printer=printer, document_name=document_name, copies=int(copies or 1))


@frappe.whitelist()
def sync_all_servers():
	"""Sync printers from all configured CUPS servers."""
	servers = frappe.get_all("Printer Server", fields=["name"])
	results = {}
	for server in servers:
		doc = frappe.get_doc("Printer Server", server.name)
		try:
			results[server.name] = doc.sync_printers()
		except Exception as e:
			results[server.name] = {"error": str(e)}
	return results

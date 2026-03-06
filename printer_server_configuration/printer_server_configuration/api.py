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
def print_file(printer, file_url, title=None, copies=1, document_type=None, document_name=None):
	"""Create a Print Job and send it to CUPS immediately."""
	job = frappe.get_doc(
		{
			"doctype": "Print Job",
			"printer": printer,
			"file_url": file_url,
			"job_title": title or file_url,
			"copies": int(copies),
			"document_type": document_type,
			"document_name": document_name,
		}
	)
	job.insert(ignore_permissions=True)
	result = job.submit_to_cups()
	return {"job": job.name, **result}


@frappe.whitelist()
def print_thermal(printer, thermal_template, document_type=None, document_name=None, title=None):
	"""Create a thermal Print Job and send ESC/POS bytes to CUPS immediately."""
	job = frappe.get_doc(
		{
			"doctype": "Print Job",
			"printer": printer,
			"job_type": "Thermal",
			"thermal_template": thermal_template,
			"job_title": title or thermal_template,
			"document_type": document_type,
			"document_name": document_name,
		}
	)
	job.insert(ignore_permissions=True)
	result = job.submit_to_cups()
	return {"job": job.name, **result}


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

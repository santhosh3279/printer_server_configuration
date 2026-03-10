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
def print_layout(printer, layout_template, document_type=None, document_name=None, title=None):
	"""Render a Thermal Layout Template and send ESC/POS bytes to CUPS."""
	from printer_server_configuration.printer_server_configuration.utils.escpos_utils import (
		send_raw_to_cups,
	)
	from printer_server_configuration.printer_server_configuration.utils.layout_utils import (
		render_layout_template,
	)

	template_doc = frappe.get_doc("Thermal Layout Template", layout_template)
	context = {"doc": {}}
	if document_type and document_name:
		context["doc"] = frappe.get_doc(document_type, document_name).as_dict()

	printer_doc = frappe.get_doc("Printer", printer)
	server_doc = frappe.get_doc("Printer Server", printer_doc.printer_server)
	raw_bytes = render_layout_template(template_doc, context)
	job_id = send_raw_to_cups(server_doc, printer_doc.cups_printer_name, raw_bytes, title or layout_template)
	return {"success": True, "cups_job_id": job_id}


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

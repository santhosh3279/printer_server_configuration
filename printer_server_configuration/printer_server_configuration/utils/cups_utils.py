"""
Pure-Python IPP client for communicating with a remote CUPS server.
Uses only `requests` (already a Frappe dependency) — no libcups required.
"""

import io
import struct
import warnings

import frappe
import requests
import urllib3

warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------------
# IPP Protocol Constants
# ---------------------------------------------------------------------------

# Delimiter group tags
TAG_OPERATION = 0x01
TAG_JOB = 0x02
TAG_END = 0x03
TAG_PRINTER = 0x04

# Value tags
TAG_INTEGER = 0x21
TAG_BOOLEAN = 0x22
TAG_ENUM = 0x23
TAG_URI = 0x45
TAG_CHARSET = 0x47
TAG_LANGUAGE = 0x48
TAG_MIMETYPE = 0x49
TAG_KEYWORD = 0x44
TAG_NAME = 0x42  # nameWithoutLanguage
TAG_TEXT = 0x41  # textWithoutLanguage

# Operation IDs
OP_PRINT_JOB = 0x0002
OP_CANCEL_JOB = 0x0008
OP_GET_JOB_ATTRIBUTES = 0x0009
OP_GET_PRINTER_ATTRIBUTES = 0x000B
OP_CUPS_GET_PRINTERS = 0x4002


# ---------------------------------------------------------------------------
# IPP Encoding
# ---------------------------------------------------------------------------

def _enc(tag, name, value):
	name_b = name.encode() if name else b""
	if tag in (TAG_INTEGER, TAG_ENUM):
		val_b = struct.pack(">i", int(value))
	elif tag == TAG_BOOLEAN:
		val_b = bytes([1 if value else 0])
	else:
		val_b = value.encode() if isinstance(value, str) else bytes(value)
	return (
		struct.pack(">B", tag)
		+ struct.pack(">H", len(name_b))
		+ name_b
		+ struct.pack(">H", len(val_b))
		+ val_b
	)


def _build_request(op_id, op_attrs, extra_groups=None, request_id=1):
	buf = io.BytesIO()
	buf.write(b"\x01\x01")  # IPP/1.1
	buf.write(struct.pack(">H", op_id))
	buf.write(struct.pack(">I", request_id))
	buf.write(bytes([TAG_OPERATION]))
	for args in op_attrs:
		buf.write(_enc(*args))
	if extra_groups:
		for group_tag, attrs in extra_groups:
			buf.write(bytes([group_tag]))
			for args in attrs:
				buf.write(_enc(*args))
	buf.write(bytes([TAG_END]))
	return buf.getvalue()


# ---------------------------------------------------------------------------
# IPP Decoding
# ---------------------------------------------------------------------------

def _parse_response(raw):
	buf = io.BytesIO(raw)
	buf.read(2)  # version
	status = struct.unpack(">H", buf.read(2))[0]
	buf.read(4)  # request-id

	groups = []
	current = {}
	last_name = None

	while True:
		b = buf.read(1)
		if not b:
			break
		tag = b[0]

		if tag == TAG_END:
			if current:
				groups.append(current)
			break
		elif tag <= 0x0F:
			# Delimiter — start a new group
			if current:
				groups.append(current)
			current = {}
			last_name = None
			continue

		name_len = struct.unpack(">H", buf.read(2))[0]
		name = buf.read(name_len).decode("utf-8", errors="replace")
		val_len = struct.unpack(">H", buf.read(2))[0]
		raw_val = buf.read(val_len)

		if name:
			last_name = name
		else:
			name = last_name  # Additional value for the same attribute

		if not name:
			continue

		if tag in (TAG_INTEGER, TAG_ENUM):
			val = struct.unpack(">i", raw_val)[0] if len(raw_val) == 4 else int.from_bytes(raw_val, "big", signed=True)
		elif tag == TAG_BOOLEAN:
			val = bool(raw_val[0]) if raw_val else False
		else:
			val = raw_val.decode("utf-8", errors="replace")

		if name in current:
			existing = current[name]
			if not isinstance(existing, list):
				current[name] = [existing]
			current[name].append(val)
		else:
			current[name] = val

	return status, groups


# ---------------------------------------------------------------------------
# HTTP Transport
# ---------------------------------------------------------------------------

def _send(server_doc, path, op_id, op_attrs, extra_groups=None, document=None):
	scheme = "https" if server_doc.use_ssl else "http"
	url = f"{scheme}://{server_doc.host}:{int(server_doc.port or 631)}{path}"

	body = _build_request(op_id, op_attrs, extra_groups)
	if document:
		body += document

	auth = None
	if server_doc.username:
		auth = (server_doc.username, server_doc.get_password("password") or "")

	resp = requests.post(
		url,
		data=body,
		headers={"Content-Type": "application/ipp"},
		auth=auth,
		verify=False,
		timeout=15,
	)
	resp.raise_for_status()
	return _parse_response(resp.content)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_attrs(server_doc, printer_uri=None):
	attrs = [
		(TAG_CHARSET, "attributes-charset", "utf-8"),
		(TAG_LANGUAGE, "attributes-natural-language", "en"),
	]
	if printer_uri:
		attrs.append((TAG_URI, "printer-uri", printer_uri))
	return attrs


def _make_printer_uri(server_doc, cups_name):
	return f"ipp://{server_doc.host}:{int(server_doc.port or 631)}/printers/{cups_name}"


def _make_job_uri(server_doc, job_id):
	return f"ipp://{server_doc.host}:{int(server_doc.port or 631)}/jobs/{int(job_id)}"


def _map_cups_state(state):
	# 3 = Idle, 4 = Processing, 5 = Stopped
	return {3: "Ready", 4: "Ready", 5: "Offline"}.get(int(state) if state else 0, "Unknown")


def _map_job_state(state):
	# 3=Pending, 4=Pending-Held, 5=Processing, 6=Stopped, 7=Cancelled, 8=Aborted, 9=Completed
	return {
		3: "Pending",
		4: "Pending",
		5: "Sent",
		6: "Failed",
		7: "Cancelled",
		8: "Failed",
		9: "Completed",
	}.get(int(state) if state else 3, "Pending")


# ---------------------------------------------------------------------------
# Public Functions
# ---------------------------------------------------------------------------

def test_cups_connection(server_doc):
	if isinstance(server_doc, str):
		server_doc = frappe.get_doc("Printer Server", server_doc)

	status, groups = _send(server_doc, "/", OP_CUPS_GET_PRINTERS, _base_attrs(server_doc))

	if status > 0x00FF:
		frappe.throw(f"CUPS returned error status: 0x{status:04x}")

	printers = [g.get("printer-name", "") for g in groups if g.get("printer-name")]
	return {"success": True, "printer_count": len(printers), "printers": printers}


def sync_printers_from_cups(server_doc):
	if isinstance(server_doc, str):
		server_doc = frappe.get_doc("Printer Server", server_doc)

	status, groups = _send(server_doc, "/", OP_CUPS_GET_PRINTERS, _base_attrs(server_doc))

	if status > 0x00FF:
		frappe.throw(f"CUPS returned error status: 0x{status:04x}")

	synced = []
	updated = []

	for g in groups:
		cups_name = g.get("printer-name")
		if not cups_name:
			continue

		state = _map_cups_state(g.get("printer-state", 3))
		existing = frappe.db.get_value(
			"Printer",
			{"cups_printer_name": cups_name, "printer_server": server_doc.name},
		)

		if not existing:
			frappe.get_doc(
				{
					"doctype": "Printer",
					"printer_name": cups_name,
					"printer_server": server_doc.name,
					"cups_printer_name": cups_name,
					"description": g.get("printer-info", ""),
					"location": g.get("printer-location", ""),
					"status": state,
				}
			).insert(ignore_permissions=True)
			synced.append(cups_name)
		else:
			frappe.db.set_value("Printer", existing, "status", state)
			updated.append(cups_name)

	frappe.db.commit()
	return {"synced": synced, "updated": updated, "total": len(synced) + len(updated)}


def get_printer_status(printer_doc):
	if isinstance(printer_doc, str):
		printer_doc = frappe.get_doc("Printer", printer_doc)

	server_doc = frappe.get_doc("Printer Server", printer_doc.printer_server)
	uri = _make_printer_uri(server_doc, printer_doc.cups_printer_name)

	status, groups = _send(
		server_doc,
		f"/printers/{printer_doc.cups_printer_name}",
		OP_GET_PRINTER_ATTRIBUTES,
		_base_attrs(server_doc, uri) + [(TAG_KEYWORD, "requested-attributes", "printer-state")],
	)

	if not groups:
		return "Unknown"
	return _map_cups_state(groups[0].get("printer-state", 0))


def submit_print_job(job_doc):
	if isinstance(job_doc, str):
		job_doc = frappe.get_doc("Print Job", job_doc)

	printer_doc = frappe.get_doc("Printer", job_doc.printer)
	server_doc = frappe.get_doc("Printer Server", printer_doc.printer_server)
	uri = _make_printer_uri(server_doc, printer_doc.cups_printer_name)

	# Resolve file from Frappe file URL
	file_url = job_doc.file_url
	if file_url.startswith("/files/"):
		file_path = frappe.get_site_path("public" + file_url)
	elif file_url.startswith("/private/files/"):
		file_path = frappe.get_site_path(file_url.lstrip("/"))
	else:
		frappe.throw(f"Unsupported file URL format: {file_url}")

	with open(file_path, "rb") as f:
		document = f.read()

	op_attrs = _base_attrs(server_doc, uri) + [
		(TAG_MIMETYPE, "document-format", "application/octet-stream"),
	]
	job_attrs = [(TAG_NAME, "job-name", job_doc.name)]
	if job_doc.copies and int(job_doc.copies) > 1:
		job_attrs.append((TAG_INTEGER, "copies", int(job_doc.copies)))

	try:
		status, groups = _send(
			server_doc,
			f"/printers/{printer_doc.cups_printer_name}",
			OP_PRINT_JOB,
			op_attrs,
			extra_groups=[(TAG_JOB, job_attrs)],
			document=document,
		)

		if status > 0x00FF:
			raise Exception(f"CUPS error: 0x{status:04x}")

		job_id = groups[0].get("job-id") if groups else None
		job_doc.db_set("cups_job_id", job_id)
		job_doc.db_set("status", "Sent")
		return {"success": True, "cups_job_id": job_id}
	except Exception as e:
		job_doc.db_set("status", "Failed")
		job_doc.db_set("error_message", str(e))
		frappe.throw(str(e))


def get_job_status(job_doc):
	if isinstance(job_doc, str):
		job_doc = frappe.get_doc("Print Job", job_doc)

	printer_doc = frappe.get_doc("Printer", job_doc.printer)
	server_doc = frappe.get_doc("Printer Server", printer_doc.printer_server)
	job_uri = _make_job_uri(server_doc, job_doc.cups_job_id)

	try:
		status, groups = _send(
			server_doc,
			f"/jobs/{int(job_doc.cups_job_id)}",
			OP_GET_JOB_ATTRIBUTES,
			_base_attrs(server_doc) + [(TAG_URI, "job-uri", job_uri)],
		)
		if not groups:
			return {"error": "No job attributes returned"}

		job_status = _map_job_state(groups[0].get("job-state", 3))
		job_doc.db_set("status", job_status)
		return {"status": job_status}
	except Exception as e:
		return {"error": str(e)}


def send_raw_to_cups(server_doc, cups_printer_name, raw_bytes, job_name="raw-print"):
	"""Send raw bytes (ESC/POS, ZPL, TSPL) to a CUPS printer via IPP with octet-stream mime type."""
	uri = _make_printer_uri(server_doc, cups_printer_name)
	op_attrs = _base_attrs(server_doc, uri) + [
		(TAG_MIMETYPE, "document-format", "application/octet-stream"),
	]
	job_attrs = [(TAG_NAME, "job-name", job_name)]

	status, groups = _send(
		server_doc,
		f"/printers/{cups_printer_name}",
		OP_PRINT_JOB,
		op_attrs,
		extra_groups=[(TAG_JOB, job_attrs)],
		document=raw_bytes,
	)

	if status > 0x00FF:
		frappe.throw(f"CUPS error: 0x{status:04x}")

	return groups[0].get("job-id") if groups else None


def send_pdf_to_cups(server_doc, cups_printer_name, pdf_bytes, job_name="pdf-print", print_speed=None, paper_type=None):
	"""Send raw PDF bytes to a CUPS printer via IPP."""
	uri = _make_printer_uri(server_doc, cups_printer_name)
	op_attrs = _base_attrs(server_doc, uri) + [
		(TAG_MIMETYPE, "document-format", "application/pdf"),
	]
	job_attrs = [(TAG_NAME, "job-name", job_name)]
	if print_speed:
		job_attrs.append((TAG_INTEGER, "print-speed", int(print_speed)))
	if paper_type:
		job_attrs.append((TAG_KEYWORD, "media-type", str(paper_type)))

	status, groups = _send(
		server_doc,
		f"/printers/{cups_printer_name}",
		OP_PRINT_JOB,
		op_attrs,
		extra_groups=[(TAG_JOB, job_attrs)],
		document=pdf_bytes,
	)

	if status > 0x00FF:
		frappe.throw(f"CUPS error: 0x{status:04x}")

	return groups[0].get("job-id") if groups else None


def cancel_print_job(job_doc):
	if isinstance(job_doc, str):
		job_doc = frappe.get_doc("Print Job", job_doc)

	printer_doc = frappe.get_doc("Printer", job_doc.printer)
	server_doc = frappe.get_doc("Printer Server", printer_doc.printer_server)
	job_uri = _make_job_uri(server_doc, job_doc.cups_job_id)

	_send(
		server_doc,
		f"/jobs/{int(job_doc.cups_job_id)}",
		OP_CANCEL_JOB,
		_base_attrs(server_doc) + [(TAG_URI, "job-uri", job_uri)],
	)
	job_doc.db_set("status", "Cancelled")
	return {"success": True}

import frappe
from frappe.model.document import Document

from printer_server_configuration.printer_server_configuration.utils.render_utils import (
	build_context,
	build_report_context,
	render_to_escpos,
	render_to_html,
)


def _inject_style(html, style):
	if "<head>" in html:
		return html.replace("<head>", f"<head>{style}", 1)
	if "<html>" in html:
		return html.replace("<html>", f"<html><head>{style}</head>", 1)
	return style + html


def _suppress_frappe_margins(html):
	"""Inject empty header/footer marker divs so frappe's prepare_header_footer
	does not fall into the else-branch and unconditionally set margin-top/bottom to 15mm.
	Skips injection if the template already defines its own header/footer element."""
	markers = ""
	if 'id="header-html"' not in html and "id='header-html'" not in html:
		markers += '<div id="header-html"></div>'
	if 'id="footer-html"' not in html and "id='footer-html'" not in html:
		markers += '<div id="footer-html"></div>'
	if not markers:
		return html
	if "</body>" in html:
		return html.replace("</body>", markers + "</body>", 1)
	return html + markers


def _place_a5_on_a4(pdf_bytes, orientation):
	"""Place each A5 page from a wkhtmltopdf-generated PDF onto the top half of an A4 sheet.

	- Landscape: A5 page (210×148.5 mm) placed at the top of portrait A4, no rotation.
	  Content top = top of A4, content bottom = middle of A4.
	- Portrait: A5 page (148×210 mm) rotated 90° CCW, placed at the top of portrait A4.
	  Content top edge → left edge of A4, content bottom edge → right edge of A4.

	Rotation math (row-vector PDF convention, CCW 90°):
	  (x,y) → (-y, x)  after rotate(90)
	  Corners of 148×210mm page end up at x=[-210,0], y=[0,148] (all in mm).
	  Translate by tx=210mm, ty=(297-148)mm to land at x=[0,210], y=[149,297] (top half of A4).
	"""
	from io import BytesIO

	from pypdf import PdfReader, PdfWriter, Transformation

	MM = 72 / 25.4  # 1 mm in PDF points
	A4_W = 210 * MM  # ≈ 595.28 pt
	A4_H = 297 * MM  # ≈ 841.89 pt

	reader = PdfReader(BytesIO(pdf_bytes))
	writer = PdfWriter()

	for src_page in reader.pages:
		src_w = float(src_page.mediabox.width)   # points
		src_h = float(src_page.mediabox.height)  # points

		a4_page = writer.add_blank_page(width=A4_W, height=A4_H)

		if orientation == "Portrait":
			# Rotate 90° CCW: content moves to x=[-src_h, 0], y=[0, src_w]
			# Translate by (src_h, A4_H - src_w) to land at top of A4
			tf = Transformation().rotate(90).translate(src_h, A4_H - src_w)
		else:
			# No rotation — translate to top of A4
			tf = Transformation().translate(0, A4_H - src_h)

		a4_page.merge_transformed_page(src_page, tf)

	buf = BytesIO()
	writer.write(buf)
	return buf.getvalue()


def _build_custom_pdf(html, page_size, orientation, margins=None):
	"""Prepare HTML and wkhtmltopdf options for Custom PDF.

	Returns (html, options, a5_orientation).
	- a5_orientation is "Portrait" or "Landscape" when A5 post-processing is needed, else None.
	- Always suppresses Frappe's 15mm auto-margin injection so rendering is identical
	  across dev/Docker regardless of wkhtmltopdf version.
	- margins: dict with keys top/bottom/left/right (e.g. {"top": "10mm"}).
	  Defaults to 10mm on each side. Ignored for A5 (forced 0mm for correct placement).

	For A5: wkhtmltopdf renders into native A5 page dimensions so it paginates
	automatically when content overflows. Each resulting page is then placed onto
	the top half of an A4 sheet via pypdf (_place_a5_on_a4).
	"""
	m = margins or {}
	margin_top    = m.get("top")    or "0mm"
	margin_bottom = m.get("bottom") or "0mm"
	margin_left   = m.get("left")   or "0mm"
	margin_right  = m.get("right")  or "0mm"

	# Always suppress Frappe's prepare_header_footer auto-margin injection.
	# Without this, Frappe unconditionally adds margin-top/bottom 15mm whenever
	# no #header-html / #footer-html divs are present — behaviour that differs
	# between wkhtmltopdf versions and causes layout shifts in Docker production.
	html = _suppress_frappe_margins(html)

	if page_size != "A5":
		options = {
			"page-size": page_size,
			"orientation": orientation,
			"margin-top": margin_top,
			"margin-bottom": margin_bottom,
			"margin-left": margin_left,
			"margin-right": margin_right,
			"encoding": "utf-8",
		}
		return html, options, None

	# A5: force 0mm wkhtmltopdf margins — content spacing is handled entirely by
	# the template's CSS. Each rendered A5 page is then placed onto A4 via pypdf.
	if orientation == "Landscape":
		style = "<style>@page{size:A5 landscape;margin:0}</style>"
		options = {
			"page-size": "A5",
			"orientation": "Landscape",
			"margin-top": "0mm",
			"margin-bottom": "0mm",
			"margin-left": "0mm",
			"margin-right": "0mm",
			"encoding": "utf-8",
		}
	else:  # Portrait
		style = "<style>@page{size:A5 portrait;margin:0}</style>"
		options = {
			"page-size": "A5",
			"orientation": "Portrait",
			"margin-top": "0mm",
			"margin-bottom": "0mm",
			"margin-left": "0mm",
			"margin-right": "0mm",
			"encoding": "utf-8",
		}

	html = _inject_style(html, style)
	return html, options, orientation


def _custom_pdf_margins(doc):
	"""Extract margin settings from a PrintTemplate doc, falling back to 0mm."""
	return {
		"top":    getattr(doc, "custom_pdf_margin_top", None)    or "0mm",
		"bottom": getattr(doc, "custom_pdf_margin_bottom", None) or "0mm",
		"left":   getattr(doc, "custom_pdf_margin_left", None)   or "0mm",
		"right":  getattr(doc, "custom_pdf_margin_right", None)  or "0mm",
	}


def _get_context(template_doc, document_name=None):
	"""Return the Jinja context for the template based on its source_type."""
	if getattr(template_doc, "source_type", "DocType") == "Report":
		if not template_doc.report_name:
			frappe.throw("Report is required when Source Type is 'Report'.")
		return build_report_context(template_doc.report_name)
	return build_context(template_doc, document_name)


class PrintTemplate(Document):
	@frappe.whitelist()
	def preview(self, document_name=None):
		"""Return rendered text for quick inspection."""
		is_report = getattr(self, "source_type", "DocType") == "Report"
		ctx = _get_context(self, document_name)
		if self.format_type == "Thermal":
			return frappe.render_template(self.template_content or "", ctx)
		elif self.format_type == "Barcode":
			return frappe.render_template(self.barcode_template or "", ctx)
		elif self.format_type == "PDF":
			if is_report:
				frappe.throw("PDF format (Print Format) is not supported for Report source type. Use Custom PDF or HTML instead.")
			if not document_name:
				frappe.throw("Document Name is required for PDF preview.")
			return frappe.get_print(
				self.document_type, document_name, self.print_format, letterhead=self.letter_head
			)
		elif self.format_type == "Custom PDF":
			return frappe.render_template(self.custom_pdf_template or "", ctx)
		elif self.format_type == "HTML":
			return frappe.render_template(self.template_content or "", ctx)

	@frappe.whitelist()
	def preview_pdf(self, document_name=None):
		"""Return base64-encoded PDF for browser preview."""
		import base64

		from frappe.utils.pdf import get_pdf

		is_report = getattr(self, "source_type", "DocType") == "Report"

		if self.format_type == "PDF":
			if is_report:
				frappe.throw("PDF format (Print Format) is not supported for Report source type. Use Custom PDF or HTML instead.")
			if not document_name:
				frappe.throw("Document Name is required for PDF preview.")
			html = frappe.get_print(
				self.document_type, document_name, self.print_format, letterhead=self.letter_head
			)
			return base64.b64encode(get_pdf(html)).decode()

		elif self.format_type == "Thermal":
			ctx = _get_context(self, document_name)
			rendered = frappe.render_template(self.template_content or "", ctx)
			html = render_to_html(rendered, self.paper_width or "80mm")
			return base64.b64encode(get_pdf(html)).decode()

		elif self.format_type == "Barcode":
			import html as html_module

			ctx = _get_context(self, document_name)
			zpl = frappe.render_template(self.barcode_template or "", ctx)
			preview_html = f"""<html><head><meta charset='utf-8'>
<style>body{{font-family:monospace;font-size:12px;padding:16px}}
pre{{background:#f5f5f5;padding:12px;border:1px solid #ddd;white-space:pre-wrap}}</style>
</head><body>
<p style='color:#888;margin-bottom:8px'>ZPL Output — {self.label_width_mm or 50}mm × {self.label_height_mm or 30}mm</p>
<pre>{html_module.escape(zpl)}</pre>
</body></html>"""
			return base64.b64encode(get_pdf(preview_html)).decode()

		elif self.format_type == "Custom PDF":
			ctx = _get_context(self, document_name)
			html = frappe.render_template(self.custom_pdf_template or "", ctx)
			if self.custom_pdf_letter_head:
				lh = frappe.get_doc("Letter Head", self.custom_pdf_letter_head)
				html = f"<div>{lh.content}</div>{html}"
			html, options, a5_orient = _build_custom_pdf(
				html, self.custom_pdf_page_size or "A4", self.custom_pdf_orientation or "Portrait",
				margins=_custom_pdf_margins(self),
			)
			pdf_bytes = get_pdf(html, options=options)
			if a5_orient:
				pdf_bytes = _place_a5_on_a4(pdf_bytes, a5_orient)
			return base64.b64encode(pdf_bytes).decode()

		elif self.format_type == "HTML":
			ctx = _get_context(self, document_name)
			html = frappe.render_template(self.template_content or "", ctx)
			return base64.b64encode(get_pdf(html)).decode()

	@frappe.whitelist()
	def print_doc(self, printer, document_name=None, copies=1):
		"""Render and send to the given Printer via CUPS."""
		from printer_server_configuration.printer_server_configuration.utils.cups_utils import (
			send_pdf_to_cups,
			send_raw_to_cups,
		)

		printer_doc = frappe.get_doc("Printer", printer)
		server_doc = frappe.get_doc("Printer Server", printer_doc.printer_server)
		copies = int(copies or 1)
		is_report = getattr(self, "source_type", "DocType") == "Report"
		job_label = (self.report_name if is_report else document_name) or self.template_name

		if self.format_type == "Thermal":
			ctx = _get_context(self, document_name)
			raw_bytes = render_to_escpos(self, ctx)
			job_id = send_raw_to_cups(
				server_doc, printer_doc.cups_printer_name, raw_bytes, self.template_name
			)
			return {"success": True, "cups_job_id": job_id}

		elif self.format_type == "PDF":
			from frappe.utils.pdf import get_pdf

			if is_report:
				frappe.throw("PDF format (Print Format) is not supported for Report source type. Use Custom PDF or HTML instead.")
			if not document_name:
				frappe.throw("Document Name is required for PDF printing.")
			html = frappe.get_print(
				self.document_type, document_name, self.print_format, letterhead=self.letter_head
			)
			pdf_bytes = get_pdf(html)
			job_id = None
			for _ in range(copies):
				job_id = send_pdf_to_cups(
					server_doc, printer_doc.cups_printer_name, pdf_bytes, job_label
				)
			return {"success": True, "cups_job_id": job_id}

		elif self.format_type == "Barcode":
			ctx = _get_context(self, document_name)
			zpl = frappe.render_template(self.barcode_template or "", ctx)
			raw_bytes = zpl.encode("utf-8")
			total = copies * int(self.copies_per_doc or 1)
			job_id = None
			for _ in range(total):
				job_id = send_raw_to_cups(
					server_doc, printer_doc.cups_printer_name, raw_bytes, self.template_name
				)
			return {"success": True, "cups_job_id": job_id, "copies_sent": total}

		elif self.format_type == "Custom PDF":
			from frappe.utils.pdf import get_pdf

			ctx = _get_context(self, document_name)
			html = frappe.render_template(self.custom_pdf_template or "", ctx)
			if self.custom_pdf_letter_head:
				lh = frappe.get_doc("Letter Head", self.custom_pdf_letter_head)
				html = f"<div>{lh.content}</div>{html}"
			html, options, a5_orient = _build_custom_pdf(
				html, self.custom_pdf_page_size or "A4", self.custom_pdf_orientation or "Portrait",
				margins=_custom_pdf_margins(self),
			)
			pdf_bytes = get_pdf(html, options=options)
			if a5_orient:
				pdf_bytes = _place_a5_on_a4(pdf_bytes, a5_orient)
			job_id = None
			for _ in range(copies):
				job_id = send_pdf_to_cups(
					server_doc, printer_doc.cups_printer_name, pdf_bytes, job_label,
					print_speed=getattr(self, "custom_pdf_print_speed", None),
					paper_type=getattr(self, "custom_pdf_paper_type", None),
				)
			return {"success": True, "cups_job_id": job_id}

		elif self.format_type == "HTML":
			from frappe.utils.pdf import get_pdf

			ctx = _get_context(self, document_name)
			html = frappe.render_template(self.template_content or "", ctx)
			pdf_bytes = get_pdf(html)
			job_id = None
			for _ in range(copies):
				job_id = send_pdf_to_cups(
					server_doc, printer_doc.cups_printer_name, pdf_bytes, job_label
				)
			return {"success": True, "cups_job_id": job_id}

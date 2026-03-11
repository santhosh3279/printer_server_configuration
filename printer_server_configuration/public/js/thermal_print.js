/**
 * Print button — injected into all document forms.
 * Shows a dialog to pick a printer + Print Template, then sends
 * the document to CUPS (Thermal ESC/POS, PDF, or Barcode ZPL).
 */

frappe.provide("printer_server_configuration");

// Cache: doctype → template count (false = none, positive = has templates)
printer_server_configuration._template_cache = {};

// ----------------------------------------------------------------
// Inject into every form refresh
// ----------------------------------------------------------------
const _orig_refresh = frappe.ui.form.Form.prototype.refresh;

frappe.ui.form.Form.prototype.refresh = function () {
	_orig_refresh.apply(this, arguments);

	const frm = this;
	if (frm.is_new() || !frm.docname) return;

	const cached = printer_server_configuration._template_cache[frm.doctype];
	if (cached === false) return;
	if (cached > 0) {
		_add_print_button(frm);
		return;
	}

	// First visit for this doctype — query Print Template count
	frappe
		.xcall("frappe.client.get_count", {
			doctype: "Print Template",
			filters: { document_type: frm.doctype },
		})
		.then((count) => {
			printer_server_configuration._template_cache[frm.doctype] = count || false;
			if (count > 0) _add_print_button(frm);
		})
		.catch(() => {});
};

// ----------------------------------------------------------------
// Button
// ----------------------------------------------------------------
function _add_print_button(frm) {
	if (frm.custom_buttons[__(\"Print\")]) return;
	frm.add_custom_button(__(\"Print\"), () => {
		printer_server_configuration.show_print_dialog(frm);
	}).addClass("btn-primary");
}

// ----------------------------------------------------------------
// Print dialog
// ----------------------------------------------------------------
printer_server_configuration.show_print_dialog = function (frm) {
	const _badge = { Thermal: "🖨", PDF: "📄", Barcode: "▦" };

	Promise.all([
		frappe.xcall("frappe.client.get_list", {
			doctype: "Print Template",
			filters: { document_type: frm.doctype },
			fields: ["name", "format_type"],
			limit: 100,
		}),
		frappe.xcall("printer_server_configuration.printer_server_configuration.api.get_printers"),
	])
		.then(([template_list, printers]) => {
			const templates = (template_list || []).map((t) => ({
				value: t.name,
				label: `${t.name}  [${_badge[t.format_type] || ""}${t.format_type}]`,
			}));

			if (!templates.length) {
				frappe.msgprint(__("No Print Templates found for {0}.", [frm.doctype]));
				return;
			}
			if (!printers || !printers.length) {
				frappe.msgprint(__("No printers configured. Please add a Printer first."));
				return;
			}

			const default_printer = (printers.find((p) => p.is_default) || printers[0]).name;

			const dialog = new frappe.ui.Dialog({
				title: __("Print"),
				fields: [
					{
						fieldtype: "Select",
						fieldname: "template",
						label: __("Template"),
						options: templates,
						default: templates[0].value,
						reqd: 1,
					},
					{
						fieldtype: "Select",
						fieldname: "printer",
						label: __("Printer"),
						options: printers.map((p) => ({
							value: p.name,
							label: `${p.printer_name} (${p.status})`,
						})),
						default: default_printer,
						reqd: 1,
					},
					{
						fieldtype: "Int",
						fieldname: "copies",
						label: __("Copies"),
						default: 1,
					},
				],
				primary_action_label: __("Print"),
				primary_action(values) {
					dialog.disable_primary_action();
					frappe
						.xcall(
							"printer_server_configuration.printer_server_configuration.api.print_document",
							{
								printer: values.printer,
								print_template: values.template,
								document_type: frm.doctype,
								document_name: frm.docname,
								copies: values.copies || 1,
								title: frm.docname,
							},
						)
						.then(() => {
							frappe.show_alert({ message: __("Sent to printer"), indicator: "green" }, 5);
							dialog.hide();
						})
						.catch(() => {
							dialog.enable_primary_action();
						});
				},
			});

			dialog.show();
		})
		.catch(() => {
			frappe.msgprint(__("Failed to load templates. Check console for errors."));
		});
};

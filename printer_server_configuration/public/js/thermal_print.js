/**
 * Thermal Print button — injected into all document forms.
 * Shows a dialog to pick a printer + template (Thermal Print Template
 * or Thermal Layout Template), then sends the document to CUPS/ESC-POS.
 */

frappe.provide("printer_server_configuration");

// Cache of doctype → total template count (both types combined)
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
		_add_thermal_button(frm);
		return;
	}

	// First visit for this doctype — query both template types
	Promise.all([
		frappe.xcall("frappe.client.get_count", {
			doctype: "Thermal Print Template",
			filters: { document_type: frm.doctype },
		}),
		frappe.xcall("frappe.client.get_count", {
			doctype: "Thermal Layout Template",
			filters: { document_type: frm.doctype },
		}),
	]).then(([c1, c2]) => {
		const count = (c1 || 0) + (c2 || 0);
		printer_server_configuration._template_cache[frm.doctype] = count || false;
		if (count > 0) _add_thermal_button(frm);
	}).catch(() => {});
};

// ----------------------------------------------------------------
// Button
// ----------------------------------------------------------------
function _add_thermal_button(frm) {
	if (frm.custom_buttons[__("Thermal Print")]) return;
	frm.add_custom_button(__("Thermal Print"), () => {
		printer_server_configuration.show_thermal_dialog(frm);
	}).addClass("btn-primary");
}

// ----------------------------------------------------------------
// Print dialog
// ----------------------------------------------------------------
printer_server_configuration.show_thermal_dialog = function (frm) {
	Promise.all([
		frappe.xcall("frappe.client.get_list", {
			doctype: "Thermal Print Template",
			filters: { document_type: frm.doctype },
			fields: ["name"],
			limit: 100,
		}),
		frappe.xcall("frappe.client.get_list", {
			doctype: "Thermal Layout Template",
			filters: { document_type: frm.doctype },
			fields: ["name"],
			limit: 100,
		}),
		frappe.xcall("printer_server_configuration.printer_server_configuration.api.get_printers"),
	]).then(([thermal_list, layout_list, printers]) => {
		// Encode type into value so we know which API to call
		const templates = [
			...(thermal_list || []).map((t) => ({
				value: `thermal::${t.name}`,
				label: t.name,
			})),
			...(layout_list || []).map((t) => ({
				value: `layout::${t.name}`,
				label: `${t.name}  [Layout]`,
			})),
		];

		if (!templates.length) {
			frappe.msgprint(__("No Thermal Print Templates found for {0}.", [frm.doctype]));
			return;
		}
		if (!printers || !printers.length) {
			frappe.msgprint(__("No printers configured. Please add a Printer first."));
			return;
		}

		const default_printer = (printers.find((p) => p.is_default) || printers[0]).name;

		const dialog = new frappe.ui.Dialog({
			title: __("Thermal Print"),
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

				const sep = values.template.indexOf("::");
				const type = values.template.slice(0, sep);
				const template_name = values.template.slice(sep + 2);
				const is_layout = type === "layout";

				frappe.xcall(
					is_layout
						? "printer_server_configuration.printer_server_configuration.api.print_layout"
						: "printer_server_configuration.printer_server_configuration.api.print_thermal",
					{
						printer: values.printer,
						[is_layout ? "layout_template" : "thermal_template"]: template_name,
						document_type: frm.doctype,
						document_name: frm.docname,
						title: frm.docname,
					},
				).then(() => {
					frappe.show_alert({ message: __("Sent to printer"), indicator: "green" }, 5);
					dialog.hide();
				}).catch(() => {
					dialog.enable_primary_action();
				});
			},
		});

		dialog.show();
	}).catch(() => {
		frappe.msgprint(__("Failed to load templates. Check console for errors."));
	});
};

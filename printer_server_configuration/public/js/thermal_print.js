/**
 * Thermal Print button — injected into all document forms.
 * Shows a dialog to pick a printer and template, then sends
 * the document to the thermal printer via CUPS/ESC-POS.
 */

frappe.provide("printer_server_configuration");

// Cache of doctype -> template count so we don't call the server on every refresh
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

	if (cached === false) return; // known: no templates for this doctype

	if (cached > 0) {
		_add_thermal_button(frm);
		return;
	}

	// First time for this doctype — ask the server
	frappe.call({
		method: "frappe.client.get_count",
		args: { doctype: "Thermal Print Template", filters: { document_type: frm.doctype } },
		callback(r) {
			const count = r.message || 0;
			printer_server_configuration._template_cache[frm.doctype] = count;
			if (count > 0) _add_thermal_button(frm);
		},
	});
};

// ----------------------------------------------------------------
// Add the button to the form toolbar
// ----------------------------------------------------------------
function _add_thermal_button(frm) {
	// Avoid duplicates on repeated refreshes
	if (frm.custom_buttons[__("Thermal Print")]) return;

	frm.add_custom_button(__("Thermal Print"), () => {
		printer_server_configuration.show_thermal_dialog(frm);
	}).addClass("btn-primary");
}

// ----------------------------------------------------------------
// Print dialog
// ----------------------------------------------------------------
printer_server_configuration.show_thermal_dialog = function (frm) {
	// Load templates and printers in parallel
	Promise.all([
		frappe.call({
			method: "frappe.client.get_list",
			args: {
				doctype: "Thermal Print Template",
				filters: { document_type: frm.doctype },
				fields: ["name"],
				limit: 100,
			},
		}),
		frappe.call({
			method: "printer_server_configuration.printer_server_configuration.api.get_printers",
		}),
	]).then(([tpl_res, prn_res]) => {
		const templates = (tpl_res.message || []).map((t) => t.name);
		const printers = prn_res.message || [];

		if (!templates.length) {
			frappe.msgprint(__("No Thermal Print Templates found for {0}.", [frm.doctype]));
			return;
		}
		if (!printers.length) {
			frappe.msgprint(__("No printers configured. Please add a Printer first."));
			return;
		}

		const default_printer = (printers.find((p) => p.is_default) || printers[0]).name;

		const dialog = new frappe.ui.Dialog({
			title: __("Thermal Print"),
			fields: [
				{
					fieldtype: "Select",
					fieldname: "thermal_template",
					label: __("Template"),
					options: templates,
					default: templates[0],
					reqd: 1,
				},
				{
					fieldtype: "Select",
					fieldname: "printer",
					label: __("Printer"),
					options: printers.map((p) => ({ value: p.name, label: `${p.printer_name} (${p.status})` })),
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
				frappe.call({
					method: "printer_server_configuration.printer_server_configuration.api.print_thermal",
					args: {
						printer: values.printer,
						thermal_template: values.thermal_template,
						document_type: frm.doctype,
						document_name: frm.docname,
						title: frm.docname,
					},
					callback(r) {
						if (r.message && r.message.success) {
							frappe.show_alert(
								{
									message: __("Sent to printer — Job {0}", [r.message.job]),
									indicator: "green",
								},
								5
							);
							dialog.hide();
						}
					},
					error() {
						dialog.enable_primary_action();
					},
				});
			},
		});

		dialog.show();
	});
};

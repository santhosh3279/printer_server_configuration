// Copyright (c) 2026, Santhosh and contributors
// For license information, please see license.txt

frappe.ui.form.on("Barcode_Prinitng", {
	refresh(frm) {
		if (frm.is_new()) return;
		// Redirect the standard ERPNext print button to our custom barcode dialog
		frm.print_doc = function () {
			printer_server_configuration.show_print_dialog(frm);
		};
	}
});

frappe.ui.form.on("Barcode_subwindow", {
	item_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item_code) return;

		frappe.db.get_value("Item", row.item_code, ["item_name", "valuation_rate"], (r) => {
			if (r) {
				frappe.model.set_value(cdt, cdn, "item_name", r.item_name || "");
				frappe.model.set_value(cdt, cdn, "valuation_rate", r.valuation_rate || 0);
			}
		});

		if (frm.doc.price_list) {
			frappe.db.get_value(
				"Item Price",
				{ item_code: row.item_code, price_list: frm.doc.price_list },
				"price_list_rate",
				(r) => {
					if (r && r.price_list_rate) {
						frappe.model.set_value(cdt, cdn, "rate", r.price_list_rate);
					}
				}
			);
		}
	}
});

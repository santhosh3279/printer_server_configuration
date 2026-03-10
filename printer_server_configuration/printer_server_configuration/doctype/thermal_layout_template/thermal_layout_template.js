frappe.ui.form.on("Thermal Layout Template", {
	refresh(frm) {
		frm.add_custom_button(__("Preview PDF"), () => {
			_ask_doc_name(frm, (doc_name) => _open_pdf(frm, doc_name));
		});

		frm.add_custom_button(__("Print Test"), () => {
			_pick_printer(frm, (printer) => {
				_ask_doc_name(frm, (doc_name) => _print_test(frm, printer, doc_name));
			});
		});
	},
});

function _ask_doc_name(frm, cb) {
	if (frm.doc.document_type) {
		frappe.prompt(
			{
				label: __("Document Name"),
				fieldname: "document_name",
				fieldtype: "Dynamic Link",
				options: "document_type",
			},
			({ document_name }) => cb(document_name || null),
			__("Select Document"),
			__("Continue"),
		);
	} else {
		cb(null);
	}
}

function _pick_printer(frm, cb) {
	frappe.call({
		method: "printer_server_configuration.printer_server_configuration.api.get_printers",
		callback(r) {
			const printers = (r.message || []).map((p) => ({ label: p.printer_name, value: p.name }));
			if (!printers.length) {
				frappe.msgprint(__("No printers configured."));
				return;
			}
			frappe.prompt(
				{ label: __("Printer"), fieldname: "printer", fieldtype: "Select", options: printers },
				({ printer }) => cb(printer),
				__("Select Printer"),
				__("Print"),
			);
		},
	});
}

function _open_pdf(frm, document_name) {
	frappe.call({
		method: "preview_pdf",
		doc: frm.doc,
		args: { document_name },
		freeze: true,
		freeze_message: __("Generating PDF…"),
		callback(r) {
			if (!r.message) return;
			const bytes = atob(r.message);
			const buf = new Uint8Array(bytes.length);
			for (let i = 0; i < bytes.length; i++) buf[i] = bytes.charCodeAt(i);
			window.open(URL.createObjectURL(new Blob([buf], { type: "application/pdf" })), "_blank");
		},
	});
}

function _print_test(frm, printer, document_name) {
	frappe.call({
		method: "print_test",
		doc: frm.doc,
		args: { printer, document_name },
		freeze: true,
		freeze_message: __("Sending to printer…"),
		callback(r) {
			if (r.message?.success) {
				frappe.show_alert({ message: __("Sent to printer"), indicator: "green" });
			}
		},
	});
}

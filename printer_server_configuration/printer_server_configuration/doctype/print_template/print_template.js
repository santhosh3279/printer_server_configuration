frappe.ui.form.on("Print Template", {
	refresh(frm) {
		// Filter Print Format by selected Document Type
		frm.set_query("print_format", () => ({
			filters: { doc_type: frm.doc.document_type || "" },
		}));

		frm.add_custom_button(__("Preview PDF"), () => {
			_ask_doc_name(frm, (doc_name) => _open_pdf(frm, doc_name));
		});

		frm.add_custom_button(__("Print Test"), () => {
			_pick_printer_and_doc(frm, (printer, doc_name, copies) => {
				_print_doc(frm, printer, doc_name, copies);
			});
		});
	},

	format_type(frm) {
		// Clear irrelevant fields when format changes
		frm.refresh();
	},
});

// ---------------------------------------------------------------

function _ask_doc_name(frm, cb) {
	if (frm.doc.document_type) {
		frappe.prompt(
			{
				label: __("Document Name"),
				fieldname: "document_name",
				fieldtype: "Link",
				options: frm.doc.document_type,
				reqd: frm.doc.format_type === "PDF" ? 1 : 0,
			},
			({ document_name }) => cb(document_name || null),
			__("Select Document"),
			__("Continue"),
		);
	} else {
		cb(null);
	}
}

function _pick_printer_and_doc(frm, cb) {
	frappe.xcall("printer_server_configuration.printer_server_configuration.api.get_printers").then(
		(printers) => {
			if (!printers || !printers.length) {
				frappe.msgprint(__("No printers configured."));
				return;
			}
			const default_printer = (printers.find((p) => p.is_default) || printers[0]).name;

			const fields = [
				{
					label: __("Printer"),
					fieldname: "printer",
					fieldtype: "Select",
					options: printers.map((p) => ({
						value: p.name,
						label: `${p.printer_name} (${p.status})`,
					})),
					default: default_printer,
					reqd: 1,
				},
			];

			if (frm.doc.document_type) {
				fields.push({
					label: __("Document Name"),
					fieldname: "document_name",
					fieldtype: "Link",
					options: frm.doc.document_type,
					reqd: frm.doc.format_type === "PDF" ? 1 : 0,
				});
			}

			if (frm.doc.format_type === "PDF") {
				fields.push({
					label: __("Copies"),
					fieldname: "copies",
					fieldtype: "Int",
					default: 1,
				});
			}

			frappe.prompt(
				fields,
				(values) => cb(values.printer, values.document_name || null, values.copies || 1),
				__("Print"),
				__("Send to Printer"),
			);
		},
	);
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
			const url = URL.createObjectURL(new Blob([buf], { type: "application/pdf" }));
			const a = document.createElement("a");
			a.href = url;
			a.target = "_blank";
			a.rel = "noopener";
			document.body.appendChild(a);
			a.click();
			document.body.removeChild(a);
			setTimeout(() => URL.revokeObjectURL(url), 1000);
		},
	});
}

function _print_doc(frm, printer, document_name, copies) {
	frappe.call({
		method: "print_doc",
		doc: frm.doc,
		args: { printer, document_name, copies },
		freeze: true,
		freeze_message: __("Sending to printer…"),
		callback(r) {
			if (r.message?.success) {
				const info = r.message.copies_sent ? ` (${r.message.copies_sent} labels)` : "";
				frappe.show_alert({ message: __("Sent to printer") + info, indicator: "green" }, 5);
			}
		},
	});
}

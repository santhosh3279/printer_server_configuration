frappe.ui.form.on("Thermal Print Template", {
	refresh(frm) {
		frm.add_custom_button(__("Preview PDF"), () => {
			if (frm.doc.document_type) {
				frappe.prompt(
					{
						label: __("Document Name"),
						fieldname: "document_name",
						fieldtype: "Dynamic Link",
						options: "document_type",
					},
					({ document_name }) => _open_pdf_preview(frm, document_name),
					__("Preview PDF"),
					__("Preview"),
				);
			} else {
				_open_pdf_preview(frm, null);
			}
		});
	},
});

function _open_pdf_preview(frm, document_name) {
	frappe.call({
		method: "preview_pdf",
		doc: frm.doc,
		args: { document_name: document_name || null },
		freeze: true,
		freeze_message: __("Generating PDF…"),
		callback(r) {
			if (!r.message) return;
			const bytes = atob(r.message);
			const buf = new Uint8Array(bytes.length);
			for (let i = 0; i < bytes.length; i++) buf[i] = bytes.charCodeAt(i);
			const blob = new Blob([buf], { type: "application/pdf" });
			const url = URL.createObjectURL(blob);
			window.open(url, "_blank");
		},
	});
}

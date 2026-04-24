import frappe
from frappe.utils import now_datetime

class LogMixin:
    def log_processing(self, pdf_file: str | None, step: str, status: str, error: str | None = None):
        doc = frappe.get_doc({
            "doctype": "UPSC Processing Log",
            "pdf_file": pdf_file,
            "step": step,
            "status": status,
            "error": error,
            "timestamp": now_datetime()
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()

    def get_processing_status(self) -> dict:
        status = {}
        status["total_pdfs"] = self.get_pdf_count()
        status["total_pages"] = frappe.db.count("UPSC Page")
        status["classified_pages"] = frappe.db.sql("SELECT count(name) FROM `tabUPSC Page` WHERE classification IS NOT NULL AND classification != ''")[0][0]
        status["transcribed_pages"] = frappe.db.sql("SELECT count(name) FROM `tabUPSC Page` WHERE transcription IS NOT NULL AND transcription != ''")[0][0]
        status["total_answers"] = frappe.db.count("UPSC Answer")
        
        dim_rows = frappe.db.sql("SELECT dimension_name, COUNT(*) as cnt FROM `tabUPSC Answer Dimension` GROUP BY dimension_name", as_dict=True)
        status["dimensions"] = {r["dimension_name"]: r["cnt"] for r in dim_rows}

        agg_rows = frappe.db.sql("SELECT dimension_name, answer_count FROM `tabUPSC Dimension Aggregation`", as_dict=True)
        status["aggregations"] = {r["dimension_name"]: r["answer_count"] for r in agg_rows}

        err_rows = frappe.db.sql("SELECT step, COUNT(*) as cnt FROM `tabUPSC Processing Log` WHERE status = 'error' GROUP BY step", as_dict=True)
        status["errors"] = {r["step"]: r["cnt"] for r in err_rows}

        return status

    def reset_from_step(self, step_number: int):
        if step_number <= 6: frappe.db.sql("DELETE FROM `tabUPSC Dimension Aggregation`")
        if step_number <= 5: frappe.db.sql("DELETE FROM `tabUPSC Answer Dimension`")
        if step_number <= 4: frappe.db.sql("DELETE FROM `tabUPSC Answer`")
        if step_number <= 3: frappe.db.sql("UPDATE `tabUPSC Page` SET classification = NULL")
        if step_number <= 2: frappe.db.sql("UPDATE `tabUPSC Page` SET transcription = NULL, processed = 0")
        if step_number <= 1: frappe.db.sql("DELETE FROM `tabUPSC Page`")
        
        self.log_processing(None, f"reset_from_{step_number}", "done")
        frappe.db.commit()

    def delete_pdf_data(self, pdf_file: str):
        frappe.db.sql("DELETE FROM `tabUPSC Answer Dimension` WHERE answer IN (SELECT name FROM `tabUPSC Answer` WHERE pdf_file = %s)", (pdf_file,))
        frappe.db.sql("DELETE FROM `tabUPSC Answer` WHERE pdf_file = %s", (pdf_file,))
        frappe.db.sql("DELETE FROM `tabUPSC Page` WHERE pdf_file = %s", (pdf_file,))
        frappe.db.sql("DELETE FROM `tabUPSC Processing Log` WHERE pdf_file = %s", (pdf_file,))
        frappe.db.commit()

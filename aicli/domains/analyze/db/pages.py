import frappe

class PageMixin:
    """Operations related to the 'UPSC Page' DocType."""
    
    def insert_page(self, pdf_file: str, page_number: int, image_path: str) -> str:
        existing = frappe.get_all("UPSC Page", filters={"pdf_file": pdf_file, "page_number": page_number}, limit=1)
        if existing:
            return existing[0].name
        
        doc = frappe.get_doc({
            "doctype": "UPSC Page",
            "pdf_file": pdf_file,
            "page_number": page_number,
            "image_path": image_path,
            "processed": 0
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc.name

    def get_pages_for_pdf(self, pdf_file: str) -> list[dict]:
        rows = frappe.get_all("UPSC Page", filters={"pdf_file": pdf_file}, fields=["*"], order_by="page_number asc")
        for r in rows: r["id"] = r["name"]
        return rows

    def get_unclassified_pages(self) -> list[dict]:
        rows = frappe.get_all("UPSC Page", filters={"classification": ["in", ["", None]]}, fields=["*"], order_by="pdf_file asc, page_number asc")
        for r in rows: r["id"] = r["name"]
        return rows

    def update_classification(self, page_id: str, classification: str):
        frappe.db.set_value("UPSC Page", page_id, "classification", classification)
        frappe.db.commit()

    def get_untranscribed_pages(self) -> list[dict]:
        pages = frappe.get_all("UPSC Page", filters={"transcription": ["in", ["", None]]}, fields=["*"], order_by="pdf_file asc, page_number asc")
        pages += frappe.get_all("UPSC Page", filters={"transcription": ["like", "[TRANSCRIPTION_ERROR%"]}, fields=["*"], order_by="pdf_file asc, page_number asc")
        for r in pages: r["id"] = r["name"]
        return pages

    def update_transcription(self, page_id: str, transcription: str):
        frappe.db.set_value("UPSC Page", page_id, {
            "transcription": transcription,
            "processed": 1
        })
        frappe.db.commit()

    def get_page(self, page_id: str) -> dict | None:
        if frappe.db.exists("UPSC Page", page_id):
            row = frappe.get_doc("UPSC Page", page_id).as_dict()
            row["id"] = row["name"]
            return row
        return None

    def get_pdf_count(self) -> int:
        return len(self.get_all_pdfs())

    def get_all_pdfs(self) -> list[str]:
        pdfs = frappe.db.sql("SELECT DISTINCT pdf_file FROM `tabUPSC Page` ORDER BY pdf_file", as_dict=True)
        return [p.pdf_file for p in pdfs]

    def get_pdf_progress(self, pdf_file: str) -> dict:
        progress = {}
        pages = frappe.get_all("UPSC Page", filters={"pdf_file": pdf_file}, fields=["name", "transcription", "classification"])
        page_count = len(pages)
        
        progress["1"] = "done" if page_count > 0 else "pending"
        if page_count == 0:
            for s in ["2", "3", "4", "5"]: progress[s] = "pending"
            return progress
            
        ocr_count = sum(1 for p in pages if p.transcription)
        if ocr_count == page_count: progress["2"] = "done"
        elif ocr_count > 0: progress["2"] = "partial"
        else: progress["2"] = "pending"
        
        cls_count = sum(1 for p in pages if p.classification)
        if cls_count == page_count: progress["3"] = "done"
        elif cls_count > 0: progress["3"] = "partial"
        else: progress["3"] = "pending"
        
        answers = frappe.get_all("UPSC Answer", filters={"pdf_file": pdf_file}, fields=["name"])
        ans_count = len(answers)
        progress["4"] = "done" if ans_count > 0 else "pending"
        
        if ans_count > 0:
            analyzed = frappe.db.sql('''
                SELECT COUNT(DISTINCT answer) as cnt FROM `tabUPSC Answer Dimension`
                WHERE answer IN (SELECT name FROM `tabUPSC Answer` WHERE pdf_file = %s)
            ''', (pdf_file,), as_dict=True)[0].cnt
            if analyzed == ans_count: progress["5"] = "done"
            elif analyzed > 0: progress["5"] = "partial"
            else: progress["5"] = "pending"
        else:
            progress["5"] = "pending"
            
        return progress

import json
import frappe

class AnswerMixin:
    """Operations related to the 'UPSC Answer' DocType."""
    def get_unsegmented_pdfs(self) -> list[str]:
        pages = frappe.get_all("UPSC Page", filters={"classification": ["in", ["answer", "continuation"]], "transcription": ["is", "set"]}, fields=["pdf_file"])
        pdf_files = list(set([p.pdf_file for p in pages]))
        
        answers = frappe.get_all("UPSC Answer", fields=["pdf_file"])
        answered_pdfs = set([a.pdf_file for a in answers])
        
        return sorted(list(set(pdf_files) - answered_pdfs))

    def insert_answer(
        self,
        pdf_file: str,
        candidate_name: str | None,
        upsc_id: str | None,
        test_code: str | None,
        question_number: str | None,
        question_text: str | None,
        question_directive: str | None,
        word_limit: int | None,
        raw_text: str,
        page_ids: list[int],
    ) -> str:
        doc = frappe.get_doc({
            "doctype": "UPSC Answer",
            "pdf_file": pdf_file,
            "candidate_name": candidate_name,
            "upsc_id": upsc_id,
            "test_code": test_code,
            "question_number": question_number,
            "question_text": question_text,
            "question_directive": question_directive,
            "word_limit": word_limit,
            "raw_text": raw_text,
            "page_ids": json.dumps(page_ids),
            "segmentation_done": 1
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc.name

    def get_all_answers(self) -> list[dict]:
        rows = frappe.get_all("UPSC Answer", fields=["*"], order_by="pdf_file asc, question_number asc")
        for r in rows: r["id"] = r["name"]
        return rows

    def get_answer_by_id(self, answer_id: str) -> dict | None:
        if frappe.db.exists("UPSC Answer", answer_id):
            row = frappe.get_doc("UPSC Answer", answer_id).as_dict()
            row["id"] = row["name"]
            return row
        return None

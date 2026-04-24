import frappe
from frappe.utils import now_datetime

class DimensionMixin:
    def get_unanalyzed_answers(self, dimension_name: str) -> list[dict]:
        answers = frappe.get_all("UPSC Answer", fields=["*"], order_by="pdf_file asc, question_number asc")
        analyzed_answers = frappe.get_all("UPSC Answer Dimension", 
            filters={"dimension_name": dimension_name, "result_json": ["not like", '%"error":%']}, 
            fields=["answer"])
        analyzed_ids = set([d.answer for d in analyzed_answers])
        
        filtered = []
        for a in answers:
            a["id"] = a["name"]
            if a["name"] not in analyzed_ids:
                filtered.append(a)
        return filtered

    def insert_dimension_result(self, answer_id: str, dimension_name: str, result_json: str):
        existing = frappe.get_all("UPSC Answer Dimension", filters={"answer": answer_id, "dimension_name": dimension_name}, limit=1)
        if existing:
            frappe.db.set_value("UPSC Answer Dimension", existing[0].name, {"result_json": result_json, "processed_at": now_datetime()})
        else:
            doc = frappe.get_doc({
                "doctype": "UPSC Answer Dimension",
                "answer": answer_id,
                "dimension_name": dimension_name,
                "result_json": result_json,
                "processed_at": now_datetime()
            })
            doc.insert(ignore_permissions=True)
        frappe.db.commit()

    def get_dimension_results(self, dimension_name: str) -> list[dict]:
        results = frappe.db.sql('''
            SELECT ad.*, a.pdf_file, a.candidate_name, a.question_number,
            a.question_text, a.question_directive
            FROM `tabUPSC Answer Dimension` ad
            JOIN `tabUPSC Answer` a ON ad.answer = a.name
            WHERE ad.dimension_name = %s
            ORDER BY a.pdf_file, a.question_number
        ''', (dimension_name,), as_dict=True)
        for r in results:
            r["id"] = r["name"]
        return results

    def get_dimension_count(self, dimension_name: str) -> int:
        return frappe.db.count("UPSC Answer Dimension", filters={"dimension_name": dimension_name})

    def insert_aggregation(self, dimension_name: str, aggregation_json: str, answer_count: int):
        existing = frappe.get_all("UPSC Dimension Aggregation", filters={"dimension_name": dimension_name}, limit=1)
        if existing:
            frappe.db.set_value("UPSC Dimension Aggregation", existing[0].name, {
                "aggregation_json": aggregation_json,
                "generated_at": now_datetime(),
                "answer_count": answer_count
            })
        else:
            doc = frappe.get_doc({
                "doctype": "UPSC Dimension Aggregation",
                "dimension_name": dimension_name,
                "aggregation_json": aggregation_json,
                "generated_at": now_datetime(),
                "answer_count": answer_count
            })
            doc.insert(ignore_permissions=True)
        frappe.db.commit()

    def get_aggregation(self, dimension_name: str) -> dict | None:
        agg = frappe.get_all("UPSC Dimension Aggregation", filters={"dimension_name": dimension_name}, fields=["*"], limit=1)
        if agg:
            agg[0]["id"] = agg[0]["name"]
            return agg[0]
        return None

    def get_all_aggregations(self) -> list[dict]:
        aggs = frappe.get_all("UPSC Dimension Aggregation", fields=["*"], order_by="dimension_name asc")
        for a in aggs:
            a["id"] = a["name"]
        return aggs

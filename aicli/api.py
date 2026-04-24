import frappe
import json
import os
from aicli.config import config as aicli_config, DATA_DIR
from aicli.server.repositories.analyze_repository import AnalyzeRepository

@frappe.whitelist(allow_guest=True)
def get_csrf_token():
    return frappe.sessions.get_csrf_token()

@frappe.whitelist()
def get_settings():
    doc = frappe.get_single("AICLI Settings")
    return doc.as_dict()

@frappe.whitelist()
def update_settings():
    settings = frappe.request.get_json()
    doc = frappe.get_doc("AICLI Settings")
    for key, value in settings.items():
        if key in doc.as_dict():
            if key == "analyze_step_models" and not isinstance(value, str):
                doc.set(key, json.dumps(value))
            else:
                doc.set(key, value)
    doc.save()
    frappe.db.commit()
    return {"ok": True}

@frappe.whitelist()
def list_models():
    from aicli.providers.lm_studio import LMStudioProvider
    from aicli.providers.ollama import OllamaProvider
    doc = frappe.get_single("AICLI Settings")
    provider_type = doc.provider_type
    if provider_type == "lmstudio":
        return {"models": LMStudioProvider.list_models()}
    elif provider_type == "ollama":
        return {"models": OllamaProvider.list_models()}
    return {"models": []}

@frappe.whitelist()
def get_pdfs():
    repo = AnalyzeRepository()
    pdfs = repo.get_all_pdfs()
    repo.close()
    
    # Return as list of dicts for UI compatibility
    return [{"id": p, "filename": p} for p in pdfs]

@frappe.whitelist()
def get_pipeline_status():
    repo = AnalyzeRepository()
    status = repo.get_processing_status()
    repo.close()
    return status

@frappe.whitelist()
def get_pages(pdf_file):
    repo = AnalyzeRepository()
    pages = repo.get_pages_for_pdf(pdf_file)
    repo.close()
    return pages

@frappe.whitelist()
def get_answers(pdf_file):
    repo = AnalyzeRepository()
    answers = [a for a in repo.get_all_answers() if a.get("pdf_file") == pdf_file]
    repo.close()
    return answers

@frappe.whitelist()
def get_dimensions(answer_id):
    # Fetch dimensions for this answer by looking at UPSC Answer Dimension
    dimensions = frappe.get_all("UPSC Answer Dimension", filters={"answer": answer_id}, fields=["*"])
    for d in dimensions: d["id"] = d["name"]
    return dimensions

@frappe.whitelist()
def get_aggregations():
    repo = AnalyzeRepository()
    aggs = repo.get_all_aggregations()
    repo.close()
    # Frontend expects dict or list. The AnalyzeApiClient maps it nicely.
    return aggs

@frappe.whitelist()
def reset_pipeline(step):
    repo = AnalyzeRepository()
    repo.reset_from_step(int(step))
    repo.close()
    return {"ok": True}

@frappe.whitelist()
def retry_errors():
    # Clear errors in processing log
    frappe.db.sql("DELETE FROM `tabUPSC Processing Log` WHERE status = 'error'")
    frappe.db.commit()
    return {"ok": True}

@frappe.whitelist()
def stop_pipeline():
    # Stub for orchestrator stop
    return {"ok": True}

@frappe.whitelist()
def delete_pdf(pdf_file):
    repo = AnalyzeRepository()
    repo.delete_pdf_data(pdf_file)
    repo.close()
    return {"ok": True}

@frappe.whitelist()
def run_analyze(target_steps=None, workers=2, dpi=150, llm_model=None):
    from aicli.server.services.analyze_pipeline_service import AnalyzePipelineService
    from aicli.server.orchestrator.base import BaseOrchestrator
    
    if not hasattr(frappe.local, "aicli_orch"):
        frappe.local.aicli_orch = BaseOrchestrator()
        
    return {"message": "Pipeline started"}

@frappe.whitelist()
def upload_pdfs():
    # Use Frappe's request.files
    import os
    if "files" not in frappe.request.files:
        return {"error": "No files found"}
        
    files = frappe.request.files.getlist("files")
    
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)
        
    for f in files:
        file_path = os.path.join(DATA_DIR, f.filename)
        f.save(file_path)
        
    return {"ok": True}

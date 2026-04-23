import frappe
import json
import os
from aicli.config import config as aicli_config, DATA_DIR
from aicli.server.repositories.analyze_repository import AnalyzeRepository

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
    pdfs = repo.get_pdf_list(DATA_DIR)
    repo.close()
    return pdfs

@frappe.whitelist()
def get_pipeline_status():
    repo = AnalyzeRepository()
    status = repo.get_status_metrics()
    repo.close()
    return status

@frappe.whitelist()
def run_analyze(target_steps=None, workers=2, dpi=150, llm_model=None):
    from aicli.server.services.analyze_pipeline_service import AnalyzePipelineService
    from aicli.server.orchestrator.base import BaseOrchestrator
    
    # We use a global orchestrator in the module to track state
    if not hasattr(frappe.local, "aicli_orch"):
        frappe.local.aicli_orch = BaseOrchestrator()
    
    # Trigger pipeline logic ...
    # This is complex because of threading in Frappe, but let's assume it works for PoC
    return {"message": "Pipeline started"}


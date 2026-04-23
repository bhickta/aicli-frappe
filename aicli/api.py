import frappe
import json
import os
from aicli.aicli.config import config as aicli_config, save_config, AppConfig

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
    from aicli.aicli.providers.lm_studio import LMStudioProvider
    from aicli.aicli.providers.ollama import OllamaProvider
    doc = frappe.get_single("AICLI Settings")
    provider_type = doc.provider_type
    if provider_type == "lmstudio":
        return {"models": LMStudioProvider.list_models()}
    elif provider_type == "ollama":
        return {"models": OllamaProvider.list_models()}
    return {"models": []}

@frappe.whitelist()
def analyze_pdf(pdf_name):
    # This would call the pipeline
    from aicli.aicli.services.analyze.orchestrator import AnalyzeOrchestrator
    # ... logic to run pipeline ...
    return {"status": "started"}

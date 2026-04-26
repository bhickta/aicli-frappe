import frappe
import json
import os
import logging
from aicli.config import config as aicli_config, DATA_DIR

logger = logging.getLogger(__name__)
from aicli.domains.analyze.database import AnalyzeDB

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
    import requests
    doc = frappe.get_single("AICLI Settings")
    provider_type = doc.provider_type
    try:
        if provider_type in ["lms", "lmstudio"]:
            base_url = doc.get("lms_base_url") or doc.get("lm_studio_base_url") or "http://localhost:1234/v1"
            base_url = base_url.rstrip("/")
            import time
            for attempt in range(5):
                try:
                    res = requests.get(f"{base_url}/models", timeout=5)
                    if res.ok:
                        data = res.json()
                        return {"models": [m["id"] for m in data.get("data", []) if m.get("id")]}
                except requests.exceptions.RequestException as e:
                    if attempt < 4:
                        time.sleep(1)
                    else:
                        frappe.log_error(f"Failed to connect to LM Studio after 5 retries: {e}")
        elif provider_type == "ollama":
            base_url = (doc.ollama_base_url or "http://localhost:11434").rstrip("/")
            res = requests.get(f"{base_url}/api/tags", timeout=5)
            if res.ok:
                data = res.json()
                return {"models": [m["name"] for m in data.get("models", []) if m.get("name")]}
    except Exception as e:
        frappe.log_error(f"Failed to fetch models: {e}")
    return {"models": []}

@frappe.whitelist()
def get_pdfs():
    db = AnalyzeDB()
    pdfs = db.get_all_pdfs()
    return [{"id": p, "filename": p} for p in pdfs]

@frappe.whitelist()
def get_pipeline_status():
    return AnalyzeDB().get_processing_status()

@frappe.whitelist()
def get_pages(pdf_file):
    return AnalyzeDB().get_pages_for_pdf(pdf_file)

@frappe.whitelist()
def get_answers(pdf_file):
    return [a for a in AnalyzeDB().get_all_answers() if a.get("pdf_file") == pdf_file]

@frappe.whitelist()
def get_dimensions(answer_id):
    # Fetch dimensions for this answer by looking at UPSC Answer Dimension
    dimensions = frappe.get_all("UPSC Answer Dimension", filters={"answer": answer_id}, fields=["*"])
    for d in dimensions: d["id"] = d["name"]
    return dimensions

@frappe.whitelist()
def get_aggregations():
    return AnalyzeDB().get_all_aggregations()

@frappe.whitelist()
def reset_pipeline(step):
    AnalyzeDB().reset_from_step(int(step))
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
    AnalyzeDB().delete_pdf_data(pdf_file)
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

# ──────────────────────────────────────────────────────────────────
# OCR Endpoints — thin wrappers delegating to domain layer
# ──────────────────────────────────────────────────────────────────

@frappe.whitelist()
def start_zip_ocr(file_url: str, model_name: str = None, max_workers: int = None):
    """Start OCR job from a Frappe File URL."""
    from aicli.domains.ocr.job_service import OcrJobService
    from aicli.domains.ocr.constants import DEFAULT_MODEL, DEFAULT_MAX_WORKERS, ENQUEUE_TIMEOUT, ENQUEUE_QUEUE

    if not model_name:
        doc = frappe.get_single("AICLI Settings")
        model_name = doc.model_name or DEFAULT_MODEL

    if max_workers is None:
        max_workers = DEFAULT_MAX_WORKERS

    # 1. Fetch the File DocType
    file_doc = frappe.get_doc("File", {"file_url": file_url})
    
    # 2. Unzip it
    # We use frappe's native unzip. It returns a list of File docs or we just rely on its behavior.
    file_doc.unzip()
    
    # After unzip, the files are typically created with `attached_to_folder` or `folder`.
    # `unzip()` creates a new folder named after the zip file (without extension) if one doesn't exist,
    # and places all extracted files there.
    import os
    folder_name = os.path.splitext(file_doc.file_name)[0]
    
    # Fetch all newly created file docs
    extracted_files = frappe.get_all("File", filters={"folder": folder_name, "is_folder": 0}, fields=["name", "file_url", "folder"])
    if not extracted_files:
        # Fallback if folder logic differs: fetch files attached to same parent
        extracted_files = frappe.get_all("File", filters={"attached_to_name": file_doc.attached_to_name, "is_folder": 0, "name": ("!=", file_doc.name)}, fields=["name", "file_url", "folder"])
        
    if not extracted_files:
        frappe.throw("No files found after unzipping the archive.")

    file_docs = [frappe.get_doc("File", f.name) for f in extracted_files]

    # Create job using the new repository method
    svc = OcrJobService()
    job_name = svc.create_job_from_files(file_docs, model_name)

    frappe.enqueue(
        "aicli.domains.ocr.tasks.run_ocr_job",
        ocr_job_name=job_name, 
        max_workers=max_workers,
        queue=ENQUEUE_QUEUE, 
        timeout=ENQUEUE_TIMEOUT, 
        is_async=True,
    )

    return {"job_name": job_name, "status": "Queued"}

@frappe.whitelist()
def ocr_status(job_name):
    """Get the current status of an OCR job."""
    from aicli.domains.ocr.job_service import OcrJobService
    return OcrJobService().get_status(job_name)

@frappe.whitelist()
def ocr_output(job_name):
    """Get the assembled markdown output."""
    from aicli.domains.ocr.job_service import OcrJobService
    return {"markdown": OcrJobService().get_output(job_name)}

@frappe.whitelist()
def ocr_jobs():
    """List all OCR jobs."""
    from aicli.domains.ocr.job_service import OcrJobService
    return OcrJobService().list_jobs()

@frappe.whitelist()
def resume_ocr(job_name, max_workers=3):
    """Resume a paused or failed OCR job."""
    from aicli.domains.ocr.constants import ENQUEUE_TIMEOUT, ENQUEUE_QUEUE
    frappe.enqueue(
        "aicli.domains.ocr.tasks.run_ocr_job",
        ocr_job_name=job_name, max_workers=int(max_workers),
        queue=ENQUEUE_QUEUE, timeout=ENQUEUE_TIMEOUT, is_async=True,
    )
    return {"job_name": job_name, "status": "Resuming"}

@frappe.whitelist()
def stop_ocr(job_name):
    """Stop a running OCR job."""
    from aicli.domains.ocr.job_service import OcrJobService
    OcrJobService().stop_job(job_name)
    return {"status": "Paused"}

@frappe.whitelist()
def delete_ocr_job(job_name):
    """Delete an OCR job and all its data."""
    from aicli.domains.ocr.job_service import OcrJobService
    OcrJobService().delete_job(job_name)
    return {"ok": True}

@frappe.whitelist()
def reset_ocr_job(job_name):
    """Reset an OCR job — wipe progress, keep images."""
    from aicli.domains.ocr.job_service import OcrJobService
    OcrJobService().reset_job(job_name)
    return {"ok": True}

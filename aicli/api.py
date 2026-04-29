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
def start_zip_ocr(file_url: str, model_name: str = None, max_workers: int = None, shutdown_after_completion: bool = False):
    """Start OCR job from a Frappe File URL."""
    from aicli.domains.ocr.job_service import OcrJobService
    from aicli.domains.ocr.constants import DEFAULT_MODEL, DEFAULT_MAX_WORKERS, ENQUEUE_TIMEOUT, ENQUEUE_QUEUE

    if not model_name:
        doc = frappe.get_single("AICLI Settings")
        model_name = doc.model_name or DEFAULT_MODEL

    if max_workers is None:
        max_workers = DEFAULT_MAX_WORKERS

    file_doc = frappe.get_doc("File", {"file_url": file_url})
    
    svc = OcrJobService()
    
    # If the file is already attached to an OCR Job, it means we already extracted it.
    if file_doc.attached_to_doctype == "OCR Job" and file_doc.attached_to_name:
        job_name = file_doc.attached_to_name
        # It's already extracted, get the files
        extracted_files = frappe.get_all("File", filters={"attached_to_doctype": "OCR Job", "attached_to_name": job_name, "is_folder": 0, "name": ("!=", file_doc.name)})
        if not extracted_files:
            frappe.throw("Job exists but no extracted images found. Please re-upload.")
    else:
        # Create a new job using the service (handles result file creation)
        job_name = svc.create_job("Native Unzip", "ocr_results", model_name, 0, shutdown_after_completion=shutdown_after_completion)
        
        # Attach the ZIP to the job so unzip() inherits this attachment!
        file_doc.attached_to_doctype = "OCR Job"
        file_doc.attached_to_name = job_name
        file_doc.save(ignore_permissions=True)
        frappe.db.commit()
        
        # Unzip it - Frappe will attach all extracted files to the OCR Job
        file_doc.unzip()
        
        # 3. Retrieve the newly created image File docs using native Frappe Core API
        from frappe.core.api.file import get_attached_images
        # get_attached_images expects a list or a JSON string of a list
        attached = get_attached_images("OCR Job", [job_name])
        image_urls = attached.get(job_name, [])
        
        # Filter out the original ZIP if it's in the list
        image_urls = [url for url in image_urls if url != file_doc.file_url]
        
        import re
        def natural_sort_key(s):
            return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]
        
        image_urls.sort(key=natural_sort_key)
        
        # Create the pages in the DB using the standard File URLs

        pages_data = []
        for i, url in enumerate(image_urls):
            # Extract the original filename from the URL
            filename = url.split("/")[-1]
            # We store the URL (/files/...) and the filename for proper ordering
            pages_data.append({
                "page_number": i + 1, 
                "image_path": url,
                "source_filename": filename
            })
            
        svc._repo.create_pages(job_name, pages_data)
        
        # Update job total pages
        frappe.db.set_value("OCR Job", job_name, "total_pages", len(pages_data))
        
    # Save zip path
    frappe.db.set_value("OCR Job", job_name, "zip_path", file_doc.name)

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

# ──────────────────────────────────────────────────────────────────
# Audio Studio Endpoints — MP3 transcription, analysis, playlists
# ──────────────────────────────────────────────────────────────────

@frappe.whitelist()
def upload_audio():
    """Upload MP3 files and create an Audio Job with tracks."""
    from aicli.domains.audio.job_service import AudioJobService
    from aicli.domains.audio.constants import DEFAULT_WHISPER_MODEL, DEFAULT_LLM_MODEL, AUDIO_EXTENSIONS

    if "files" not in frappe.request.files:
        frappe.throw("No audio files found in request")

    files = frappe.request.files.getlist("files")
    whisper_model = frappe.form_dict.get("whisper_model", DEFAULT_WHISPER_MODEL)
    llm_model = frappe.form_dict.get("llm_model", DEFAULT_LLM_MODEL)

    # Save files via Frappe File system
    file_data = []
    for f in files:
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in AUDIO_EXTENSIONS:
            continue

        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": f.filename,
            "content": f.read(),
            "is_private": 0,
        }).insert(ignore_permissions=True)

        file_data.append({
            "file_url": file_doc.file_url,
            "original_filename": f.filename,
        })

    if not file_data:
        frappe.throw("No valid audio files found. Supported: " + ", ".join(AUDIO_EXTENSIONS))

    frappe.db.commit()

    svc = AudioJobService()
    job_name = svc.create_job(file_data, whisper_model, llm_model)

    # Attach files to the job
    for fd in file_data:
        try:
            fdoc = frappe.get_doc("File", {"file_url": fd["file_url"]})
            fdoc.attached_to_doctype = "Audio Job"
            fdoc.attached_to_name = job_name
            fdoc.save(ignore_permissions=True)
        except Exception:
            pass

    frappe.db.commit()
    return {"job_name": job_name, "tracks": len(file_data)}


@frappe.whitelist()
def start_audio_pipeline(job_name, max_workers=2):
    """Start the audio pipeline in the background."""
    from aicli.domains.audio.constants import ENQUEUE_TIMEOUT, ENQUEUE_QUEUE

    frappe.enqueue(
        "aicli.domains.audio.tasks.run_audio_job",
        job_name=job_name,
        max_workers=int(max_workers),
        queue=ENQUEUE_QUEUE,
        timeout=ENQUEUE_TIMEOUT,
        is_async=True,
    )
    return {"job_name": job_name, "status": "Queued"}


@frappe.whitelist()
def audio_job_status(job_name):
    """Get the current status of an audio job."""
    from aicli.domains.audio.job_service import AudioJobService
    return AudioJobService().get_status(job_name)


@frappe.whitelist()
def audio_tracks(job_name):
    """Get all tracks for an audio job with metadata."""
    from aicli.domains.audio.job_service import AudioJobService
    return AudioJobService().get_tracks(job_name)


@frappe.whitelist()
def audio_playlists(job_name):
    """Get generated playlists for an audio job."""
    from aicli.domains.audio.job_service import AudioJobService
    return AudioJobService().get_playlists(job_name)


@frappe.whitelist()
def audio_jobs():
    """List all audio jobs."""
    from aicli.domains.audio.job_service import AudioJobService
    return AudioJobService().list_jobs()


@frappe.whitelist()
def delete_audio_job(job_name):
    """Delete an audio job and all its data."""
    from aicli.domains.audio.job_service import AudioJobService
    AudioJobService().delete_job(job_name)
    return {"ok": True}


@frappe.whitelist()
def stop_audio_job(job_name):
    """Stop a running audio job."""
    from aicli.domains.audio.job_service import AudioJobService
    AudioJobService().stop_job(job_name)
    return {"status": "Paused"}


@frappe.whitelist()
def generate_recall_triggers(notes):
    """Generate 4 broad recall triggers based on provided notes using OpenRouter."""
    import requests
    import json
    from datetime import datetime

    settings = frappe.get_single("AICLI Settings")
    api_key = settings.get_password("openrouter_api_key")
    model = settings.upsc_recall_model or "openrouter/free"

    if not api_key:
        frappe.throw("OpenRouter API Key is not set in AICLI Settings.")

    prompt = (
        "<INSTRUCTION>\nYou are a strict UPSC Examiner. Generate exactly 4 broad recall triggers based on the NOTES provided.\n\n"
        "STRICT RULES:\n"
        "1. CONCEPT PARTITIONING (NO REPETITION): Each trigger MUST test a completely different concept from the notes. Do not ask about the same topic twice.\n"
        "2. Format: Output a simple list starting with * bullet points. No introductory or concluding text.\n"
        "3. Verb: Start every bullet with: Explain, Detail, Differentiate, or Outline.\n"
        "4. Style: Keep triggers broad. DO NOT include specific names, numbers, or definitions in the triggers themselves.\n"
        "</INSTRUCTION>\n\n"
        "<EXAMPLE OF PARTITIONING>\n"
        "* Explain the structural transition zones between diverse systems.\n"
        "* Detail the phenomena of increased biodiversity at environmental boundaries.\n"
        "* Differentiate the genetic adaptations of specialized populations in unique conditions.\n"
        "* Outline the community distribution characteristics within a junction zone.\n"
        "</EXAMPLE>\n\n"
        "<NOTES>\n" + notes + "\n</NOTES>"
    )

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.0
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        result_data = response.json()
        triggers = result_data.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        if not triggers or "error" in triggers.lower():
            error_msg = result_data.get("error", {}).get("message", "Unknown error from OpenRouter")
            frappe.throw(f"OpenRouter Error: {error_msg}")

        # Save to history
        history_doc = frappe.get_doc({
            "doctype": "UPSC Recall History",
            "notes": notes,
            "triggers": triggers,
            "model": model,
            "timestamp": frappe.utils.now_datetime()
        })
        history_doc.insert(ignore_permissions=True)
        frappe.db.commit()

        return {"triggers": triggers, "history_name": history_doc.name}

    except Exception as e:
        frappe.log_error(f"UPSC Recall Generation Failed: {str(e)}")
        frappe.throw(f"Failed to generate triggers: {str(e)}")


@frappe.whitelist()
def get_recall_history(limit=20):
    """Retrieve recent UPSC recall trigger history."""
    return frappe.get_all(
        "UPSC Recall History",
        fields=["name", "notes", "triggers", "model", "timestamp"],
        order_by="timestamp desc",
        limit=limit
    )

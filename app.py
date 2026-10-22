import base64
import os
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

APP_DIR = Path(__file__).resolve().parent
MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "12"))
MODEL_BASE_URL = os.getenv("MODEL_BASE_URL", "").rstrip("/")
MODEL_API_KEY = os.getenv("MODEL_API_KEY", "")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-VL-7B-Instruct")

app = FastAPI(title="Knowlix AI", version="1.0.0", description="Study assistant for notes, explanations, quizzes, and revision.")
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")

class HealthResponse(BaseModel):
    status: str
    model_configured: bool

@app.get("/", include_in_schema=False)
async def home():
    return FileResponse(APP_DIR / "static" / "index.html")

@app.get("/api/health", response_model=HealthResponse)
async def health():
    return {"status": "ok", "model_configured": bool(MODEL_BASE_URL and MODEL_NAME)}

def build_prompt(mode: str, level: str, length: str, extracted_text: str) -> str:
    mode_instructions = {
        "explain": "Explain the source material clearly. Define key terms, use a simple analogy, and finish with a short recap.",
        "quiz": "Create a quiz based only on the source material. Give 5 multiple-choice questions with four options each, then provide an answer key with brief explanations at the end.",
        "revision": "Create a targeted revision plan based only on the source material. Include key concepts, active-recall prompts, common mistakes if supported, and a short checklist.",
        "evaluate": "Create 3 short-answer questions based on the source material and provide a simple rubric describing what a good answer should include."
    }
    return f"""You are Knowlix AI, a careful study assistant.
Task: {mode_instructions[mode]}
Audience/level: {level}
Requested session length: {length}
Rules:
- Use the supplied study material as the primary source.
- Do not claim a detail appears in the material if it does not.
- If the material is incomplete or hard to read, say so briefly.
- Use readable headings and bullet points.
- Do not reveal hidden reasoning. Give concise educational explanations.
- If the user supplied handwritten notes or a page image, interpret only what is reasonably legible.
STUDY MATERIAL:
{extracted_text if extracted_text else "[The uploaded file is an image. Inspect the image content directly.]"}
"""

async def call_model(prompt: str, image_data_url: Optional[str] = None) -> str:
    if not MODEL_BASE_URL:
        raise HTTPException(
            status_code=503,
            detail="AI model is not configured. Copy .env.example to .env and set MODEL_BASE_URL, MODEL_NAME, and (if required) MODEL_API_KEY. See README.md."
        )
    endpoint = MODEL_BASE_URL
    if not endpoint.endswith("/chat/completions"):
        endpoint = endpoint + "/chat/completions"
    content = [{"type": "text", "text": prompt}]
    if image_data_url:
        content.append({"type": "image_url", "image_url": {"url": image_data_url}})
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.3,
        "max_tokens": 1800
    }
    headers = {"Content-Type": "application/json"}
    if MODEL_API_KEY:
        headers["Authorization"] = f"Bearer {MODEL_API_KEY}"
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="The AI model took too long to respond. Try again or use a smaller file.")
    except httpx.HTTPStatusError as exc:
        message = exc.response.text[:600]
        raise HTTPException(status_code=502, detail=f"AI provider returned HTTP {exc.response.status_code}: {message}")
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Could not read a valid response from the AI endpoint: {exc}")

async def extract_text(upload: UploadFile, raw: bytes) -> str:
    name = (upload.filename or "upload").lower()
    if name.endswith((".txt", ".md", ".csv")) or (upload.content_type or "").startswith("text/"):
        return raw.decode("utf-8", errors="replace")[:60000]
    if name.endswith(".pdf") or upload.content_type == "application/pdf":
        try:
            from pypdf import PdfReader
            import io
            reader = PdfReader(io.BytesIO(raw))
            pages = []
            for page in reader.pages[:30]:
                pages.append(page.extract_text() or "")
            return "\n\n".join(pages)[:60000]
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Could not read this PDF. If it is scanned, upload a page image or run OCR first. Details: {exc}")
    return ""

@app.post("/api/study-session")
async def study_session(
    file: UploadFile = File(...),
    mode: str = Form("explain"),
    level: str = Form("Beginner friendly"),
    length: str = Form("5 minutes")
):
    allowed_modes = {"explain", "quiz", "revision", "evaluate"}
    if mode not in allowed_modes:
        raise HTTPException(status_code=400, detail="Unsupported study mode.")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(raw) > MAX_FILE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File is too large. Maximum size is {MAX_FILE_MB} MB.")
    content_type = file.content_type or ""
    filename = (file.filename or "").lower()
    is_image = content_type.startswith("image/") or filename.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp"))
    is_pdf = content_type == "application/pdf" or filename.endswith(".pdf")
    is_text = filename.endswith((".txt", ".md", ".csv")) or content_type.startswith("text/")
    if not (is_image or is_pdf or is_text):
        raise HTTPException(status_code=415, detail="Supported files: images (PNG/JPG/WEBP/BMP), PDF, TXT, or Markdown.")
    extracted = await extract_text(file, raw)
    image_data_url = None
    if is_image:
        mime = content_type if content_type.startswith("image/") else "image/jpeg"
        image_data_url = f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
    elif is_pdf and not extracted.strip():
        raise HTTPException(status_code=400, detail="No selectable text was found in this PDF. Export a page as an image or OCR the PDF, then upload the image/text.")
    prompt = build_prompt(mode, level, length, extracted)
    result = await call_model(prompt, image_data_url=image_data_url)
    return {"filename": file.filename, "mode": mode, "level": level, "length": length, "result": result}


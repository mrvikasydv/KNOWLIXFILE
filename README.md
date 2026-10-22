# Knowlix AI — Full-stack starter

Knowlix AI turns uploaded study material into explanations, quizzes, and revision plans. This project includes a responsive browser UI and a Python FastAPI backend.

## Features

- Upload an image of notes, selectable-text PDF, TXT, Markdown, or CSV.
- Send images to a vision-language model such as Qwen2.5-VL through an OpenAI-compatible chat-completions API.
- Extract selectable text from PDFs using `pypdf`.
- Generate simple explanations, multiple-choice quizzes, revision plans, and answer-evaluation prompts.
- File-size checks, API error messages, health endpoint, and Docker setup.

## Important model setup

The app does **not** bundle model weights or a hosted AI service. You must run or obtain access to an inference endpoint that supports the OpenAI-compatible `/v1/chat/completions` API and image input for Qwen-VL. A normal text-only endpoint will not understand uploaded images.

1. Install Python 3.11 or newer.
2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # macOS/Linux:
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env`.
4. Set `MODEL_BASE_URL`, `MODEL_NAME`, and `MODEL_API_KEY` for your inference provider. Keep credentials in `.env`; never place them in browser JavaScript or commit `.env`.
5. Start the app:
   ```bash
   uvicorn app:app --reload --port 8080
   ```
6. Open `http://127.0.0.1:8080`. Check `http://127.0.0.1:8080/api/health` for service status.

## Docker

After creating `.env` with your model endpoint:
```bash
docker compose up --build
```
Then open `http://localhost:8080`.

## Model endpoint notes

- `MODEL_BASE_URL` should usually be the base URL ending in `/v1`, such as `http://localhost:8000/v1`. The app appends `/chat/completions`.
- `MODEL_NAME` must exactly match the model name served by your inference provider.
- Some providers require an API key; others do not.
- Qwen2.5-VL deployments differ in image payload handling. If your provider documents a different request format, adapt `call_model()` in `app.py` to that provider's API.
- Model weights may require substantial RAM/VRAM and a compatible inference runtime. You can instead use a trusted hosted endpoint that supports vision input.

## Supported files and limitations

- Images are sent to the vision-language model as base64 data URLs.
- PDFs with selectable text are extracted and sent as text. Scanned PDFs without a text layer are not OCR'd automatically; export pages as images or add a dedicated OCR/PDF-rendering pipeline.
- TXT, Markdown, and CSV files are read as UTF-8 text.
- Maximum upload size defaults to 12 MB (`MAX_FILE_MB`).
- This starter does not include user accounts, persistent file storage, database-backed history, or production authentication/rate limiting. Uploaded bytes are processed in memory and are not saved by this app.
- AI outputs can be wrong; verify important information against your course material.

## Project structure

```text
knowlix-ai/
├── app.py
├── static/
│   └── index.html
├── requirements.txt
├── .env.example
├── Dockerfile
├── docker-compose.yml
└── README.md
```

# Campus Event Assistant – backend (FastAPI + Grok)

Backend for `campus_event_assistant_combined.html`. It checks event proposals against your guideline
documents with Grok (xAI), answers questions in the AI Assistant page, and stores event briefs.

## Run it

```bash
cd campus-event-backend
python -m venv .venv
.venv\Scripts\activate          # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # macOS/Linux: cp .env.example .env
# open .env and paste your key:  XAI_API_KEY=...
uvicorn app.main:app --reload --port 8000
```

Check it: open http://127.0.0.1:8000/health (shows the model, whether the key is set, and how many
guideline documents are loaded). Interactive docs: http://127.0.0.1:8000/docs.
Then open the HTML file. It already points at `http://127.0.0.1:8000`.

## Add your real guidelines

Put PDF, DOCX, TXT or MD files in the `guidelines/` folder (or pick them in the frontend's
"Guideline documents" box, which now uploads them here). New files are picked up automatically.
**Delete `guidelines/SAMPLE_not_official.txt`** – it is a made-up test document.
Scanned PDFs with no text layer cannot be read; `/api/documents` marks them "no extractable text".

## How verification works

`POST /api/verify-event` returns `{"checklist": [...]}`, each item `{id, title, status, reason, source}`:

1. Backend form checks: required details present, numbers valid, end after start, date not in the past.
2. Grok reads the guideline excerpts, lists the mandatory rules that apply to the proposal and marks each
   `pass`, `fail` or `pending`, citing the document and page. If no guideline documents are loaded, or Grok
   returns a pass without a source, the result is `pending`, so the proposal letter stays locked.

If the guideline text is larger than `GUIDELINE_CONTEXT_CHARS` (default 80,000 characters), only the most
relevant excerpts are sent. Grok's output is a review aid, not an official approval.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Status, model, key set?, document count |
| POST | `/api/verify-event` | Checklist for the verification page |
| POST | `/api/chat` | `{question, event_id?}` → `{answer, retrieved_sources, warnings}` |
| POST / GET | `/api/events` | Save / list event briefs (SQLite file `events.db`) |
| GET / DELETE | `/api/events/{id}` | One event / delete it |
| GET / POST | `/api/documents` | List / upload guideline files (`files` form field) |
| DELETE | `/api/documents/{filename}` | Remove a guideline file |

## Notes

- Your xAI key stays on the server in `.env`; the HTML never sees it. Do not commit `.env`.
- `XAI_MODEL` defaults to `grok-4.7`. Model names change, so check https://docs.x.ai/developers/models
  and set the one you have access to. Slow models can take 20–40 s on a long guideline set (the frontend waits 60 s).
- CORS allows any origin by default so the HTML opened from a file works. For a deployed site set
  `CORS_ORIGINS` to your site's address. There is no login on this API, so keep it on your own machine or
  behind your college network unless you add authentication.

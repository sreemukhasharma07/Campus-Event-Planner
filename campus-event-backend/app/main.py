import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from . import chat as chat_service
from . import store
from .config import settings
from .grok import GrokError
from .guidelines import ALLOWED, index
from .mcp_server import mcp
from .verify import verify_event


@asynccontextmanager
async def lifespan(_):
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="Campus Event Assistant API",
              version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False,
                   allow_methods=["*"], allow_headers=["*"])
app.mount("/mcp", mcp.streamable_http_app())


class VerifyIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    eventName: str = ""
    eventType: str = ""
    organizer: str = ""
    coordinator: str = ""
    faculty: str = ""
    eventDate: str = ""
    startTime: str = ""
    endTime: str = ""
    venue: str = ""
    participants: str = ""
    budget: str = ""
    funding: str = ""
    refreshments: str = ""
    externalGuests: str = ""
    equipment: str = ""
    safety: str = ""
    additional: str = ""
    description: str = ""


class ChatIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    event_id: Optional[str] = None


class EventIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str = Field(min_length=1, max_length=200)
    category: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=3000)
    organizer: Optional[str] = Field(None, max_length=200)
    faculty_coordinator: Optional[str] = Field(None, max_length=200)
    proposed_date: Optional[str] = Field(None, max_length=20)
    start_time: Optional[str] = Field(None, max_length=10)
    end_time: Optional[str] = Field(None, max_length=10)
    preferred_venue: Optional[str] = Field(None, max_length=200)
    expected_attendance: Optional[int] = Field(None, ge=0)
    budget_estimate: Optional[float] = Field(None, ge=0)
    equipment_requirements: Optional[str] = Field(None, max_length=1000)
    notes: Optional[str] = Field(None, max_length=3000)


def _grok_http(exc: GrokError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=exc.message)


@app.get("/health")
def health():
    index.refresh()
    return {"status": "ok", "model": settings.model, "grok_key_configured": bool(settings.xai_api_key),
            "guideline_documents": len(index.docs), "guideline_chunks": len(index.chunks)}


@app.post("/api/verify-event")
async def verify(body: VerifyIn):
    try:
        return {"checklist": await verify_event(body.model_dump())}
    except GrokError as exc:
        raise _grok_http(exc)


@app.post("/api/chat")
async def chat(body: ChatIn):
    event = store.get(body.event_id) if body.event_id else None
    try:
        return await chat_service.answer(body.question.strip(), event)
    except GrokError as exc:
        raise _grok_http(exc)


@app.post("/api/events", status_code=201)
def create_event(body: EventIn):
    return store.create(body.model_dump(exclude_none=True))


@app.get("/api/events")
def list_events():
    return {"items": store.list_all()}


@app.get("/api/events/{event_id}")
def get_event(event_id: str):
    ev = store.get(event_id)
    if not ev:
        raise HTTPException(404, "Event not found.")
    return ev


@app.delete("/api/events/{event_id}")
def delete_event(event_id: str):
    if not store.delete(event_id):
        raise HTTPException(404, "Event not found.")
    return {"deleted": True}


@app.get("/api/documents")
def list_documents():
    index.refresh()
    return {"items": index.docs}


@app.post("/api/documents", status_code=201)
async def upload_documents(files: list[UploadFile] = File(...)):
    saved = []
    for f in files:
        name = re.sub(r"[^A-Za-z0-9._ -]", "_",
                      Path(f.filename or "").name).strip(". ")
        if Path(name).suffix.lower() not in ALLOWED:
            raise HTTPException(
                400, f"{f.filename}: only PDF, DOCX, TXT and MD files are accepted.")
        data = await f.read()
        if len(data) > settings.max_upload_bytes:
            raise HTTPException(
                413, f"{f.filename}: file is larger than {settings.max_upload_bytes // 1048576} MB.")
        (settings.guidelines_dir / name).write_bytes(data)
        saved.append(name)
    index.refresh(force=True)
    return {"saved": saved, "items": index.docs}


@app.delete("/api/documents/{filename}")
def delete_document(filename: str):
    path = settings.guidelines_dir / Path(filename).name
    if not path.is_file():
        raise HTTPException(404, "Document not found.")
    path.unlink()
    index.refresh(force=True)
    return {"deleted": True}

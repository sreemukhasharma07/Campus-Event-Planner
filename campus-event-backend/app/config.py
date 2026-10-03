import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


class Settings:
    xai_api_key = os.getenv("XAI_API_KEY", "").strip()
    xai_base_url = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1").rstrip("/")
    model = os.getenv("XAI_MODEL", "grok-4.7").strip()
    timeout = float(os.getenv("XAI_TIMEOUT", "55"))
    temperature = float(os.environ["XAI_TEMPERATURE"]) if os.getenv("XAI_TEMPERATURE") else None
    cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
    context_chars = int(os.getenv("GUIDELINE_CONTEXT_CHARS", "80000"))
    max_upload_bytes = int(float(os.getenv("MAX_UPLOAD_MB", "20")) * 1024 * 1024)
    guidelines_dir = Path(os.getenv("GUIDELINES_DIR", ROOT / "guidelines"))
    db_path = Path(os.getenv("DB_PATH", ROOT / "events.db"))


settings = Settings()
settings.guidelines_dir.mkdir(parents=True, exist_ok=True)

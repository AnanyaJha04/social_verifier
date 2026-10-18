import logging
import shutil

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import auth, clips, editor, observability, sessions, verify, ws
from app.core import db
from app.core.auth import SESSION_TOKEN
from app.core.config import settings
from app.rag import claim_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Live Cutter")

AUTH_EXEMPT_PATHS = {"/api/auth/login", "/api/health"}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api") and request.url.path not in AUTH_EXEMPT_PATHS:
            # Accept either: a Bearer header (used by fetch()-based JSON API
            # calls) or the session cookie (used automatically by the browser
            # for <img>/<video>/<a download> requests, which can't set
            # custom headers at all).
            header_ok = request.headers.get("authorization") == f"Bearer {SESSION_TOKEN}"
            cookie_ok = request.cookies.get("lc_session") == SESSION_TOKEN
            if not (header_ok or cookie_ok):
                return JSONResponse({"detail": "Not authenticated"}, status_code=401)
        return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuthMiddleware)

app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(clips.router)
app.include_router(verify.router)
app.include_router(editor.router)
app.include_router(ws.router)
app.include_router(observability.router)


@app.on_event("startup")
def startup():
    db.get_conn()  # initializes schema

    missing = [
        name for name, bin_path in (
            ("ffmpeg", settings.ffmpeg_bin),
            ("ffprobe", settings.ffprobe_bin),
            ("yt-dlp", settings.ytdlp_bin),
        )
        if shutil.which(bin_path) is None
    ]
    if missing:
        raise RuntimeError(
            f"Required binaries not found on PATH: {', '.join(missing)}. "
            "Install with `brew install ffmpeg yt-dlp` before starting the server."
        )
    if not settings.groq_api_key or "placeholder" in settings.groq_api_key:
        logger.warning(
            "GROQ_API_KEY is not set (or is a placeholder) -- transcription and "
            "boundary detection will fail until a real key is configured in .env"
        )
    if not settings.openai_api_key:
        logger.warning(
            "OPENAI_API_KEY is not set -- reel claim verification will fall back to a "
            "non-web-search Groq model until a real key is configured in .env"
        )
    if settings.qdrant_url:
        try:
            claim_store.ensure_collection()
        except Exception:
            logger.exception(
                "Failed to reach Qdrant at startup -- claim verification will run without "
                "cross-claim context until this is fixed"
            )
    else:
        logger.warning(
            "QDRANT_URL is not set -- reel claim verification will run without cross-claim "
            "context (continuation claims won't see earlier claims in the same video)"
        )


@app.get("/api/health")
def health():
    return {"status": "ok"}


# In the production Docker image the frontend is prebuilt and copied in
# (see Dockerfile); STATIC_DIR points at it and this serves it from the same
# origin as the API. Locally STATIC_DIR is unset and the Vite dev server
# handles the frontend instead, so none of this registers. Registered last
# so it never shadows a real API route -- Starlette matches in registration
# order, and this catch-all pattern would otherwise swallow everything.
if settings.static_dir and settings.static_dir.exists():
    app.mount("/assets", StaticFiles(directory=settings.static_dir / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404)
        candidate = settings.static_dir / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(settings.static_dir / "index.html")

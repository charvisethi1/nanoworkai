from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager

# Load .env before any os.getenv() calls (safe no-op if dotenv not installed)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from . import __version__


# ---------------------------------------------------------------------------
# Application logging
# ---------------------------------------------------------------------------
_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=_LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
    force=True,
)
logging.getLogger("nanowork_mobile").setLevel(
    logging.DEBUG if _LOG_LEVEL == "DEBUG" else logging.INFO
)

from .nano_deploy.waitlist_db import (
    get_page_by_slug,
    get_expired_previews,
    expire_preview,
    get_previews_to_nudge,
    mark_payment_nudged,
)
from .deployment.preview_hosting import CUSTOMER_SITE_HOST, subdomain_serving_apex
from .infrastructure.services import send_linq_message
from .orchestration.tasks import process_message
from .rag_services import conversation_control as _convctrl
from .orchestration import async_queue as _async_queue
from .orchestration.cancel_flags import request_cancel as _request_cancel

logger = logging.getLogger(__name__)

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")
_NANOWORK_DOMAIN = os.getenv("NANOWORK_DOMAIN", "")

STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
RESEND_WEBHOOK_SECRET = os.getenv("RESEND_WEBHOOK_SECRET")
INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "")


# ---------------------------------------------------------------------------
# Lifespan — runs once on startup/shutdown (replaces deprecated @app.on_event)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "nanowork-mobile-agent %s starting (LOG_LEVEL=%s)",
        __version__,
        _LOG_LEVEL,
    )
    from .infrastructure.llm_client import warmup_anthropic_if_enabled

    await warmup_anthropic_if_enabled()
    yield
    logger.info("nanowork-mobile-agent shutting down")


app = FastAPI(
    title="nanowork-mobile-agent",
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
_cors_origins_raw = os.getenv("CORS_ORIGINS", "*").split(",")
_cors_origins = [o.strip() for o in _cors_origins_raw if o.strip()]
_cors_credentials = _cors_origins != ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


_SUBDOMAIN_SKIP = frozenset({
    "api",
    "www",
    "admin",
    "preview",
    "staging",
    "dev",
    "test",
    "mail",
    "smtp",
    "ftp",
    "ns1",
    "ns2",
    # Reserved for OG image / favicon routes; must not resolve as a slug.
    "og",
    "favicon",
})


def _preview_subdomain_suffixes() -> tuple[str, ...]:
    """Host suffixes for preview pages: product apex, plus ``localhost`` when API base is loopback."""
    suf = (CUSTOMER_SITE_HOST,)
    if subdomain_serving_apex(APP_BASE_URL, _NANOWORK_DOMAIN) == "localhost":
        return (*suf, "localhost")
    return suf


class SubdomainRoutingMiddleware(BaseHTTPMiddleware):
    """
    Serves preview HTML at ``{slug}.nanowork.app`` (or ``NANOWORK_PUBLIC_SITE_HOST``) and
    ``{slug}.localhost`` when the API ``APP_BASE_URL`` is loopback.

    No ``/preview/{slug}`` route. Reserved first labels fall through.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        host = request.headers.get("host", "").split(":")[0].lower()
        if not host:
            return await call_next(request)

        if (
            host == CUSTOMER_SITE_HOST
            or host == f"www.{CUSTOMER_SITE_HOST}"
            or host == "localhost"
            or host.startswith("localhost.")
            or host[0].isdigit()
            or host.endswith(".onrender.com")
        ):
            return await call_next(request)

        slug: str | None = None
        for apex_norm in _preview_subdomain_suffixes():
            site_suffix = f".{apex_norm}"
            if host.endswith(site_suffix):
                cand = host[: -len(site_suffix)]
                if cand and "." not in cand and cand not in _SUBDOMAIN_SKIP:
                    slug = cand
                    break

        if not slug:
            return await call_next(request)

        try:
            row = await asyncio.to_thread(get_page_by_slug, slug)
        except Exception:
            logger.exception(
                "[SubdomainRouting] DB lookup failed for slug=%s host=%s — falling through",
                slug,
                host,
            )
            return await call_next(request)

        if row and row.get("page_html"):
            return HTMLResponse(content=row["page_html"])

        return HTMLResponse(content="<h1>Page not found</h1>", status_code=404)


app.add_middleware(SubdomainRoutingMiddleware)


# ---------------------------------------------------------------------------
# Include routers
# ---------------------------------------------------------------------------
from .routers.webhooks import router as webhooks_router
from .routers.pages import router as pages_router
from .routers.connect import router as connect_router
from .routers.internal import router as internal_router
from .routers.customers import router as customers_router
from .routers.diagnostics import router as diagnostics_router
from .routers.orchestration import router as orchestration_router
from .routers.dns import router as dns_router
from .routers.worker import router as worker_router
from .routers.linq_gateway import router as linq_gateway_router
from .routers.memory import router as memory_router
from .routers.scraper import router as scraper_router

app.include_router(orchestration_router)
app.include_router(dns_router)
app.include_router(webhooks_router)
app.include_router(pages_router)
app.include_router(connect_router)
app.include_router(internal_router)
app.include_router(customers_router)
app.include_router(diagnostics_router)
app.include_router(worker_router)
app.include_router(linq_gateway_router)
app.include_router(memory_router)
app.include_router(scraper_router)

# Re-export BackgroundTasks at module level for test backward compatibility
from fastapi import BackgroundTasks  # noqa: F811,E402


# ---------------------------------------------------------------------------
# Global exception handler — surfaces stack traces in logs instead of
# returning a bare 500 with no diagnostic info.
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "Unhandled exception on %s %s",
        request.method,
        request.url.path,
    )
    return JSONResponse(
        {"error": "internal server error", "detail": str(exc)},
        status_code=500,
    )


# ---------------------------------------------------------------------------
# Core routes (health, info, catch-all slug)
# ---------------------------------------------------------------------------
@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "environment": os.getenv("ENVIRONMENT", ""),
    }


@app.get("/health/supabase")
def health_supabase() -> dict:
    """Diagnostic endpoint to check Supabase connectivity and configuration."""
    import socket
    from urllib.parse import urlparse

    supabase_url = os.getenv("SUPABASE_URL", "")
    has_service_key = bool(os.getenv("SUPABASE_SERVICE_KEY"))
    has_anon_key = bool(os.getenv("SUPABASE_ANON_KEY"))

    result = {
        "supabase_url": supabase_url or "(not set)",
        "has_service_key": has_service_key,
        "has_anon_key": has_anon_key,
        "dns_resolution": "unknown",
        "connection_test": "unknown",
    }

    # Test DNS resolution
    if supabase_url:
        try:
            parsed = urlparse(supabase_url)
            hostname = parsed.hostname
            if hostname:
                ip_address = socket.gethostbyname(hostname)
                result["dns_resolution"] = f"ok ({hostname} -> {ip_address})"
                result["hostname"] = hostname
                result["ip_address"] = ip_address
        except socket.gaierror as e:
            result["dns_resolution"] = f"failed: {e}"
        except Exception as e:
            result["dns_resolution"] = f"error: {e}"

    # Test actual Supabase connection
    if has_service_key and supabase_url:
        try:
            from .nano_deploy.waitlist_db import supabase
            # Simple query that should work on any Supabase project
            response = supabase.table("nano_waitlist").select("id").limit(1).execute()
            result["connection_test"] = "ok"
            result["row_count_sample"] = len(response.data) if response.data else 0
        except Exception as e:
            result["connection_test"] = f"failed: {type(e).__name__}: {e}"

    return result


@app.get("/health/linq")
async def health_linq() -> dict:
    """
    Diagnostic endpoint to check Linq API connectivity and configuration.

    Tests:
    1. Environment variables are set
    2. API key is properly formatted
    3. Base URL is reachable
    4. Authentication works (list chats endpoint)
    5. Can send test messages (if test_chat_id provided)
    """
    import httpx

    linq_api_key = os.getenv("LINQ_API_KEY", "")
    linq_base_url = os.getenv("LINQ_BASE_URL", "")

    result = {
        "linq_api_key_set": bool(linq_api_key),
        "linq_api_key_length": len(linq_api_key) if linq_api_key else 0,
        "linq_base_url": linq_base_url or "(not set)",
        "api_reachable": "unknown",
        "authentication": "unknown",
        "error": None
    }

    if not linq_api_key:
        result["error"] = "LINQ_API_KEY environment variable not set"
        return result

    if not linq_base_url:
        result["error"] = "LINQ_BASE_URL environment variable not set"
        return result

    # Test API reachability and authentication
    headers = {
        "Authorization": f"Bearer {linq_api_key}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Try to list chats (read-only, safe operation)
            response = await client.get(
                f"{linq_base_url}/chats",
                headers=headers
            )

            result["api_reachable"] = "yes"
            result["status_code"] = response.status_code

            if response.status_code == 200:
                result["authentication"] = "ok"
                data = response.json()
                if isinstance(data, dict) and 'data' in data:
                    chats = data.get('data', [])
                    result["chats_count"] = len(chats)
                    result["status"] = "healthy"
            elif response.status_code == 401:
                result["authentication"] = "failed"
                result["error"] = "API key is invalid or expired"
                result["status"] = "unhealthy"
            elif response.status_code == 403:
                result["authentication"] = "forbidden"
                result["error"] = "API key lacks required permissions"
                result["status"] = "unhealthy"
            else:
                result["authentication"] = "unknown"
                result["error"] = f"Unexpected status code: {response.status_code}"
                result["response_preview"] = response.text[:200]
                result["status"] = "unhealthy"

    except httpx.ConnectError as e:
        result["api_reachable"] = "no"
        result["error"] = f"Connection failed: {str(e)}"
        result["status"] = "unhealthy"
    except httpx.TimeoutException:
        result["api_reachable"] = "timeout"
        result["error"] = "Request timed out"
        result["status"] = "unhealthy"
    except Exception as e:
        result["error"] = f"Unexpected error: {type(e).__name__}: {str(e)}"
        result["status"] = "unhealthy"

    return result


@app.get("/info")
def info() -> dict[str, str]:
    return {"name": "nanowork-mobile-agent", "version": __version__}


# ---------------------------------------------------------------------------
# Message content extraction helpers
# ---------------------------------------------------------------------------
async def _transcribe_audio(audio_url: str) -> str:
    """Download audio from Linq and transcribe with OpenAI Whisper."""
    import tempfile
    import httpx

    # Download audio file
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            audio_url,
            headers={"User-Agent": "nanowork-mobile-agent/1.0"},
            follow_redirects=True,
        )
        resp.raise_for_status()
        audio_bytes = resp.content

    # Detect format from content-type or URL
    content_type = resp.headers.get("content-type", "audio/m4a")
    ext = ".m4a"
    if "ogg" in content_type or audio_url.endswith(".ogg"):
        ext = ".ogg"
    elif "mpeg" in content_type or audio_url.endswith(".mp3"):
        ext = ".mp3"
    elif "wav" in content_type or audio_url.endswith(".wav"):
        ext = ".wav"
    elif "webm" in content_type or audio_url.endswith(".webm"):
        ext = ".webm"

    # Write to temp file and transcribe
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name

    try:
        import openai
        openai_client = openai.AsyncOpenAI(
            api_key=os.environ.get("OPENAI_API_KEY")
        )
        with open(tmp_path, "rb") as audio_file:
            result = await openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
            )
        return result.text.strip()
    finally:
        os.unlink(tmp_path)


async def _extract_message_content(parts: list) -> tuple[str, bool]:
    """
    Returns (user_text, is_transcribed).
    Handles text, audio/voice, and mixed parts.
    """
    if not parts:
        return "", False

    # Check for media part (Linq sends all media including voice as type="media")
    media_part = next(
        (p for p in parts if p.get("type") == "media"),
        None
    )
    if media_part:
        media_url = media_part.get("url")
        if media_url:
            # Check if it's audio by mime_type, filename, or URL extension
            mime_type = media_part.get("mime_type", "")
            filename = media_part.get("filename", "")
            audio_mimes = (
                "audio/mpeg", "audio/x-m4a", "audio/mp4",
                "audio/aac", "audio/wav", "audio/aiff",
                "audio/x-aiff", "audio/x-caf", "audio/amr",
                "audio/ogg", "audio/webm",
            )
            audio_extensions = (
                ".m4a", ".aac", ".mp3", ".wav",
                ".aiff", ".caf", ".amr", ".ogg", ".webm"
            )
            is_audio = (
                mime_type.lower() in audio_mimes
                or any(filename.lower().endswith(ext) for ext in audio_extensions)
                or any(media_url.lower().split("?")[0].endswith(ext)
                       for ext in audio_extensions)
            )
            if is_audio:
                try:
                    transcription = await _transcribe_audio(media_url)
                    if transcription:
                        return transcription, True
                except Exception:
                    logger.exception(
                        "[Linq webhook] Audio transcription failed url=%s",
                        media_url
                    )
                return "", False
            else:
                # Non-audio media (image, video, doc) — ignore for now
                return "", False

    # Fall back to text
    text_part = next(
        (p for p in parts if p.get("type") in ("text", None)),
        parts[0]
    )
    return (text_part.get("value") or "").strip(), False


# ---------------------------------------------------------------------------
# Linq webhook — kept at app level because integration tests patch
# api.process_message / api._async_queue directly on this module.
# ---------------------------------------------------------------------------
@app.post("/webhook/linq")
async def linq_webhook(request: Request, background_tasks: BackgroundTasks):
    """Entry point for inbound Linq messages."""
    # Log incoming request for debugging
    logger.info("[Linq webhook] Received request from %s", request.client.host if request.client else "unknown")

    try:
        payload = await request.json()
        logger.debug("[Linq webhook] Payload: %s", json.dumps(payload)[:500])
    except Exception as e:
        logger.error("[Linq webhook] Failed to parse JSON body: %s", e, exc_info=True)
        return JSONResponse({"error": "invalid json"}, status_code=400)

    event_type = payload.get("event_type")
    if event_type != "message.received":
        logger.debug("[Linq webhook] Ignoring event_type=%s", event_type)
        return {"status": "ok"}

    data = payload.get("data", {}) or {}
    parts = data.get("parts") or []
    logger.info("[DEBUG] parts=%s", parts)
    user_text, is_transcribed = await _extract_message_content(parts)
    chat_id = (data.get("chat") or {}).get("id")
    sender_handle = data.get("sender_handle") or {}
    sender_phone = sender_handle.get("handle") or ""

    logger.info(
        "[Linq webhook] message.received | chat=%s phone=%s text=%r transcribed=%s",
        chat_id or "MISSING",
        sender_phone or "MISSING",
        user_text[:100],
        is_transcribed
    )

    # Handle empty text (could be failed audio transcription or unsupported media)
    if not user_text:
        # Check if Linq delivered a media message
        media_part = next(
            (p for p in parts if p.get("type") == "media"),
            None
        )

        if media_part and chat_id:
            media_url = media_part.get("url", "")
            # Check if it was an audio file
            audio_extensions = (".m4a", ".aac", ".mp3", ".wav", ".aiff", ".caf", ".amr")
            is_audio = any(media_url.lower().endswith(ext) for ext in audio_extensions)

            if is_audio:
                await send_linq_message(
                    chat_id,
                    "I couldn't catch that voice note 🎙️ — "
                    "try again or type your idea!"
                )
                return JSONResponse({"status": "audio_transcription_failed"})
            else:
                # Other media type (image, video, file, etc.)
                await send_linq_message(chat_id,
                    "I can only understand text messages right now — try describing your idea in a message!")
                return JSONResponse({"status": "unsupported_message_type"})

    if not chat_id:
        logger.warning("[Linq webhook] No chat_id in payload — processing without queue")
        background_tasks.add_task(process_message, payload)
        return {"status": "ok"}

    if not sender_phone:
        logger.warning("[Linq webhook] No sender_phone in payload chat=%s", chat_id)

    intent = _convctrl.classify_control_intent(user_text.strip())
    logger.debug("[Linq webhook] Classified intent=%s for chat=%s", intent, chat_id)

    # Stop / cancel intents: set the flag immediately so orchestrator
    # polls see cancellation before process_message runs (queue drain + task
    # cancel still happen in the handler).
    if intent == _convctrl.CONTROL_STOP and sender_phone:
        logger.info("[Linq webhook] Setting cancel flag for phone=%s", sender_phone)
        _request_cancel(sender_phone)

    if intent != _convctrl.CONTROL_NONE:
        if intent in (_convctrl.CONTROL_STOP, _convctrl.CONTROL_RESTART):
            logger.info("[Linq webhook] Draining queue for chat=%s (intent=%s)", chat_id, intent)
            _async_queue.drain_queue(chat_id)
        logger.info("[Linq webhook] Scheduling immediate processing (control intent=%s)", intent)
        background_tasks.add_task(process_message, payload)
        return {"status": "ok"}

    logger.info("[Linq webhook] Enqueuing message to async queue for chat=%s", chat_id)
    _async_queue.enqueue(chat_id, lambda p=payload: process_message(p))
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Preview lifecycle crons — kept at app level because integration tests
# monkeypatch api_mod.get_expired_previews / api_mod.send_linq_message etc.
# ---------------------------------------------------------------------------

def _check_internal_auth(request: Request) -> JSONResponse | None:
    """Returns a 401 response if the request fails internal-secret validation."""
    if not INTERNAL_SECRET:
        logger.warning(
            "INTERNAL_SECRET is not set — internal endpoint %s is unprotected. "
            "Set INTERNAL_SECRET in the environment to restrict access.",
            request.url.path,
        )
        return None
    if request.headers.get("x-internal-secret") != INTERNAL_SECRET:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return None


async def _send_preview_expired(row: dict) -> None:
    chat_id = row.get("chat_id")
    if not chat_id:
        return
    slug = row.get("page_slug") or "your preview"
    try:
        await send_linq_message(
            chat_id,
            (
                "heads up — the 24h window on your preview just ran out and "
                "i had to take it down ⏳\n\n"
                "reply 'pay' whenever you want it back — i'll spin it up "
                "fresh the moment payment clears 🚀"
            ),
        )
        logger.info("[PreviewExpiry] Notified chat=%s slug=%s", chat_id, slug)
    except Exception:
        logger.exception(
            "[PreviewExpiry] Failed to notify user — continuing takedown chat=%s", chat_id
        )


async def _expire_one_preview(row: dict) -> None:
    phone = row.get("phone_number")
    if not phone:
        return
    try:
        await asyncio.to_thread(expire_preview, phone, build_id=row.get("build_id"))
    except Exception:
        logger.exception(
            "[PreviewExpiry] DB takedown failed phone=%s — skipping notify", phone
        )
        return
    await _send_preview_expired(row)


@app.post("/internal/expire-previews")
async def expire_previews_cron(request: Request, background_tasks: BackgroundTasks):
    if resp := _check_internal_auth(request):
        return resp
    try:
        rows = await asyncio.to_thread(get_expired_previews, 24, 500)
    except Exception:
        logger.exception("[PreviewExpiry] Failed to fetch expired previews")
        return JSONResponse({"error": "db error"}, status_code=500)
    for row in rows:
        background_tasks.add_task(_expire_one_preview, row)
    logger.info("[PreviewExpiry] Queued takedowns for %d previews", len(rows))
    return {"status": "ok", "expired": len(rows)}


async def _send_payment_nudge(row: dict) -> None:
    chat_id = row.get("chat_id")
    phone = row.get("phone_number")
    if not chat_id or not phone:
        return

    name = (row.get("name") or "").strip()
    payment_url = row.get("payment_url") or ""
    greeting = f"hey {name}" if name else "hey"

    if payment_url and payment_url != "PENDING":
        msg = (
            f"{greeting} — your preview's still live but the 24h window is "
            f"almost up ⏳\n\n"
            f"here's your payment link again 👇\n{payment_url}\n\n"
            f"reply when it's done and i'll build out the full site 🚀"
        )
    else:
        msg = (
            f"{greeting} — your preview's still live but the 24h window is "
            f"almost up ⏳\n\n"
            f"reply 'pay' and i'll send the payment link so we can keep "
            f"building 💳"
        )

    try:
        await send_linq_message(chat_id, msg)
    except Exception:
        logger.exception(
            "[PaymentNudge] Failed to DM chat=%s — not marking nudged so we retry next run",
            chat_id,
        )
        return

    try:
        await asyncio.to_thread(mark_payment_nudged, phone, build_id=row.get("build_id"))
        logger.info("[PaymentNudge] Sent and marked phone=%s", phone)
    except Exception:
        logger.exception(
            "[PaymentNudge] DB mark failed phone=%s — may re-nudge; monitor", phone
        )


@app.post("/internal/payment-nudge")
async def payment_nudge_cron(request: Request, background_tasks: BackgroundTasks):
    if resp := _check_internal_auth(request):
        return resp
    try:
        rows = await asyncio.to_thread(get_previews_to_nudge, 12, 24, 500)
    except Exception:
        logger.exception("[PaymentNudge] Failed to fetch nudge candidates")
        return JSONResponse({"error": "db error"}, status_code=500)
    for row in rows:
        background_tasks.add_task(_send_payment_nudge, row)
    logger.info("[PaymentNudge] Queued %d nudges", len(rows))
    return {"status": "ok", "nudged": len(rows)}


_RESERVED_PREFIXES = frozenset({
    "webhook", "internal", "connect", "diag", "orchestrate",
    "payment", "checkout", "og", "preview",
    "changelog", "leads", "customers",
})


@app.get("/{slug}", response_class=HTMLResponse)
async def serve_page_clean(slug: str):
    if slug in _RESERVED_PREFIXES:
        return HTMLResponse(content="<h1>Not found</h1>", status_code=404)
    row = await asyncio.to_thread(get_page_by_slug, slug)
    if not row or not row.get("page_html"):
        return HTMLResponse(content="<h1>Page not found</h1>", status_code=404)
    return HTMLResponse(content=row["page_html"])


logger.info("nanowork-mobile-agent uvicorn app ready")

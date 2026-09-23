"""Web UI backend for Jev Subtitle Translator."""

import json
import logging
import queue
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from .openrouter import (
    OPENROUTER_BASE_URL,
    OpenRouterClient,
    OpenRouterError,
    is_openrouter_url,
)
from .qc import (
    build_report,
    deterministic_check,
    finalize_qc_status,
    normalize_qc_model,
    pair_existing_translation,
    run_jev_qc,
)
from .srt import SRTError, parse_srt, render_srt
from .translator import translate_cues

STATIC_DIR = Path(__file__).parent / "static"
log = logging.getLogger("uvicorn.error")


def _make_client(base_url: str, openrouter_key: str, local_key: str) -> OpenRouterClient:
    """Pick the key that belongs to the endpoint so a local server never sees the OpenRouter key."""

    base_url = base_url.strip() or OPENROUTER_BASE_URL
    key = openrouter_key if is_openrouter_url(base_url) else local_key
    return OpenRouterClient(key, base_url=base_url)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(title="GeekLink Subtitle Translator")

    @app.get("/")
    def root():
        return FileResponse(STATIC_DIR / "index.html", media_type="text/html")

    @app.post("/api/translate")
    def api_translate(
        file: Annotated[UploadFile, File()],
        source_language: Annotated[str, Form()],
        target_language: Annotated[str, Form()],
        model: Annotated[str, Form()],
        api_key: Annotated[str, Form()] = "",
        base_url: Annotated[str, Form()] = OPENROUTER_BASE_URL,
        local_api_key: Annotated[str, Form()] = "",
        jev_model: Annotated[str, Form()] = "typesafe/jev-1.13",
        qc_base_url: Annotated[str, Form()] = OPENROUTER_BASE_URL,
        prompt: Annotated[str, Form()] = "",
    ):
        """Stream NDJSON progress events, ending with a result or error event."""

        jev_model = normalize_qc_model(jev_model)
        try:
            client = _make_client(base_url, api_key, local_api_key)
            qc_client = _make_client(qc_base_url, api_key, local_api_key) if jev_model else None
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})

        try:
            source_cues = parse_srt(file.file.read().decode("utf-8-sig"))
        except (SRTError, UnicodeDecodeError) as exc:
            return JSONResponse(status_code=400, content={"error": f"Invalid SRT: {exc}"})

        events: queue.Queue[dict[str, Any] | None] = queue.Queue()

        def progress(stage: str):
            def report(done: int, total: int) -> None:
                log.info("[%s] %s %d/%d", file.filename, stage, done, total)
                events.put({"type": "progress", "stage": stage, "done": done, "total": total})

            return report

        def run() -> None:
            try:
                log.info(
                    "[%s] %d cues, model=%s @ %s, qc=%s",
                    file.filename,
                    len(source_cues),
                    model,
                    client.label,
                    jev_model or "off",
                )
                progress("translate")(0, len(source_cues))
                translated = translate_cues(
                    client,
                    source_cues,
                    model=model,
                    source_language=source_language,
                    target_language=target_language,
                    custom_prompt=prompt,
                    on_progress=progress("translate"),
                )
                records, _ = deterministic_check(source_cues, translated.translations)
                qc_status, qc_errors = run_jev_qc(
                    qc_client,
                    records,
                    source_language=source_language,
                    target_language=target_language,
                    model=jev_model,
                    custom_prompt=prompt,
                    on_progress=progress("qc"),
                )
                qc_status = finalize_qc_status(records, qc_status)
                report = build_report(
                    source_cues,
                    translated.translations,
                    records,
                    qc_status=qc_status,
                    qc_errors=qc_errors,
                    translation_model=model,
                    jev_model=jev_model,
                    translation_failures=translated.failures,
                )
                events.put(
                    {
                        "type": "result",
                        "mode": "translate",
                        "source_cues": [
                            {
                                "id": cue.id,
                                "number": cue.number,
                                "start": cue.start,
                                "end": cue.end,
                                "text": cue.text,
                            }
                            for cue in source_cues
                        ],
                        "translations": translated.translations,
                        "translated_srt": render_srt(source_cues, translated.translations),
                        "report": report,
                    }
                )
                log.info("[%s] done: qc_status=%s flagged=%d", file.filename, qc_status, report["flagged_count"])
            except OpenRouterError as exc:
                log.warning("[%s] failed: %s", file.filename, exc)
                events.put({"type": "error", "error": str(exc)})
            finally:
                events.put(None)

        threading.Thread(target=run, daemon=True).start()

        def stream() -> Iterator[str]:
            while (event := events.get()) is not None:
                yield json.dumps(event, ensure_ascii=False) + "\n"

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    @app.post("/api/qc")
    def api_qc(
        source_file: Annotated[UploadFile, File()],
        translation_file: Annotated[UploadFile, File()],
        source_language: Annotated[str, Form()],
        target_language: Annotated[str, Form()],
        api_key: Annotated[str, Form()] = "",
        local_api_key: Annotated[str, Form()] = "",
        jev_model: Annotated[str, Form()] = "typesafe/jev-1.13",
        qc_base_url: Annotated[str, Form()] = OPENROUTER_BASE_URL,
        prompt: Annotated[str, Form()] = "",
    ):
        """Run deterministic checks and model review over an existing SRT pair."""

        jev_model = normalize_qc_model(jev_model)
        try:
            qc_client = _make_client(qc_base_url, api_key, local_api_key) if jev_model else None
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})

        try:
            source_cues = parse_srt(source_file.file.read().decode("utf-8-sig"))
        except (SRTError, UnicodeDecodeError) as exc:
            return JSONResponse(status_code=400, content={"error": f"Invalid source SRT: {exc}"})

        try:
            translation_text = translation_file.file.read().decode("utf-8-sig")
            target_cues = parse_srt(translation_text)
        except (SRTError, UnicodeDecodeError) as exc:
            return JSONResponse(status_code=400, content={"error": f"Invalid translated SRT: {exc}"})

        translations = pair_existing_translation(source_cues, target_cues)
        events: queue.Queue[dict[str, Any] | None] = queue.Queue()
        source_name = source_file.filename or "source.srt"

        def progress(done: int, total: int) -> None:
            log.info("[%s] qc %d/%d", source_name, done, total)
            events.put({"type": "progress", "stage": "qc", "done": done, "total": total})

        def run() -> None:
            try:
                log.info(
                    "[%s] independent QC: %d source cues, %d target cues, jev=%s",
                    source_name,
                    len(source_cues),
                    len(target_cues),
                    jev_model,
                )
                records, _ = deterministic_check(
                    source_cues,
                    translations,
                    target_cues=target_cues,
                )
                progress(0, len(source_cues))
                qc_status, qc_errors = run_jev_qc(
                    qc_client,
                    records,
                    source_language=source_language,
                    target_language=target_language,
                    model=jev_model,
                    custom_prompt=prompt,
                    on_progress=progress,
                )
                qc_status = finalize_qc_status(records, qc_status)
                report = build_report(
                    source_cues,
                    translations,
                    records,
                    qc_status=qc_status,
                    qc_errors=qc_errors,
                    translation_model="external",
                    jev_model=jev_model,
                )
                events.put(
                    {
                        "type": "result",
                        "mode": "qc",
                        "source_cues": [
                            {
                                "id": cue.id,
                                "number": cue.number,
                                "start": cue.start,
                                "end": cue.end,
                                "text": cue.text,
                            }
                            for cue in source_cues
                        ],
                        "translations": translations,
                        "translated_srt": translation_text,
                        "report": report,
                    }
                )
                log.info(
                    "[%s] independent QC done: status=%s flagged=%d",
                    source_name,
                    qc_status,
                    report["flagged_count"],
                )
            except OpenRouterError as exc:
                log.warning("[%s] independent QC failed: %s", source_name, exc)
                events.put({"type": "error", "error": str(exc)})
            finally:
                events.put(None)

        threading.Thread(target=run, daemon=True).start()

        def stream() -> Iterator[str]:
            while (event := events.get()) is not None:
                yield json.dumps(event, ensure_ascii=False) + "\n"

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8000)

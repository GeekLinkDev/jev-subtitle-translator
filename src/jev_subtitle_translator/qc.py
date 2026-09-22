"""Deterministic and Jev-powered subtitle translation quality checks."""

import hashlib
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .languages import language_name
from .models import Cue
from .openrouter import OpenRouterClient, OpenRouterError

STATUS_COMPLETED = "completed"
STATUS_NEEDS_REPAIR = "needs_repair"
STATUS_NEEDS_REVIEW = "needs_review"

QC_COMPLETED = "completed"
QC_COMPLETED_WITH_FLAGS = "completed_with_flags"
QC_PARTIAL = "partial"
QC_FAILED = "failed"


def pair_existing_translation(
    source_cues: list[Cue],
    target_cues: list[Cue],
) -> dict[str, str]:
    """Pair an existing translated SRT with its source by cue position."""

    return {
        source_cue.id: target_cues[index].text if index < len(target_cues) else ""
        for index, source_cue in enumerate(source_cues)
    }


def deterministic_check(
    source_cues: list[Cue],
    translations: dict[str, str],
    *,
    target_cues: list[Cue] | None = None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Check pairing and empty translations without calling a model."""

    records: dict[str, dict[str, Any]] = {}
    repair_ids: list[str] = []
    structural_issues: list[str] = []

    if target_cues is not None and len(source_cues) != len(target_cues):
        structural_issues.append("source_target_count_mismatch")

    for index, source_cue in enumerate(source_cues):
        target_text = translations.get(source_cue.id, "")
        issues: list[str] = []
        if source_cue.text.strip() and not target_text.strip():
            issues.append("empty_translation")
        if target_cues is not None and index < len(target_cues):
            target_cue = target_cues[index]
            if target_cue.number != source_cue.number:
                issues.append("subtitle_id_mismatch")
            if target_cue.start != source_cue.start or target_cue.end != source_cue.end:
                issues.append("timing_mismatch")

        status = STATUS_NEEDS_REPAIR if issues else STATUS_COMPLETED
        record = {
            "cue_index": index,
            "srt_id": source_cue.number,
            "source": source_cue.text,
            "translation": target_text,
            "translation_status": status,
            "needs_review": False,
            "issues": issues,
        }
        records[source_cue.id] = record
        if issues:
            repair_ids.append(source_cue.id)

    records["_run"] = {"structural_issues": structural_issues}
    return records, repair_ids


def build_jev_guidelines(source_language: str, target_language: str, custom_prompt: str = "") -> str:
    """Build the semantic review rules shared by the Jev request."""

    source_language = language_name(source_language)
    target_language = language_name(target_language)
    guidance = (
        "You are a bilingual subtitle quality-control checker. You do not translate "
        "or rewrite. Judge whether each "
        f"{target_language} translation of its {source_language} source needs human review.\n"
        "Flag genuine defects: omission, reversed negation, changed numbers/dates/units, "
        "changed or dropped names, opposite meaning, unsupported additions, truncation, "
        "or obvious repetition. Do not flag legitimate wording or word-order differences "
        "that preserve meaning. When uncertain, prefer review."
    )
    if custom_prompt.strip():
        guidance += (
            "\nThe following translator instructions are reference context. Treat choices "
            "explicitly requested there as correct:\n" + custom_prompt.strip()
        )
    return guidance


def run_jev_qc(
    client: OpenRouterClient,
    records: dict[str, dict[str, Any]],
    *,
    source_language: str,
    target_language: str,
    model: str = "typesafe/jev-1.13",
    custom_prompt: str = "",
    batch_size: int = 40,
    workers: int = 3,
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[str, list[str]]:
    """Run Jev over every structurally valid non-empty translation pair.

    Batches run concurrently; ``on_progress(done, total)`` is called as each
    one finishes, with ``done`` counting pairs so it stays monotonic.
    """

    pairs = [
        {
            "id": subtitle_id,
            "source": record.get("source", ""),
            "translation": record.get("translation", ""),
        }
        for subtitle_id, record in records.items()
        if not subtitle_id.startswith("_")
        and record.get("translation_status") == STATUS_COMPLETED
        and record.get("source", "").strip()
        and record.get("translation", "").strip()
    ]
    if not pairs:
        return QC_COMPLETED, []

    guidelines = build_jev_guidelines(source_language, target_language, custom_prompt)
    failures: list[str] = []
    checked = 0
    done = 0
    batch_size = max(1, batch_size)
    batches = [pairs[start : start + batch_size] for start in range(0, len(pairs), batch_size)]

    def review_batch(batch: list[dict[str, str]]) -> tuple[dict[str, bool] | None, str]:
        last_error = ""
        for _ in range(2):
            try:
                verdicts = client.decisions(model=model, pairs=batch, guidelines=guidelines)
                return verdicts, ""
            except OpenRouterError as exc:
                last_error = str(exc)
                if exc.status in {400, 401, 403}:
                    break
        return None, last_error

    # Records are only mutated here on the calling thread, never inside workers.
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(review_batch, batch): batch for batch in batches}
        for future in as_completed(futures):
            batch = futures[future]
            verdicts, last_error = future.result()

            if verdicts is None:
                failures.append(last_error or "jev_request_failed")
            else:
                checked += len(verdicts)
                for subtitle_id, needs_review in verdicts.items():
                    if needs_review and subtitle_id in records:
                        records[subtitle_id]["translation_status"] = STATUS_NEEDS_REVIEW
                        records[subtitle_id]["needs_review"] = True
                        records[subtitle_id].setdefault("issues", []).append("jev_review")

                missing = [pair["id"] for pair in batch if pair["id"] not in verdicts]
                if missing:
                    failures.append(f"jev_missing_verdicts:{','.join(missing)}")

            done += len(batch)
            if on_progress is not None:
                on_progress(done, len(pairs))

    if checked == 0 and failures:
        return QC_FAILED, failures
    if failures:
        return QC_PARTIAL, failures
    return QC_COMPLETED, []


def finalize_qc_status(records: dict[str, dict[str, Any]], status: str) -> str:
    """Promote a successful run when deterministic checks found flagged lines."""

    if status != QC_COMPLETED:
        return status
    has_flags = any(
        key != "_run" and record.get("translation_status") != STATUS_COMPLETED
        for key, record in records.items()
    )
    structural_issues = bool((records.get("_run") or {}).get("structural_issues"))
    return QC_COMPLETED_WITH_FLAGS if has_flags or structural_issues else QC_COMPLETED


def build_report(
    source_cues: list[Cue],
    translations: dict[str, str],
    records: dict[str, dict[str, Any]],
    *,
    qc_status: str,
    qc_errors: list[str],
    translation_model: str,
    jev_model: str,
    translation_failures: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a portable JSON report without writing any telemetry."""

    line_records = [
        record for key, record in records.items() if not key.startswith("_")
    ]
    flagged = [record for record in line_records if record.get("translation_status") != STATUS_COMPLETED]
    return {
        "version": 1,
        "qc_status": qc_status,
        "structural_issues": list((records.get("_run") or {}).get("structural_issues", [])),
        "source_count": len(source_cues),
        "translated_count": sum(bool(value.strip()) for value in translations.values()),
        "flagged_count": len(flagged),
        "translation_model": translation_model,
        "jev_model": jev_model,
        "translation_failures": translation_failures or {},
        "qc_errors": qc_errors,
        "lines": line_records,
        "source_hash": text_hash([cue.text for cue in source_cues]),
        "translation_hash": text_hash([translations.get(cue.id, "") for cue in source_cues]),
    }


def text_hash(lines: list[str]) -> str:
    """Return a stable hash for a sequence of subtitle texts."""

    digest = hashlib.sha256()
    for line in lines:
        digest.update((line or "").encode("utf-8", "replace"))
        digest.update(b"\x1e")
    return digest.hexdigest()

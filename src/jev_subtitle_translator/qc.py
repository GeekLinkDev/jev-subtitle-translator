"""Deterministic and model-powered subtitle translation quality checks."""

import hashlib
import json
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
QC_SKIPPED = "skipped"

QC_METHOD_DECISIONS = "jev_decisions"
QC_METHOD_CHAT = "chat"
QC_METHOD_OFF = "off"

DEFAULT_JEV_MODEL = "~typesafe/jev-latest"
JEV_PROMPT_VERSION = "jev-3"

REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "needs_review": {"type": "boolean"},
                },
                "required": ["id", "needs_review"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def normalize_qc_model(model: str | None) -> str:
    """Return the QC model ID, or '' when semantic QC is turned off ('', 'none', 'off')."""

    model = (model or "").strip()
    return "" if model.lower() in {"", "none", "off"} else model


def qc_method(model: str | None) -> str:
    """Jev models use OpenRouter's Decisions endpoint; any other model reviews via chat."""

    model = normalize_qc_model(model)
    if not model:
        return QC_METHOD_OFF
    return QC_METHOD_DECISIONS if model.lstrip("~").startswith("typesafe/jev") else QC_METHOD_CHAT


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


def build_jev_guidelines(
    source_language: str, target_language: str, custom_prompt: str = ""
) -> str:
    """Build the review rules sent as Jev state.guidelines and as the chat reviewer's system prompt.

    This is the public standalone copy of the canonical GeekLink Worker prompt.
    Keep it aligned with buildJevGuidelines in server/cloudflare_worker.js.
    """

    source_language = language_name(source_language)
    target_language = language_name(target_language)
    custom_prompt = custom_prompt.strip()
    instructions_block = ""
    if custom_prompt:
        instructions_block = (
            "\n--- Translator instructions (reference only) ---\n"
            "The translation was produced under the following user instructions. "
            "Treat any choice these instructions explicitly asked for (specific names, "
            "terminology, tone, style, localization) as CORRECT — do not flag it.\n"
            f"{custom_prompt}\n"
            "--- End of instructions ---\n"
        )
    return (
        "You are a precision-first bilingual subtitle quality-control checker. "
        "You do NOT translate or rewrite. Your job is to identify only clear translation "
        "defects that are worth a human reviewer's time. You judge whether each "
        f"{target_language} translation of its {source_language} source needs human review.\n"
        f"{instructions_block}"
        "The input items are ordered subtitle cues from the same video segment. A cue may "
        "contain only part of a sentence, and the target language may distribute or reorder "
        "meaning across adjacent cues.\n"
        "Before judging an item:\n"
        "1. Read the item itself.\n"
        "2. Inspect surrounding preceding and following items as context. Start with the "
        "nearest cues and expand farther within the available batch when the sentence, "
        "speaker turn, or meaning clearly continues.\n"
        "3. Compare the combined source meaning with the combined target meaning.\n"
        "4. Decide whether a genuine defect remains after accounting for normal cross-cue "
        "continuation and target-language word order.\n"
        "If two or more adjacent cues form one sentence and their combined meaning is "
        "preserved, return false for every cue in that span. Do not flag one cue merely "
        "because its words align with a neighboring cue instead.\n"
        "Flag the current item only when there is a clear, material translation defect:\n"
        "- Source meaning is absent from the current and adjacent target cues, or the source "
        "is left untranslated when it should be translated.\n"
        "- Negation or affirmative meaning is reversed.\n"
        "- A number, date, quantity, unit, or named entity is changed or dropped.\n"
        "- The target expresses the opposite or clearly wrong meaning.\n"
        "- Unsupported information is added.\n"
        "- The output is duplicated, nonsensical, or visibly truncated.\n"
        "- A word or name is visibly cut off mid-token, such as 'Transformati', 'Richa', "
        "or 'meinem T'. This is always a defect even if adjacent cues make the sentence "
        "understandable. A word split across subtitle cues is still a defect.\n"
        "Do NOT flag:\n"
        "- A sentence fragment that is naturally completed in an adjacent target cue.\n"
        "- Meaning that has moved to a neighboring cue because of target-language word order.\n"
        "- Legitimate wording, grammar, tone, or style differences that preserve meaning.\n"
        "- A proper noun, number, symbol, or expression that is correctly identical in both languages.\n"
        "- Awkwardness already present in the source transcription, unless the translation changes its meaning.\n"
        "- Anything the translator instructions above explicitly requested.\n"
        "- Minor stylistic improvements that are optional rather than necessary.\n"
        "This is a review-reduction tool. False positives waste the reviewer's time. "
        "Return true only when you are confident that human review is necessary. "
        "When uncertain, return false."
    )


def build_review_messages(
    pairs: list[dict[str, str]],
    source_language: str,
    target_language: str,
    custom_prompt: str = "",
) -> list[dict[str, str]]:
    """Build the chat prompt used when the QC model is not a Jev Decisions model.

    Mirrors GeekLink's chat fallback so both tools ask non-Jev reviewers the
    same question with the same output shape.
    """

    system = (
        build_jev_guidelines(source_language, target_language, custom_prompt)
        + "\nFor each input item, set needs_review to true or false. "
        "Return ONLY one valid JSON object with this exact schema, nothing else: "
        '{"items":[{"id":"same id","needs_review":true}]}. '
        "Keep every id unchanged, one output item per input item, no extra keys, "
        "no explanations, no markdown."
    )
    payload = {
        "items": [
            {"id": p["id"], "source": p["source"], "translation": p["translation"]} for p in pairs
        ]
    }
    user = (
        f"Check these {language_name(source_language)}->{language_name(target_language)} "
        "subtitle pairs. Return JSON only.\n"
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_review_response(response: dict[str, Any], expected_ids: set[str]) -> dict[str, bool]:
    """Keep only boolean verdicts for expected, non-duplicate IDs."""

    items = response.get("items")
    if not isinstance(items, list):
        raise TypeError("review_items_not_list")
    verdicts: dict[str, bool] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        subtitle_id = str(item.get("id", "")).strip()
        value = item.get("needs_review")
        if subtitle_id in expected_ids and subtitle_id not in verdicts and isinstance(value, bool):
            verdicts[subtitle_id] = value
    return verdicts


def run_jev_qc(
    client: OpenRouterClient | None,
    records: dict[str, dict[str, Any]],
    *,
    source_language: str,
    target_language: str,
    model: str = DEFAULT_JEV_MODEL,
    custom_prompt: str = "",
    batch_size: int = 40,
    workers: int = 3,
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[str, list[str]]:
    """Review every structurally valid non-empty translation pair.

    ``typesafe/jev-*`` models use OpenRouter's Decisions endpoint; any other
    model (hosted or local) is asked through chat completions. An empty model
    skips semantic review and keeps only the deterministic checks.

    Batches run concurrently; ``on_progress(done, total)`` is called as each
    one finishes, with ``done`` counting pairs so it stays monotonic.
    """

    model = normalize_qc_model(model)
    method = qc_method(model)
    if method == QC_METHOD_OFF:
        return QC_SKIPPED, []
    review_tag = "jev_review" if method == QC_METHOD_DECISIONS else "model_review"

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

    def ask(batch: list[dict[str, str]]) -> dict[str, bool]:
        if method == QC_METHOD_DECISIONS:
            return client.decisions(model=model, pairs=batch, guidelines=guidelines)
        response = client.chat_json(
            model=model,
            messages=build_review_messages(batch, source_language, target_language, custom_prompt),
            schema_name="subtitle_review",
            schema=REVIEW_SCHEMA,
        )
        return parse_review_response(response, {pair["id"] for pair in batch})

    def review_batch(batch: list[dict[str, str]]) -> tuple[dict[str, bool] | None, str]:
        last_error = ""
        for _ in range(2):
            try:
                return ask(batch), ""
            except (OpenRouterError, TypeError) as exc:
                last_error = str(exc)
                if isinstance(exc, OpenRouterError) and exc.status in {400, 401, 403}:
                    break
        return None, last_error

    # Records are only mutated here on the calling thread, never inside workers.
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(review_batch, batch): batch for batch in batches}
        for future in as_completed(futures):
            batch = futures[future]
            verdicts, last_error = future.result()

            if verdicts is None:
                failures.append(last_error or "qc_request_failed")
            else:
                checked += len(verdicts)
                for subtitle_id, needs_review in verdicts.items():
                    if needs_review and subtitle_id in records:
                        records[subtitle_id]["translation_status"] = STATUS_NEEDS_REVIEW
                        records[subtitle_id]["needs_review"] = True
                        records[subtitle_id].setdefault("issues", []).append(review_tag)

                missing = [pair["id"] for pair in batch if pair["id"] not in verdicts]
                if missing:
                    failures.append(f"qc_missing_verdicts:{','.join(missing)}")

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

    if status not in {QC_COMPLETED, QC_SKIPPED}:
        return status
    has_flags = any(
        key != "_run" and record.get("translation_status") != STATUS_COMPLETED
        for key, record in records.items()
    )
    structural_issues = bool((records.get("_run") or {}).get("structural_issues"))
    if has_flags or structural_issues:
        return QC_COMPLETED_WITH_FLAGS
    return status


def build_report(
    source_cues: list[Cue],
    translations: dict[str, str],
    records: dict[str, dict[str, Any]],
    *,
    qc_status: str,
    qc_errors: list[str],
    translation_model: str,
    jev_model: str | None,
    translation_failures: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a portable JSON report without writing any telemetry."""

    line_records = [record for key, record in records.items() if not key.startswith("_")]
    flagged = [
        record for record in line_records if record.get("translation_status") != STATUS_COMPLETED
    ]
    return {
        "version": 1,
        "qc_status": qc_status,
        "structural_issues": list((records.get("_run") or {}).get("structural_issues", [])),
        "source_count": len(source_cues),
        "translated_count": sum(bool(value.strip()) for value in translations.values()),
        "flagged_count": len(flagged),
        "translation_model": translation_model,
        "jev_model": normalize_qc_model(jev_model) or None,
        "qc_method": qc_method(jev_model),
        "prompt_version": JEV_PROMPT_VERSION if normalize_qc_model(jev_model) else None,
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

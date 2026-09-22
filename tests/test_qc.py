from pathlib import Path

from jev_subtitle_translator.qc import (
    STATUS_COMPLETED,
    STATUS_NEEDS_REPAIR,
    STATUS_NEEDS_REVIEW,
    build_report,
    deterministic_check,
    finalize_qc_status,
    run_jev_qc,
)
from jev_subtitle_translator.srt import read_srt

FIXTURES = Path(__file__).parent / "fixtures"


def test_deterministic_check_marks_empty_translation_without_fallback():
    source = read_srt(FIXTURES / "english.srt")
    translations = {"0": "Ich sagte ihm, er solle nicht kommen.", "1": ""}

    records, repair_ids = deterministic_check(source[:2], translations)

    assert records["0"]["translation_status"] == STATUS_COMPLETED
    assert records["1"]["translation_status"] == STATUS_NEEDS_REPAIR
    assert records["1"]["translation"] == ""
    assert repair_ids == ["1"]


def test_jev_flags_semantic_review_and_report_contains_line_data():
    class FakeClient:
        def decisions(self, **kwargs):
            return {"0": True, "1": False}

    source = read_srt(FIXTURES / "english.srt")[:2]
    translations = {"0": "Ich sagte ihm, er solle kommen.", "1": "Ich wartete drei Tage."}
    records, _ = deterministic_check(source, translations)

    status, errors, jev_review = run_jev_qc(
        FakeClient(),
        records,
        source_language="English",
        target_language="German",
    )
    report = build_report(
        source,
        translations,
        records,
        qc_status=status,
        qc_errors=errors,
        translation_model="test/translator",
        jev_model="typesafe/jev-1.13",
    )

    assert status == "completed"
    assert errors == []
    assert jev_review["generations"] == []
    assert records["0"]["translation_status"] == STATUS_NEEDS_REVIEW
    assert records["1"]["translation_status"] == STATUS_COMPLETED
    assert report["flagged_count"] == 1
    assert report["lines"][0]["source"] == "I told him not to come."


def test_jev_reports_progress_after_each_batch():
    class FakeClient:
        def decisions(self, **kwargs):
            return {pair["id"]: False for pair in kwargs["pairs"]}

    source = read_srt(FIXTURES / "english.srt")[:3]
    translations = {cue.id: "x" for cue in source}
    records, _ = deterministic_check(source, translations)

    progress = []
    run_jev_qc(
        FakeClient(),
        records,
        source_language="English",
        target_language="German",
        batch_size=2,
        on_progress=lambda done, total: progress.append((done, total)),
    )

    assert progress == [(2, 3), (3, 3)]


def test_target_count_mismatch_is_reported():
    source = read_srt(FIXTURES / "english.srt")
    target = read_srt(FIXTURES / "german-errors.srt")[:3]
    translations = {str(index): cue.text for index, cue in enumerate(target)}

    records, _ = deterministic_check(source, translations, target_cues=target)

    assert records["_run"]["structural_issues"] == ["source_target_count_mismatch"]
    assert records["3"]["translation_status"] == STATUS_NEEDS_REPAIR


def test_successful_run_with_flags_has_explicit_status():
    source = read_srt(FIXTURES / "english.srt")[:1]
    records, _ = deterministic_check(source, {"0": ""})

    assert finalize_qc_status(records, "completed") == "completed_with_flags"


def test_report_includes_jev_review_timing():
    source = read_srt(FIXTURES / "english.srt")[:1]
    translations = {"0": "Ich sagte ihm, er solle nicht kommen."}
    records, _ = deterministic_check(source, translations)

    report = build_report(
        source,
        translations,
        records,
        qc_status="completed",
        qc_errors=[],
        translation_model="test/translator",
        jev_model="typesafe/jev-1.13",
        jev_review={
            "model": "typesafe/jev-1.13",
            "timing_source": "OpenRouter generation metadata",
            "generations": [
                {
                    "generation_id": "gen-dec-test",
                    "generation_time_ms": 0,
                    "latency_ms": 128,
                }
            ],
            "openrouter_generation_time_ms": 0,
            "openrouter_latency_ms": 128,
        },
    )

    assert report["jev_review"]["model"] == "typesafe/jev-1.13"
    assert report["jev_review"]["openrouter_generation_time_ms"] == 0
    assert report["jev_review"]["openrouter_latency_ms"] == 128

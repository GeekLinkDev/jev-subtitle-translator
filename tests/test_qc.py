from pathlib import Path

from jev_subtitle_translator.qc import (
    STATUS_COMPLETED,
    STATUS_NEEDS_REPAIR,
    STATUS_NEEDS_REVIEW,
    build_report,
    deterministic_check,
    finalize_qc_status,
    pair_existing_translation,
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

    status, errors = run_jev_qc(
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
        workers=1,
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

    report = build_report(
        source,
        translations,
        records,
        qc_status="completed_with_flags",
        qc_errors=[],
        translation_model="external",
        jev_model="typesafe/jev-1.13",
    )
    assert report["structural_issues"] == ["source_target_count_mismatch"]


def test_existing_translation_is_paired_by_source_position():
    source = read_srt(FIXTURES / "english.srt")
    target = read_srt(FIXTURES / "german-errors.srt")[:3]

    translations = pair_existing_translation(source, target)

    assert translations["0"] == "Ich sagte ihm, er solle kommen."
    assert translations["2"] == "John rief Anna an."
    assert translations["3"] == ""


def test_successful_run_with_flags_has_explicit_status():
    source = read_srt(FIXTURES / "english.srt")[:1]
    records, _ = deterministic_check(source, {"0": ""})

    assert finalize_qc_status(records, "completed") == "completed_with_flags"


def test_non_jev_model_reviews_through_chat():
    from jev_subtitle_translator.qc import REVIEW_SCHEMA

    class FakeClient:
        def __init__(self):
            self.calls = []

        def chat_json(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "items": [
                    {"id": "0", "needs_review": True},
                    {"id": "1", "needs_review": False},
                    {"id": "9", "needs_review": True},
                ]
            }

        def decisions(self, **kwargs):
            raise AssertionError("chat models must not use the Decisions endpoint")

    client = FakeClient()
    source = read_srt(FIXTURES / "english.srt")[:2]
    records, _ = deterministic_check(source, {"0": "a", "1": "b"})

    status, errors = run_jev_qc(
        client, records, source_language="en", target_language="de", model="qwen2.5:7b"
    )

    assert (status, errors) == ("completed", [])
    assert client.calls[0]["schema"] is REVIEW_SCHEMA
    assert "needs_review" in client.calls[0]["messages"][0]["content"]
    assert records["0"]["issues"] == ["model_review"]
    assert records["1"]["translation_status"] == STATUS_COMPLETED


def test_empty_qc_model_skips_semantic_review_but_keeps_deterministic_flags():
    source = read_srt(FIXTURES / "english.srt")[:2]
    records, _ = deterministic_check(source, {"0": "a", "1": ""})

    status, errors = run_jev_qc(None, records, source_language="en", target_language="de", model="")
    report = build_report(
        source,
        {"0": "a", "1": ""},
        records,
        qc_status=finalize_qc_status(records, status),
        qc_errors=errors,
        translation_model="local",
        jev_model="",
    )

    assert status == "skipped"
    assert report["qc_status"] == "completed_with_flags"
    assert report["qc_method"] == "off"
    assert report["jev_model"] is None
    assert finalize_qc_status(deterministic_check(source[:1], {"0": "a"})[0], "skipped") == "skipped"


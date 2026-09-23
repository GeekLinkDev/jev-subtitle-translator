"""Command-line entry points for translation and subtitle QC."""

import argparse
import json
import os
import sys
from pathlib import Path

from .openrouter import OPENROUTER_BASE_URL, OpenRouterClient, is_openrouter_url
from .qc import (
    build_report,
    deterministic_check,
    finalize_qc_status,
    normalize_qc_model,
    pair_existing_translation,
    run_jev_qc,
)
from .srt import read_srt, write_srt
from .translator import translate_cues


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""

    parser = argparse.ArgumentParser(
        prog="jev-subtitle-translator",
        description="Translate SRT subtitles and check every translation with Jev.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    translate = subparsers.add_parser("translate", help="translate an SRT and run Jev QC")
    translate.add_argument("input", type=Path)
    translate.add_argument("--output", type=Path, required=True)
    _add_language_arguments(translate, include_short_aliases=True)
    translate.add_argument("--model", required=True, help="translation model ID")
    translate.add_argument(
        "--base-url",
        default=OPENROUTER_BASE_URL,
        help="OpenAI-compatible API root for translation, e.g. http://localhost:11434/v1 "
        f"for Ollama (default {OPENROUTER_BASE_URL})",
    )
    translate.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="sampling temperature for translation (default 0; ignored by models that reject it)",
    )
    _add_common_arguments(translate)

    qc = subparsers.add_parser("qc", help="check an existing source and translated SRT")
    qc.add_argument("--source", type=Path, required=True)
    qc.add_argument("--translation", type=Path, required=True)
    qc.add_argument("--output", type=Path, required=True)
    _add_language_arguments(qc, include_short_aliases=False)
    qc.add_argument(
        "--model",
        "--qc-model",
        dest="model",
        default="typesafe/jev-1.13",
        help="QC model: typesafe/jev-* uses Jev Decisions, any other ID reviews via chat",
    )
    _add_qc_base_url(qc)
    qc.add_argument("--prompt", default="", help="optional translation guidance for QC context")
    qc.add_argument("--timeout", type=float, default=120.0)
    qc.add_argument("--batch-size", type=int, default=40)
    qc.add_argument("--workers", type=int, default=3, help="concurrent Jev batches")

    return parser


def _add_language_arguments(
    parser: argparse.ArgumentParser,
    *,
    include_short_aliases: bool,
) -> None:
    source_flags = ["--source-language", "--source"] if include_short_aliases else ["--source-language"]
    target_flags = ["--target-language", "--target"] if include_short_aliases else ["--target-language"]
    parser.add_argument(*source_flags, dest="source_language", required=True)
    parser.add_argument(*target_flags, dest="target_language", required=True)


def _add_qc_base_url(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--qc-base-url",
        default=OPENROUTER_BASE_URL,
        help="OpenAI-compatible API root for QC (Jev models require OpenRouter)",
    )


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--jev-model",
        "--qc-model",
        dest="jev_model",
        default="typesafe/jev-1.13",
        help="QC model: typesafe/jev-* uses Jev Decisions, any other ID reviews via chat, "
        "'none' skips semantic QC",
    )
    _add_qc_base_url(parser)
    parser.add_argument("--prompt", default="", help="additional translation guidance")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--batch-size", type=int, default=40)
    parser.add_argument("--workers", type=int, default=3, help="concurrent request batches")


def main(argv: list[str] | None = None) -> int:
    """Run the selected command and return a shell exit code."""

    args = build_parser().parse_args(argv)
    qc_model = normalize_qc_model(args.jev_model if args.command == "translate" else args.model)
    try:
        qc_client = _make_client(args.qc_base_url, args.timeout) if qc_model else None
        if args.command == "translate":
            client = _make_client(args.base_url, args.timeout)
            return _run_translate(args, client, qc_client, qc_model)
        return _run_qc(args, qc_client, qc_model)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _make_client(base_url: str, timeout: float) -> OpenRouterClient:
    """OpenRouter endpoints read OPENROUTER_API_KEY; other endpoints read optional LOCAL_API_KEY."""

    env_name = "OPENROUTER_API_KEY" if is_openrouter_url(base_url) else "LOCAL_API_KEY"
    api_key = os.environ.get(env_name, "")
    return OpenRouterClient(api_key, base_url=base_url, timeout=timeout)


def _run_translate(
    args: argparse.Namespace,
    client: OpenRouterClient,
    qc_client: OpenRouterClient | None,
    qc_model: str,
) -> int:
    source_cues = read_srt(args.input)
    translated = translate_cues(
        client,
        source_cues,
        model=args.model,
        source_language=args.source_language,
        target_language=args.target_language,
        custom_prompt=args.prompt,
        batch_size=args.batch_size,
        workers=args.workers,
        temperature=args.temperature,
    )
    write_srt(args.output, source_cues, translated.translations)
    records, _ = deterministic_check(source_cues, translated.translations)
    qc_status, qc_errors = run_jev_qc(
        qc_client,
        records,
        source_language=args.source_language,
        target_language=args.target_language,
        model=qc_model,
        custom_prompt=args.prompt,
        batch_size=args.batch_size,
        workers=args.workers,
    )
    qc_status = finalize_qc_status(records, qc_status)
    report = build_report(
        source_cues,
        translated.translations,
        records,
        qc_status=qc_status,
        qc_errors=qc_errors,
        translation_model=args.model,
        jev_model=qc_model,
        translation_failures=translated.failures,
    )
    report_path = Path(f"{args.output}.qc.json")
    _write_json(report_path, report)
    _print_summary(args.output, report_path, report)
    return 1 if translated.failures or qc_status == "failed" else 0


def _run_qc(args: argparse.Namespace, qc_client: OpenRouterClient | None, qc_model: str) -> int:
    source_cues = read_srt(args.source)
    target_cues = read_srt(args.translation)
    translations = pair_existing_translation(source_cues, target_cues)
    records, _ = deterministic_check(source_cues, translations, target_cues=target_cues)
    qc_status, qc_errors = run_jev_qc(
        qc_client,
        records,
        source_language=args.source_language,
        target_language=args.target_language,
        model=qc_model,
        custom_prompt=args.prompt,
        batch_size=args.batch_size,
        workers=args.workers,
    )
    qc_status = finalize_qc_status(records, qc_status)
    report = build_report(
        source_cues,
        translations,
        records,
        qc_status=qc_status,
        qc_errors=qc_errors,
        translation_model="external",
        jev_model=qc_model,
    )
    _write_json(args.output, report)
    _print_summary(args.translation, args.output, report)
    return 1 if qc_status == "failed" else 0


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _print_summary(output_path: Path, report_path: Path, report: dict) -> None:
    print(f"Translation output: {output_path}")
    print(f"QC report: {report_path}")
    print(
        f"QC status: {report['qc_status']}; "
        f"flagged lines: {report['flagged_count']}/{report['source_count']}"
    )


if __name__ == "__main__":
    raise SystemExit(main())

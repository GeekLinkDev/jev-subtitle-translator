"""Command-line entry points for translation and subtitle QC."""

import argparse
import json
import os
import sys
from pathlib import Path

from .openrouter import OpenRouterClient
from .qc import build_report, deterministic_check, finalize_qc_status, run_jev_qc
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
    translate.add_argument("--model", required=True, help="OpenRouter translation model")
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
    qc.add_argument("--model", default="typesafe/jev-1.13", help="Jev Decisions model")
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


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--jev-model", default="typesafe/jev-1.13")
    parser.add_argument("--prompt", default="", help="additional translation guidance")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--batch-size", type=int, default=40)
    parser.add_argument("--workers", type=int, default=3, help="concurrent request batches")


def main(argv: list[str] | None = None) -> int:
    """Run the selected command and return a shell exit code."""

    args = build_parser().parse_args(argv)
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key.strip():
        print("error: OPENROUTER_API_KEY is required", file=sys.stderr)
        return 2

    client = OpenRouterClient(api_key, timeout=args.timeout)
    if args.command == "translate":
        return _run_translate(args, client)
    return _run_qc(args, client)


def _run_translate(args: argparse.Namespace, client: OpenRouterClient) -> int:
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
        client,
        records,
        source_language=args.source_language,
        target_language=args.target_language,
        model=args.jev_model,
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
        jev_model=args.jev_model,
        translation_failures=translated.failures,
    )
    report_path = Path(f"{args.output}.qc.json")
    _write_json(report_path, report)
    _print_summary(args.output, report_path, report)
    return 1 if translated.failures or qc_status == "failed" else 0


def _run_qc(args: argparse.Namespace, client: OpenRouterClient) -> int:
    source_cues = read_srt(args.source)
    target_cues = read_srt(args.translation)
    translations = {
        source_cue.id: target_cues[index].text if index < len(target_cues) else ""
        for index, source_cue in enumerate(source_cues)
    }
    records, _ = deterministic_check(source_cues, translations, target_cues=target_cues)
    qc_status, qc_errors = run_jev_qc(
        client,
        records,
        source_language=args.source_language,
        target_language=args.target_language,
        model=args.model,
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
        jev_model=args.model,
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

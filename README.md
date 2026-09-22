# GeekLink Jev Subtitle Translator

**Translate with your preferred LLM. Check every translation with Jev.**

This project is an early command-line subtitle translator and quality-control
tool. It sends subtitle dialogue to an OpenRouter model using native JSON Schema
structured output, writes a translated SRT file, and then asks Jev to identify
lines that deserve human review.

The first release is intentionally small: SRT input, OpenRouter translation, and
Jev quality control. There is no web interface, account system, telemetry, or
GeekLink-specific service dependency.

## Workflow

```text
source.srt
    |
    v
OpenRouter structured translation
    |
    +--> translated.srt
    |
    v
Deterministic checks + Jev review
    |
    v
translated.srt.qc.json
```

## What it checks

The local deterministic pass catches:

- empty translations;
- missing or duplicated translation IDs;
- source and target cue-count mismatches;
- subtitle number and timing mismatches;
- translation rows that failed upstream.

The Jev pass checks for semantic problems such as:

- omitted content;
- reversed negation;
- changed numbers, dates, quantities, or units;
- changed or missing names and entities;
- unsupported additions;
- truncation or obvious repetition.

Jev produces a review signal. It does not rewrite subtitles automatically and it
does not claim that every unflagged line is correct.

## Installation

Python 3.10 or newer is required.

```bash
git clone https://github.com/GeekLinkDev/jev-subtitle-translator.git
cd jev-subtitle-translator
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
export OPENROUTER_API_KEY="your-api-key"
```

## Translate and check an SRT

```bash
.venv/bin/jev-subtitle-translator translate \
  input.srt \
  --source-language en \
  --target-language de \
  --model your/provider-model \
  --output translated.srt
```

The command creates:

- `translated.srt`, preserving the source cue order, numbers, and timings;
- `translated.srt.qc.json`, containing line-level translation and QC results.

## Check an existing translation

```bash
.venv/bin/jev-subtitle-translator qc \
  --source input.srt \
  --translation translated.srt \
  --source-language en \
  --target-language de \
  --output qc-report.json
```

## Failure handling

The first release deliberately avoids recursive batch splitting:

- missing or empty response IDs are retried only as missing IDs;
- JSON validation, timeout, and server errors retry the same request;
- ordinary failures are not silently converted into source text;
- unresolved translations remain empty and are recorded in the report;
- Jev failures do not overwrite a completed translation.

## Privacy and cost

This repository has no built-in telemetry. Reports are written locally. Subtitle
content is sent to the OpenRouter endpoint and models selected by the user, so
users should review the terms and privacy policies of their chosen providers.
Continuous integration uses mocked responses and does not call paid models.

## Development

```bash
.venv/bin/python -m pytest -q
python3 -m compileall -q src tests
```

The code is organized around a small public boundary:

```text
SRT parser -> structured translation client -> SRT writer
                                      |
                                      v
                              Jev QC and report
```

GeekLink-specific licensing, credits, authentication, analytics, and service
adapters are intentionally outside this repository.

## Relationship to other subtitle translators

The project is inspired by the workflow and usability of
[rockbenben/subtitle-translator](https://github.com/rockbenben/subtitle-translator),
an MIT-licensed subtitle translation project. The first release does not include
source code from that repository. If compatible code is reused later, its
copyright and license notices will be retained.

## Contributing

Useful contributions include reproducible subtitle failure cases, provider
compatibility reports, parser tests, and evaluation data that does not contain
private customer content. Please include the source line, translated line,
expected review decision, provider, and model when reporting a QC issue.

All source comments and docstrings must be written in English. Commit messages
must also be written in English.

## License

Copyright (C) 2026 GeekLinkDev.

This project is licensed under the GNU General Public License version 3 or any
later version. See [LICENSE](LICENSE).

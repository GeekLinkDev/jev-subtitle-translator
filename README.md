# GeekLink Jev Subtitle Translator

Translate SRT subtitles with an OpenRouter-compatible language model and review
the result with Jev.

This is a command-line tool for subtitle translation and quality control. It
keeps the source cue order and timing, uses structured output for translation
responses, and writes a line-level JSON report for human review.

## Features

- Translate SRT files between supported languages.
- Use any translation model available through OpenRouter.
- Request translations with native JSON Schema structured output.
- Preserve subtitle IDs, order, and timing information.
- Run deterministic checks before semantic quality control.
- Ask Jev to flag omissions, changed meaning, names, numbers, negation, and
  other suspicious translations.
- Review the result in a portable local JSON report.

## Workflow

```text
source.srt
    |
    v
Structured translation
    |
    v
translated.srt
    |
    v
Deterministic checks + Jev review
    |
    v
translated.srt.qc.json
```

Jev identifies lines that deserve human review. It does not rewrite subtitles,
and an unflagged line should not be treated as a guarantee of perfect
translation.

## Requirements

- Python 3.10 or newer
- An OpenRouter API key

## Installation

```bash
git clone https://github.com/GeekLinkDev/jev-subtitle-translator.git
cd jev-subtitle-translator
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
export OPENROUTER_API_KEY="your-api-key"
```

## Translate and check an SRT file

```bash
.venv/bin/jev-subtitle-translator translate \
  input.srt \
  --source-language en \
  --target-language de \
  --model your/provider-model \
  --output translated.srt
```

The command writes:

- `translated.srt`, containing the translated subtitles;
- `translated.srt.qc.json`, containing the translation and quality-control
  results for each source cue.

The Jev model defaults to `typesafe/jev-1.13`. To select another model:

```bash
.venv/bin/jev-subtitle-translator translate \
  input.srt \
  --source-language en \
  --target-language de \
  --model your/provider-model \
  --jev-model your/jev-model \
  --output translated.srt
```

Additional translation guidance can be supplied with `--prompt`.

## Check an existing translation

```bash
.venv/bin/jev-subtitle-translator qc \
  --source input.srt \
  --translation translated.srt \
  --source-language en \
  --target-language de \
  --output qc-report.json
```

This mode checks an existing source and translated SRT pair without translating
it again.

## Quality-control report

The report contains:

- the overall quality-control status;
- the source and translated cue counts;
- the selected model names;
- deterministic issues such as empty translations, mismatched IDs, timing
  changes, and count mismatches;
- Jev review flags for individual subtitle lines;
- request or response errors that need attention.

## Data handling

Subtitle text is sent to OpenRouter and the models selected by the user. The
tool writes translation output and quality-control reports to the local
filesystem. Users should review the terms and privacy policies of their chosen
providers before processing sensitive material.

## Development

Install the development dependencies and run the test suite:

```bash
.venv/bin/python -m pytest -q
python3 -m compileall -q src tests
```

## Contributing

Useful contributions include reproducible subtitle failure cases, provider
compatibility reports, parser tests, and evaluation data that does not contain
private or confidential material. When reporting a quality-control issue,
include the source line, translated line, expected review decision, provider,
and model when possible.

## License

Copyright (C) 2026 GeekLinkDev.

This project is licensed under the GNU General Public License version 3 or any
later version. See [LICENSE](LICENSE).

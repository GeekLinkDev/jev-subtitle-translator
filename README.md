# GeekLink Jev Subtitle Translator

Translate with your preferred LLM. Let Jev flag subtitles worth reviewing.

![Demo of subtitle translation and Jev flagging lines for human review](docs/assets/translation-jev-qc.gif)

Translate SRT files, preserve their timing, and review suspicious lines in a local
web interface or JSON report. Translation uses OpenRouter models that support
JSON Schema structured output; Jev automatically checks the results.

## Quick start

Requires **Python 3.10+** and an **OpenRouter API key**. On macOS or Linux:

```bash
git clone https://github.com/GeekLinkDev/jev-subtitle-translator.git
cd jev-subtitle-translator
bash run_web.sh
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000), then:

1. Choose an SRT file, enter your API key, and select the languages and translation model.
2. Click **Translate**. Jev review runs automatically after translation.
3. Review the highlighted lines and download the translated SRT or QC report.

A video file is optional and can be added for local preview.

## What Jev checks

- Missing meaning, unsupported additions, or reversed negation.
- Changed names, numbers, dates, or units.
- Truncated or repeated content.

Empty translations and structural problems are checked locally first. Jev then
reviews each remaining non-empty source/translation pair with a yes/no question:
**Does this translation need human review?**

A flag is a suggestion to inspect a line, not a confirmed error. Jev does not
rewrite translations and can miss mistakes. The [review rules](src/jev_subtitle_translator/qc.py)
and [Jev request](src/jev_subtitle_translator/openrouter.py) are in the source code.

## Command line

Translate and review an SRT:

```bash
export OPENROUTER_API_KEY="your-api-key"

# Translate and automatically run Jev review.
.venv/bin/jev-subtitle-translator translate input.srt \
  --source-language en --target-language de \
  --model openai/gpt-4o-mini --output translated.srt
```

Check an existing translation without translating it again:

```bash
# The API key is required for Jev review.
export OPENROUTER_API_KEY="your-api-key"

.venv/bin/jev-subtitle-translator qc \
  --source input.srt --translation translated.srt \
  --source-language en --target-language de --output qc-report.json
```

The translate command writes `translated.srt` and `translated.srt.qc.json`.
Replace the example translation model with your preferred compatible model.
Jev defaults to `typesafe/jev-1.13`.

Use `--prompt` for additional translation guidance, `--batch-size` and `--workers`
to tune requests, or either command's `--help` for all options.

## Project information

**API usage:** Bring your own OpenRouter key. Translation and Jev review incur
API charges. Subtitle text is sent to OpenRouter and the selected providers;
the interface runs locally.

**GeekLink:** Looking for the desktop app? Visit
[GeekLink Subtitle Translator](https://geeklink.dev/subtitle-translator/).

**Development:** Install test dependencies with `.venv/bin/python -m pip install -e ".[dev]"`
and run `.venv/bin/python -m pytest -q`. See [CONTRIBUTING.md](CONTRIBUTING.md)
to contribute fixes or reproducible subtitle examples.

**License:** [GPL-3.0-or-later](LICENSE). Copyright (C) 2026 GeekLinkDev.

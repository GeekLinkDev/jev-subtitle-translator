# Web UI

A single-page browser front end for the translate + Jev QC pipeline. It is a
thin wrapper over the same functions the CLI uses; nothing is re-implemented.

## Run

```bash
./run_web.sh
```

or manually:

```bash
.venv/bin/python -m pip install -e ".[web]"
.venv/bin/uvicorn --factory jev_subtitle_translator.web:create_app --reload
```

Then open <http://127.0.0.1:8000>.

## Usage

1. Choose an SRT file. Optionally choose a video file; it is previewed in the
   browser and never uploaded.
2. Enter your OpenRouter API key.
3. Pick source/target languages and a translation model. The dropdown shows an
   approximate cost multiplier relative to DeepSeek V3 (input/output tokens
   weighted equally, OpenRouter list price).
4. Click **Translate**. The request blocks until translation and Jev review
   finish, so large files take a while.
5. Review the result. Lines Jev or the deterministic checks flagged are
   highlighted, with the issue tags shown under the line.
6. Download the translated SRT and the QC JSON report from the right panel.

## Files

- `src/jev_subtitle_translator/web.py` – FastAPI app with one endpoint,
  `POST /api/translate`.
- `src/jev_subtitle_translator/static/index.html` – vanilla HTML/CSS/JS, no
  build step.

Language and model choices are remembered in `localStorage`. File pickers reset
on reload; that is browser behaviour.

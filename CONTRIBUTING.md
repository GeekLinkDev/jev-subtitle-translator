# Contributing

Thank you for helping improve subtitle translation quality.

## Before opening a pull request

- Run `.venv/bin/python -m pytest -q`.
- Keep source comments and docstrings in English.
- Do not add API keys, private subtitles, customer data, or telemetry.
- Add a deterministic test for parser, mapping, retry, or QC behavior changes.
- Do not add live model calls to the test suite.

## Useful issue reports

Include a minimal reproducible source/translation pair, the expected review
decision, the provider, and the model. Remove private or copyrighted material
that you are not allowed to redistribute.

## License

Contributions are accepted under the repository license, GPL-3.0-or-later.

# Subtitle Translator with Jev QC

AI subtitle translator with Jev-powered quality control. Translate SRT/ASS/VTT
and automatically flag missing or suspicious lines.

Subtitle Translator with Jev QC combines subtitle translation with a focused,
provider-agnostic quality-control layer. It checks whether the translated output
is structurally complete and whether it still matches the meaning of the source,
then identifies the lines that deserve human attention.

> Status: early development. The interface and supported subtitle formats may
> change while the evaluation set and command-line interface are being finalized.

## Why this exists

An AI translation can return valid JSON and still contain silent errors:

- a subtitle line is missing or empty;
- an input ID is missing, duplicated, or mismatched;
- a negation is reversed;
- a number, date, unit, or proper name changes;
- part of a sentence is omitted;
- the output is fluent but no longer means the same thing as the source.

These failures are difficult to detect with format validation alone. A useful QC
step should combine inexpensive deterministic checks with a focused semantic
review pass.

## How it works

```text
source subtitles + translated subtitles
                    |
                    v
        deterministic structural checks
                    |
                    v
       semantic review of valid source/target pairs
                    |
                    v
        line-level review flags for the user
```

The semantic checker returns a small, machine-readable verdict for each subtitle
ID instead of rewriting the translation:

```json
{
  "items": [
    {"id": "42", "needs_review": true},
    {"id": "43", "needs_review": false}
  ]
}
```

The structured response contract makes the result easy to validate and map back
to the original subtitle lines. The model is instructed to flag issues such as
omission, reversed negation, changed numbers, changed entities, unsupported
additions, truncation, and repetition. Legitimate wording differences should not
be flagged when the meaning is preserved.

## Two layers of checking

### Deterministic checks

These checks do not call an AI model and do not require model credits:

- empty target translations;
- missing IDs;
- duplicate IDs;
- source/target count or pairing mismatches;
- translation rows already known to have failed upstream.

### Semantic review

Every valid source/translation pair can be sent to a binary semantic checker.
The checker does not use a character-overlap shortcut to decide which rows to
review. That kind of shortcut is unreliable for language pairs that use the same
alphabet, such as English and German.

Rows marked `needs_review` are highlighted or written to a sidecar result so the
user can inspect them. A flag is a review signal, not an automatic claim that the
translation is definitely wrong.

## Design principles

- Preserve the source subtitle file and its timing.
- Keep the translated text separate from QC metadata.
- Use structured JSON output plus local response validation.
- Report the exact subtitle IDs that need attention.
- Keep translation status and QC status separate.
- Do not silently replace a failed translation with the source text.
- Let the user decide how to edit a flagged line.
- Keep the semantic checker replaceable: different models and providers should
  be usable behind the same verdict contract.

## Integration

The project is intended to sit after an existing subtitle translation step. It
can be embedded in a desktop application, a batch pipeline, or a command-line
workflow:

```text
subtitle translator
        -> translated subtitle file
        -> Subtitle Translation QC
        -> flagged lines + QC metadata
```

The first integration target is an SRT-based workflow. Format adapters and a
standalone CLI will be added only after the core ID mapping and evaluation
behavior are stable.

## Relationship to Subtitle Translator

This project focuses on a problem that is separate from translation itself:
checking whether an AI-generated subtitle translation is complete and semantically
faithful.

It is designed to work with subtitle translation tools such as
[Subtitle Translator](https://github.com/rockbenben/subtitle-translator), which
is MIT-licensed and supports batch translation. If compatible code is reused from
that project, the original copyright and license notices will be preserved.

## Roadmap

- [ ] Stabilize the source/target subtitle ID contract
- [ ] Add an SRT command-line interface
- [ ] Add OpenAI-compatible and OpenRouter provider adapters
- [ ] Use native JSON Schema structured output where supported
- [ ] Publish a reproducible error corpus for omission, negation, number, and
      entity errors
- [ ] Add evaluation reports for precision, recall, and false-positive rate
- [ ] Add editor-friendly line highlighting and review filters
- [ ] Add Chinese documentation

## Contributing

The most useful contributions at this stage are realistic subtitle examples,
failure cases, evaluation data, and provider compatibility reports. Please open
an issue with the source line, the translated line, the expected judgment, and
the model/provider used when reporting a detection failure.

## License

The project license will be included before the first code release. Any reused
MIT-licensed code will retain its original attribution and license notice.

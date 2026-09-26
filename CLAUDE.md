# Moviewords - repo instructions

## Internationalization

- Never hardcode user-facing strings. All UI copy is authored once, in
  English, in `app/src/messages/en.json`, and rendered through `useI18n()`'s
  `t` / `tn` / `n` helpers (`app/src/i18n/`) - not inlined in components.
- `en.json` is the only file to hand-edit. The other 32 locale files in
  `app/src/messages/*.json` are machine-translated output - never edit them
  directly.
- Committing a staged change to `en.json` triggers the pre-commit hook
  (`.githooks/pre-commit`), which re-runs the translation pipeline and stages
  the regenerated locale files automatically. Enable the hook once per clone
  with `git config core.hooksPath .githooks`. CI (`.github/workflows/i18n.yml`)
  then validates key parity across all locales on every PR that touches
  `app/src/messages/**`, `app/src/i18n/**`, or `pipeline/scripts/i18n/**`.
- Manual commands (from `app/`): `npm run translate` (regenerate all
  locales via Gemini on Vertex AI, GCP project `nomadkaraoke`, ADC auth) and
  `npm run translate:validate` (key-parity check only, no API calls).
- To add a language: add an entry to `app/src/i18n/locales.json` (the single
  source of truth for supported languages, read by both the TypeScript
  runtime and the Python pipeline), then run the translation pipeline to
  generate the new `app/src/messages/<code>.json` file.

See `app/README.md` for the full i18n section (helper signatures, RTL
handling, pipeline details).

## Data quality

- Before publishing any recount, run `pipeline/scripts/audit_quality.py`
  (`--baseline` against the previous run's `--out`) and read what changed -
  the canaries (pre-1968 profanity, anachronisms, word rates, known cases)
  are how bad subtitle files were found. Background: `docs/DATA-QUALITY.md`.
- Judge detection rules by reading flagged files, not by the counts alone:
  three plausible rules were wrong in practice (see DATA-QUALITY.md,
  "Things we tried and threw away").

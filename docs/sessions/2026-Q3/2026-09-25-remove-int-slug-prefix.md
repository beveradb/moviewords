# Remove "INT." from movie page headers - 2026-09-25

**Project:** moviewords   **Branch/commit:** fix/remove-int-slug-prefix -> PR #46, merged as 5998d4a   **Status:** done - deployed and checked in prod

## Summary

Andrew asked what the "INT. " at the top of movie pages was
(`INT. GOODFELLAS - 1990`). It was a screenplay slug-line joke (INT. =
interior scene heading) that suited the Courier look, but readers took it for a
bug. Andrew decided to remove it.

## What changed

- `app/src/components/ui.tsx` - `Slug` no longer defaults its prefix to
  `t('ui.slug.defaultPrefix')`; it renders a prefix only when passed one.
  Movie.tsx never passed one, so the header is now `GoodFellas - 1990`.
  Compare.tsx still passes `1.`, `2.` for its cards.
- Deleted `ui.slug.defaultPrefix` (and the now-empty `ui.slug`) from
  `en.json` and all 32 generated locale files, plus
  `app/src/messages/.en-snapshot.json`.
- `app/src/components/ui.test.tsx` - two `Slug` tests (no prefix by default,
  given prefix is rendered).
- PR #46 squash-merged after CI; the `deploy` workflow succeeded; verified
  live with Playwright on https://moviewords.org/#/movie/tt0099685.

## Learnings / gotchas

- **Removing an en.json key needs manual pruning of every locale.**
  `translate.py` merges into existing locale files and never drops keys that
  were removed from en.json, while `validate-translations.py` fails on "Extra
  key". So delete the key from all `app/src/messages/*.json` with a small
  script (pure deletion - no translated text touched).
- The pre-commit hook rewrites `.en-snapshot.json` *after* the commit is made,
  leaving it modified; amend it into the commit (or stage it first).
- The CodeRabbit GitHub bot doesn't review this repo (no comments on #41, #43
  or #46), and the CLI is SSO-blocked, so CI (i18n validation, GitGuardian) is
  the only PR gate.

## Open threads & next steps

- None.

# Handoff: post-HN sharing strategy (Reddit, PassThePopcorn, etc.)

**Created:** 2026-09-24 (launch day)   **For:** Andrew / a fresh Claude session
**Trigger:** if the Show HN (https://news.ycombinator.com/item?id=49829886) is
quiet by this afternoon, treat it as a bust and move to the channels below.

Paste-ready drafts for every channel already live in **`docs/launch/hn-show-hn.md`**
(Reddit, PTP, Bluesky sections). This doc is the *strategy + sequencing* layer.

## First: is the Show HN actually a bust?

- New Show HNs sit on `/shownew` and need early upvotes/comments to reach the
  front page. If it's still ~1–3 points / 0 comments after a few hours, it didn't
  catch.
- **HN allows ONE re-post** of a Show HN that got no traction. Don't re-post same-
  day — wait ~1–2 weeks, try a different day/time (Tue–Thu 8:30am ET is optimal)
  and optionally a slightly different title. Never ask for upvotes.
- Don't delete the current one; just let it be.

## Channel plan (in recommended order)

### 1. Reddit — r/dataisbeautiful (best fit)
- Needs the **`[OC]`** tag + a top-level comment naming the tool/source within
  ~15 min or it's auto-removed. It wants a **specific visual**, not a homepage
  link — post a screenshot/GIF of ONE chart (the "yes → yeah" or "swell → awesome"
  trend), put the link in the OC comment.
- Title + OC comment drafted in `docs/launch/hn-show-hn.md`.
- Best posting time: weekday mornings US Eastern.

### 2. Reddit — others (higher risk / niche)
- **r/movies** — big but strict self-promo rules; prefer a text-post discussion,
  link in body, read rules first. Medium risk of removal.
- **r/linguistics** — the diachronic angle (words rising/falling) genuinely fits,
  but it's academic and allergic to low-effort promo; lead with methodology.
- **r/Screenwriting** (dialogue angle), **r/DuckDB** (the in-browser SQL /
  serverless build is a legit engineering case study).

### 3. PassThePopcorn (Andrew is a member)
- Private tracker — self-promo/off-site links are sensitive. Post in the
  off-topic/general forum as a member sharing a toy, NOT a launch. Lead with
  cinephile substance (signature words, genre fingerprints), link after. Check
  the forum rules / ask a staffer if unsure. Draft in `hn-show-hn.md`.
- Best AFTER some traction elsewhere so you can mention it lightly.

### 4. Low-effort amplifiers (anytime)
- **Bluesky / Mastodon** — film + data-viz circles; short hook + one chart image
  + link. Draft in `hn-show-hn.md`.
- **Lobste.rs** — invite-only, self-promo metered; the DuckDB-WASM/serverless
  angle is on-brand if Andrew has an account.

## Verified hooks (all checked against the corpus this session — safe to use)
- "dude" most: **The Big Lebowski (120×)**.
- Signature words that reveal the subject, not just names: **Wall Street →
  stock, market, buy, account, management, steel**; **Moneyball → base, team,
  league, field**; **Contact → signal, science, message**.
- Decade shifts (rates/M, 1930s–50s → 2000s+): **"yes"→"yeah"** (yeah 2.4×),
  **"okay" 6×**, **"shit" ~48×** (cinema learns to swear), **"swell"/"gee"/
  "marvelous" → "awesome"/"cool"/"totally"**, **mom/dad casualise 7×/4×**,
  **telegram/telephone → internet/email** (0 → present).
- Corpus honesty: **51,624 films, 26,109 (50.6%) non-English original** (their
  English subtitles are translations). "No signups, no cookies" (verified true).

## Per-channel etiquette (don't get removed / banned)
- Never solicit upvotes anywhere.
- Use a personal account, not a brand.
- Lead with the artifact/finding; disclose you made it; engage genuinely.
- Reddit: obey each sub's self-promo ratio + flair/OC rules; reply to the OC
  comment fast.
- Pre-warm social cards: the OG image + text are already correct
  (moviewords.org/og.png, 51,624 films). Reddit/Bluesky scrape fresh on first
  post; if a platform shows a stale card, use its debugger to re-scrape.

## Related
- `docs/launch/hn-show-hn.md` — the actual paste-ready copy for each channel.
- Analytics to watch during any push: GoatCounter (moviewords.goatcounter.com,
  public) + CF Web Analytics (adblock-resilient; trust it for true magnitude —
  expect it ~3–7× GoatCounter).

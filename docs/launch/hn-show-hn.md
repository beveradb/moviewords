# Launch drafts — paste-ready

Post: **Thu 24 Sep 2026, 8:30am ET (1:30pm UK)**. Be present 2–3h after to reply.

Already done: OG card fixed + live (51,624 films / 326M words / real logo); FB cache pre-warmed (200); HN logged in as `beveradb`; submit form pre-filled; calendar + phone alarm set.

Tomorrow, before you click submit:
- [ ] Open moviewords.org in a fresh incognito window — confirm a clean cold load.
- [ ] Re-read the title + text; **rewrite the text in your own voice** (see HN note below).
- [ ] Click submit. Then stay ~2–3h and reply to every comment.

---

## Hacker News — Show HN

> ⚠️ **Per HN's own guidance ([showhn.html](https://news.ycombinator.com/showhn.html) +
> [tips thread](https://news.ycombinator.com/item?id=22336638)): rewrite the text below
> in your own words, by hand.** HN is currently very sensitive to LLM-sounding copy, and
> the guidance is explicit: *"avoid marketing language, use factual, direct language."*
> The draft is a scaffold — make it sound like you. Don't ask anyone to upvote (against
> the rules). Personal account ✓, email set in profile ✓ (both required/recommended).

**Submit at:** https://news.ycombinator.com/submit  (form is pre-filled in the Playwright browser)
**URL field:** `https://moviewords.org`

**Title** (filled):
`Show HN: Movie Words - what 51,000 films actually say, by word frequency`
Plainer alternative: `Show HN: Movie Words - word frequencies and dialogue trends from 51,000 films`

**Description** — this goes in the submission **text field** (renders at the top of the
thread). Alternatively, leave the text field blank and paste this as your **first comment**
right after submitting; both are accepted for Show HN. Pre-filled version:

What do movies actually say? Not themes or plots, the literal words, counted.

Movie Words takes the English subtitles for ~51,000 films (from the OPUS OpenSubtitles corpus), reduces each to a bag of words, and uses log-odds against the whole corpus to find each film's most distinctive words. A few things I found:

- The film that says "dude" the most is The Big Lebowski (120 times).

- The Godfather Part II's signature words are corleone, fredo, roth, michael, vito.

- Across the decades you can watch "yes" give way to "yeah", "hi" catch up with "hello", and "shall" fade out.

You can filter by original language, decade and genre, and compare any two films, decades or genres side by side. No signup.

How it's built: a Python/DuckDB pipeline turns the 34GB corpus into ~2GB of Parquet and JSON on Cloudflare R2. The site is a static page that reads pre-baked JSON for the common views and runs SQL in the browser (DuckDB-WASM over HTTP range requests) for the interactive ones, so there's no backend.

I only publish derived word counts, never the subtitle text itself. Methodology and limitations (subtitles aren't scripts, the corpus is partial, non-English films use their English subtitles) are in the FAQ.

Happy to answer questions.

**Prepared replies for likely top comments:**
- *"Subtitles aren't the script / OCR noise / fan-subs vary"* → agreed, acknowledged up front; details + caveats in the FAQ.
- *"Corpus is biased toward films that have subtitles"* → yes, it's partial and skews modern/popular; stated in the FAQ.
- *"Isn't this just word frequency?"* → no — log-odds vs the whole corpus surfaces *distinctive* words, not just common ones.
- *"Hosting cost?"* → ~$0. R2 egress is free, the SPA is static on Pages, and interactive queries run in the browser via DuckDB-WASM, so there's no origin to scale.

---

## Reddit — r/dataisbeautiful (post same day / next, reuse winning findings)

Needs the `[OC]` tag + a top-level source comment within ~15 min or it's auto-removed. Submit a screenshot/GIF of ONE chart (the "yes → yeah" trend), link in the OC comment.

**Title:** `[OC] How movie dialogue swapped "yes" for "yeah" over 90 years — from 51,000 films' subtitles`

**Required OC comment:** Tool: DuckDB + Python for the analysis, React/D3 for the charts. Source: English subtitles from the OPUS OpenSubtitles corpus (~51,000 films). Fully interactive version where you can try any words: https://moviewords.org

(r/movies: strict self-promo rules, prefer a text-post discussion, link in body, read rules first — optional/higher-risk.)

---

## PassThePopcorn (post LAST, after HN, gently)

Off-topic/general forum, as a member sharing a toy — not a launch. Lead with cinephile substance.

> I've been building a side project that counts the actual words spoken across ~51k films and finds each one's signature vocabulary — e.g. The Godfather Part II's is "corleone, fredo, roth, michael, vito", and Horror as a genre is "help, god, please, her, house". It can pit genres and decades against each other too. Thought this crowd specifically might enjoy poking at it: https://moviewords.org — only derived word counts, no subtitle text redistributed. Happy to talk methodology.

(Check the forum's off-site-link rules / ask a staffer first if unsure.)

---

## Bluesky / Mastodon (anytime amplifier)

> What do movies *actually say*? I counted the words in 51,000 films' subtitles.
> • "dude" → The Big Lebowski (120×)
> • watch "yes" lose to "yeah" across the decades
> • the intensifier epidemic: totally/literally/basically/actually all climbing
> Browse any word, film, decade or genre: https://moviewords.org

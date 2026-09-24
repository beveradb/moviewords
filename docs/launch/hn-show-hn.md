# Launch drafts — paste-ready

Post: **Thu 24 Sep 2026, 8:30am ET (1:30pm UK)**. Be present 2–3h after to reply.

Pre-flight (do these first):
- [ ] Redeploy so the fixed OG card (51,624 films) is live, and to flush the stale-chunk cache.
- [ ] Open moviewords.org in a fresh incognito window — confirm a clean cold load.
- [ ] Confirm the browser is logged into HN as `beveradb`.

---

## Hacker News — Show HN

**Submit at:** https://news.ycombinator.com/submit
**URL field:** `https://moviewords.org`
**Title (pick one — my pick is #1):**

1. `Show HN: Movie Words – what 51,000 films actually say, by word frequency`
2. `Show HN: I reduced 51,000 films' dialogue to word counts and made it browsable`
3. `Show HN: Analyzing how movie dialogue changed over 90 years`

**First comment — post immediately after submitting:**

I built Movie Words to answer a question that kept nagging me: what do movies *actually say*? Not themes or plots — the literal words, counted.

It takes English subtitles for ~51,000 films (from the OPUS OpenSubtitles corpus), reduces each to a bag of words, and compares it against the whole corpus with log-odds to find each film's signature vocabulary. A few things that fell out:

- The film that says "dude" the most is, inevitably, The Big Lebowski (120×).
- The Godfather Part II's most distinctive words are corleone, fredo, roth, michael, vito.
- You can watch "yes" lose to "yeah", "hello" get caught by "hi", and "shall" quietly die off across the decades.
- The intensifier epidemic is real: totally / literally / basically / actually all climbing together.

You can filter by original language, decade, and genre, compare any two films/decades/genres head-to-head, and every claim links back to the underlying counts.

On the build: it's fully serverless. A Python/DuckDB batch pipeline turns the 34GB corpus into ~2GB of Parquet + JSON on Cloudflare R2. The site is a static SPA that reads pre-baked JSON for hot paths and runs real SQL *in the browser* (DuckDB-WASM over HTTP range requests) for anything interactive — no backend, hosting is free. UI's localized into 33 languages.

One deliberate constraint: only derived word counts are published, never any subtitle text — so nothing copyrighted is redistributed. Methodology and limitations (subtitles ≠ scripts, corpus is partial, translation caveats for non-English films) are in the FAQ.

Happy to answer anything about the pipeline, the in-browser SQL, or the linguistics.

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

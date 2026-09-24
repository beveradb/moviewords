# Restoring the batch pipeline on a fresh VM

The throwaway GCP VM (`moviewords-pipeline-tmp`) was deleted on 2026-09-15
after the dual-corpus bake shipped. Everything needed to resume pipeline
work cheaply is preserved. This runbook recreates a working pipeline VM
with all caches in roughly 30-45 minutes for ~$0.20 of compute.

## When you do NOT need a VM

- App/UI work (i18n, making the all-films corpus the default, new views).
- Re-deriving published JSON (boards, signatures, featured, trends): runs
  locally in minutes - `pipeline/scripts/fetch_published.sh [all]` then
  `uv run python scripts/rebuild_web_data.py --corpus en|all [--stage ...]`,
  publish with `pipeline/scripts/upload_r2.sh`.
- Anything answerable from the published parquets (DuckDB over
  https://data.moviewords.org/...).

A VM (or any box with ~60GB disk) is only needed for a FULL recount - e.g.
a tokenizer change, which re-parses every film. Re-selecting subtitle files
(selection-rule or blocklist changes) and counting new/changed films runs
locally without the 34GB zip: restore the cache archive into `data/work/`,
then `cli index` and `cli count --workers 16` read the published OPUS zip
over HTTP range requests (2026-09-24: 24k films re-counted this way in
~15 min on a laptop). A vote-floor or IMDb refresh adds `curate` (needs the
IMDb TSVs, ~1GB, via `cli download` minus the zip) and `enrich`.

## What is archived, and where

**Private R2 bucket `moviewords-pipeline-cache`** (same Cloudflare account
as the public data bucket; ~790MB ≈ $0.01/month):

| Object | Contents |
|---|---|
| `moviewords-work-cache-2026-09-24.tar.zst` | the whole `data/work/` tree: per-movie count caches (`work/counts/en/`, 64,644 films - keyed by (imdb_id, zip entry), the expensive thing), TMDB caches (`work/tmdb/`, 64,644), plus regenerable parquets (curated, corpus_index, word_counts, movie_stats) |
| `...tar.zst.sha256` | integrity checksum (9ec47e7b636c...37eab); the 2026-09-15 archive (51.7k films) is kept alongside |

**Not archived (re-downloadable):**
- OPUS corpus zip (34GB): `https://object.pouta.csc.fi/OPUS-OpenSubtitles/v2024/raw/en.zip`
  (see `config.OPUS_URL`; the `cli download` stage fetches it, ~15-25 min
  from a GCP datacenter). If OPUS ever removes v2024, a newer release is a
  corpus re-scope anyway - the count caches pin (imdb_id, zip entry) so a
  different zip invalidates them by design.
- IMDb TSVs: always re-download fresh (`cli download`).
- Everything in `data/out/`: recoverable from the public bucket
  (`rclone copy r2:moviewords-data/ ...`) or re-derived from work caches.

**Credentials** (all pre-existing, none were created for the archive):
- R2 S3 creds derive from `CLOUDFLARE_API_TOKEN` in
  `~/Projects/beveradb/.envrc`: access key id = token id from
  `GET /client/v4/user/tokens/verify`, secret = sha256 of the token;
  endpoint `https://<CLOUDFLARE_ACCOUNT_ID>.r2.cloudflarestorage.com`.
- `TMDB_API_KEY` in `moviewords/.envrc`.
- `MOVIEWORDS_CF_TOKEN` in `moviewords/.envrc` (zone purge, R2 bucket admin).

## Recreate the VM and restore

```bash
# 1. Provision (same shape as the original; ~$0.19/h, delete when done)
gcloud compute instances create moviewords-pipeline-tmp \
  --project=nomadkaraoke --zone=us-central1-a \
  --machine-type=e2-highmem-4 --boot-disk-size=200GB \
  --image-family=debian-12 --image-project=debian-cloud

# 2. On the VM (gcloud compute ssh ..., then sudo -i):
apt-get update && apt-get install -y git rclone zstd
curl -LsSf https://astral.sh/uv/install.sh | sh   # installs to /root/.local/bin
git clone https://github.com/beveradb/moviewords /opt/moviewords
cd /opt/moviewords/pipeline && /root/.local/bin/uv sync

# 3. Restore the caches (creds: see above; export RCLONE_CONFIG_R2_* vars)
rclone copy r2:moviewords-pipeline-cache/moviewords-work-cache-2026-09-24.tar.zst /tmp/
(cd /tmp && rclone cat r2:moviewords-pipeline-cache/moviewords-work-cache-2026-09-24.tar.zst.sha256 | sha256sum -c -)
mkdir -p /opt/moviewords/data && cd /opt/moviewords/data
tar -I zstd -xf /tmp/moviewords-work-cache-2026-09-24.tar.zst   # creates work/

# 4. Re-download raw inputs (~20 min; OPUS zip + fresh IMDb TSVs)
cd /opt/moviewords/pipeline
/root/.local/bin/uv run python -m moviewords_pipeline.cli download

# 5. Run whatever changed - the caches make count/enrich incremental
#    (a no-change rerun: curate+index ~15 min, count/enrich ~0, derive ~20 min)
/root/.local/bin/uv run python -m moviewords_pipeline.cli curate
/root/.local/bin/uv run python -m moviewords_pipeline.cli index
/root/.local/bin/uv run python -m moviewords_pipeline.cli count
TMDB_API_KEY=... /root/.local/bin/uv run python -m moviewords_pipeline.cli enrich
/root/.local/bin/uv run python scripts/scan_mislabels.py --adjudicate   # after any scope change
/root/.local/bin/uv run python -m moviewords_pipeline.cli derive --corpus en
/root/.local/bin/uv run python -m moviewords_pipeline.cli derive --corpus all
/root/.local/bin/uv run python scripts/build_movies_index.py --corpus en
/root/.local/bin/uv run python scripts/build_movies_index.py --corpus all
# then rebuild_web_data bakes + posters + upload: follow
# docs/superpowers/plans/2026-09-14-dual-corpus.md Tasks 12-13 (with its
# trends + rclone --filter addenda) and pipeline/README.md
```

Gotchas that bit previous sessions (details in
`docs/sessions/2026-Q3/2026-09-14-dual-corpus-bake-ship.md`):
- `pkill -f pattern` over gcloud ssh kills its own session; use char-class
  patterns like `"cli[ ]derive"`.
- rclone mixed `--include`/`--exclude` ordering is indeterminate - use
  ordered `--filter` rules (upload_r2.sh is the reference).
- Trend/R2 object keys must be RAW words (the edge percent-decodes URL
  paths once); `_word_key` in rebuild_web_data.py documents this.
- rclone→R2 `501 NotImplemented` on unchanged files is harmless modtime
  noise; `--no-update-modtime` silences it.
- Run long stages under `nohup ... & ` with `/opt/*_DONE` marker files and
  poll - SSH sessions drop.

## Refreshing the archive after new pipeline work

After any run that grows the caches, re-archive before deleting the VM:

```bash
cd /opt/moviewords/data
tar -I "zstd -T0 -8" -cf /tmp/moviewords-work-cache-$(date +%F).tar.zst work
sha256sum /tmp/moviewords-work-cache-$(date +%F).tar.zst > /tmp/moviewords-work-cache-$(date +%F).tar.zst.sha256
rclone copy /tmp/moviewords-work-cache-$(date +%F).tar.zst r2:moviewords-pipeline-cache/
rclone copy /tmp/moviewords-work-cache-$(date +%F).tar.zst.sha256 r2:moviewords-pipeline-cache/
rclone check /tmp/moviewords-work-cache-$(date +%F).tar.zst r2:moviewords-pipeline-cache/ --one-way
# keep the newest one or two archives; delete older ones with rclone deletefile
gcloud compute instances delete moviewords-pipeline-tmp --project=nomadkaraoke --zone=us-central1-a
```

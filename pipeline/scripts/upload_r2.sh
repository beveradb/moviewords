#!/usr/bin/env bash
# Upload pipeline/webdata/out/ to the moviewords-data R2 bucket, then purge
# the Cloudflare edge cache so fresh data serves immediately.
#
# webdata/out normally holds a PARTIAL rebuild (only the stages you re-ran),
# so this copies additively - NEVER `rclone sync`, which would delete every
# bucket object missing locally.
#
# Cache-Control: json gets a 5-minute TTL (rebuilt often; a stale edge copy
# of featured-series.json once silently pushed the homepage onto the full SQL
# engine), except the Trends bake (json/trend/** + year-totals.json + year-films.json, including
# the per-language all/lang/<code>/json/trend/** + year-totals.json + year-films.json), which
# is one file per word and safe to cache for 1h. Parquets keep 24h - the
# post-upload purge swaps versions, and parquet range reads revalidate via
# If-Range/ETag.
#
# Posters (.jpg + .avif, keyed by imdb id, never rewritten) are cached for a
# year as immutable. They live in data/out/posters/ (fetch_posters.py /
# encode_posters.py), not webdata/out, so they get their own copy step;
# override the source with POSTERS_DIR (absolute, or relative to webdata/out).
# Skipped with a warning if the directory is absent. --checksum skips objects
# already in the bucket, so the header only lands on NEW uploads - rewrite
# existing objects' metadata server-side if the policy ever changes.
#
# rclone --filter patterns containing a non-trailing `/` (e.g. `all/json/trend/**`)
# are anchored to the root, so per-language paths need their own explicit
# `all/lang/*/...` rules - they are NOT covered by the `all/json/trend/**`
# rule despite both ending in `/trend/**`.
#
# Requires: CLOUDFLARE_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY
# Optional: MOVIEWORDS_CF_TOKEN (needs Zone Read + Cache Purge on the
#           moviewords.org zone) - skips the edge purge with a warning if
#           unset. Purging the whole zone (not per-URL) is deliberate: data
#           objects serve with `Vary: Origin`, and a single-URL purge misses
#           the per-Origin variants unless each is named explicitly.
set -euo pipefail
cd "$(dirname "$0")/../webdata/out"
: "${CLOUDFLARE_ACCOUNT_ID:?}" "${R2_ACCESS_KEY_ID:?}" "${R2_SECRET_ACCESS_KEY:?}"
export RCLONE_CONFIG_R2_TYPE=s3
export RCLONE_CONFIG_R2_PROVIDER=Cloudflare
export RCLONE_CONFIG_R2_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
export RCLONE_CONFIG_R2_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
export RCLONE_CONFIG_R2_ENDPOINT="https://${CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com"
# ~680k small objects (mostly trend JSONs): per-request latency, not
# bandwidth, is the limit. rclone's default 4 transfers would take ~14h;
# 64 takes ~1.5h. Override via the environment if needed.
export RCLONE_TRANSFERS="${RCLONE_TRANSFERS:-64}" RCLONE_CHECKERS="${RCLONE_CHECKERS:-64}"
export RCLONE_NO_UPDATE_MODTIME=true   # silences R2's harmless 501 modtime noise
# One attempt per pass: each file already gets rclone's low-level retries,
# and a whole-pass retry re-checks all ~770k files. With an old rclone the
# 501s below count as errors, so the default 3 attempts cost ~2 extra hours
# and then fail the script before the later passes and the purge ran
# (2026-09-25).
export RCLONE_RETRIES="${RCLONE_RETRIES:-1}"
# rclone < 1.65 (e.g. Debian 12's 1.60) rewrites an unchanged object's
# mtime with an S3 server-side copy that R2 rejects (501 NotImplemented,
# ~1 per unchanged file). Install a current one: curl https://rclone.org/install.sh | sudo bash
rclone_minor=$(rclone version | sed -n 's/^rclone v1\.\([0-9]*\).*/\1/p')
if [[ -n "$rclone_minor" && "$rclone_minor" -lt 65 ]]; then
  echo "WARNING: rclone v1.$rclone_minor is too old for R2 (see comment above)" >&2
fi

# Ordered --filter rules, NOT mixed --include/--exclude: rclone does not
# apply mixed include/exclude flags in command-line order (excludes never
# beat `--include '*.json'`); --filter rules ARE first-match-wins in the
# order given.
rclone copy . r2:moviewords-data/ --checksum --stats 60s --stats-one-line \
  --filter '+ json/trend/**' --filter '+ all/json/trend/**' --filter '+ all/lang/*/json/trend/**' \
  --filter '+ json/year-totals.json' --filter '+ all/json/year-totals.json' --filter '+ all/lang/*/json/year-totals.json' \
  --filter '+ json/year-films.json' --filter '+ all/json/year-films.json' --filter '+ all/lang/*/json/year-films.json' \
  --filter '+ all/rating/*/json/trend/**' --filter '+ all/rating/*/json/year-totals.json' --filter '+ all/rating/*/json/year-films.json' \
  --filter '+ json/blurb/**' --filter '+ all/json/blurb/**' --filter '+ json/words/**' --filter '+ all/json/words/**' \
  --filter '- *' --header-upload "Cache-Control: public, max-age=3600"
rclone copy . r2:moviewords-data/ --checksum --stats 60s --stats-one-line \
  --filter '- json/trend/**' --filter '- all/json/trend/**' --filter '- all/lang/*/json/trend/**' \
  --filter '- json/year-totals.json' --filter '- all/json/year-totals.json' --filter '- all/lang/*/json/year-totals.json' \
  --filter '- json/year-films.json' --filter '- all/json/year-films.json' --filter '- all/lang/*/json/year-films.json' \
  --filter '- all/rating/*/json/trend/**' --filter '- all/rating/*/json/year-totals.json' --filter '- all/rating/*/json/year-films.json' \
  --filter '- json/blurb/**' --filter '- all/json/blurb/**' --filter '- json/words/**' --filter '- all/json/words/**' \
  --filter '+ *.json' --filter '- *' \
  --header-upload "Cache-Control: public, max-age=300"
rclone copy . r2:moviewords-data/ --checksum --stats 60s --stats-one-line \
  --exclude '*.json' --exclude 'posters/**' \
  --header-upload "Cache-Control: public, max-age=86400"
echo "Uploaded $(du -sh . | cut -f1) from webdata/out to r2:moviewords-data"

posters="${POSTERS_DIR:-../../../data/out/posters}"
if [[ -d "$posters" ]]; then
  rclone copy "$posters" r2:moviewords-data/posters/ --checksum --stats 60s --stats-one-line \
    --filter '- *.part.avif' --filter '+ *.jpg' --filter '+ *.avif' --filter '- *' \
    --header-upload "Cache-Control: public, max-age=31536000, immutable"
  echo "Uploaded posters from $posters"
else
  echo "WARNING: no posters dir at $posters - skipped poster upload" >&2
fi

if [[ -n "${MOVIEWORDS_CF_TOKEN:-}" ]]; then
  # the upload already succeeded, so purge problems only warn - never fail
  zone=$(curl -fsS -H "Authorization: Bearer $MOVIEWORDS_CF_TOKEN" \
    "https://api.cloudflare.com/client/v4/zones?name=moviewords.org" |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["result"][0]["id"])' \
    2>/dev/null) || zone=""
  if [[ -n "$zone" ]] && curl -fsS -X POST \
    -H "Authorization: Bearer $MOVIEWORDS_CF_TOKEN" \
    -H "Content-Type: application/json" -d '{"purge_everything":true}' \
    "https://api.cloudflare.com/client/v4/zones/${zone}/purge_cache" |
    grep -q '"success": *true'; then
    echo "Purged moviewords.org edge cache"
  else
    echo "WARNING: edge purge failed - stale data may serve up to the object TTL" >&2
  fi
else
  echo "WARNING: MOVIEWORDS_CF_TOKEN unset - skipped edge purge (json stale up to 5 min, parquet up to 24h)" >&2
fi

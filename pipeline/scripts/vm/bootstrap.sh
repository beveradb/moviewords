#!/usr/bin/env bash
# Bootstrap a pipeline VM (see docs/PIPELINE-RESTORE.md). Run as root, detached:
#   sudo setsid bash bootstrap.sh <branch> </dev/null >/dev/null 2>&1 &
# Expects /tmp/mw_r2.env (R2 + CF creds, chmod 600) and optionally
# /tmp/mw_tmdb_release.tar.zst (the MPAA ratings cache) copied up first.
# Logs /opt/bootstrap.log; touches /opt/BOOTSTRAP_DONE at the end.
set -euxo pipefail
exec >>/opt/bootstrap.log 2>&1        # plain redirect - never `> >(tee ...)` (see count.sh)
BRANCH=${1:-main}
CACHE=${CACHE:-moviewords-work-cache-2026-09-25.tar.zst}
export DEBIAN_FRONTEND=noninteractive
apt-get update -q && apt-get install -y -q git zstd curl unzip
# Debian's rclone (1.60) makes R2 return 501 for every unchanged file
# (`|| true`: on a fresh image there is no rclone, and pipefail + set -e
# would end the script right here, silently)
minor=$(rclone version 2>/dev/null | sed -n 's/^rclone v1\.\([0-9]*\).*/\1/p' || true)
if [[ -z "$minor" || "$minor" -lt 65 ]]; then curl -fsS https://rclone.org/install.sh | bash; fi
command -v /root/.local/bin/uv || curl -LsSf https://astral.sh/uv/install.sh | sh
UV=/root/.local/bin/uv

[ -d /opt/moviewords ] || git clone -q https://github.com/beveradb/moviewords /opt/moviewords
cd /opt/moviewords && git fetch -q origin && git checkout -q "$BRANCH" && git pull -q || true
cd pipeline && $UV sync -q

set +x; source /tmp/mw_r2.env; set -x
mkdir -p /opt/moviewords/data/raw && cd /opt/moviewords/data
if [ ! -d work/counts ]; then
  rclone copy "r2:moviewords-pipeline-cache/$CACHE" /tmp/
  (cd /tmp && rclone cat "r2:moviewords-pipeline-cache/$CACHE.sha256" | sha256sum -c -)
  zstd -dc "/tmp/$CACHE" | tar -x
fi
[ -f /tmp/mw_tmdb_release.tar.zst ] && (cd work && zstd -dc /tmp/mw_tmdb_release.tar.zst | tar -x)
# archives made on a Mac carry AppleDouble ._* files; derive chokes on them
find /opt/moviewords/data -name '._*' -delete

# the previous picks, for diffing what a recount changes
python3 - <<'EOF'
import json, glob
d = {}
for p in glob.glob('/opt/moviewords/data/work/counts/en/tt*.json'):
    r = json.load(open(p)); d[r['imdb_id']] = r['zip_name']
json.dump(d, open('/opt/moviewords/data/work/old_picks.json', 'w'))
print(len(d), 'old picks')
EOF

# the OPUS zip, local: ~10 min from europe-north1 (next to the CSC server);
# every read is then a file seek instead of an HTTP range request
if [ ! -s raw/opus_en.zip ]; then
  curl -fsS --retry 5 -o raw/opus_en.zip.part https://object.pouta.csc.fi/OPUS-OpenSubtitles/v2024/raw/en.zip
  mv raw/opus_en.zip.part raw/opus_en.zip
fi
touch /opt/BOOTSTRAP_DONE

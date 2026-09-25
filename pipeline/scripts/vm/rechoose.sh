#!/usr/bin/env bash
# Re-choose every film's subtitle from cached fingerprints (a SELECTION_VERSION
# bump, new TMDB credits, a retrained quality model), then run the quality
# audit. Run as root, detached, after `git push`:
#   sudo setsid bash rechoose.sh </dev/null >/dev/null 2>&1 &
# Optional /tmp/mw_credits.tar.zst (work/tmdb_credits from the laptop's
# `credits` stage) is unpacked first. Logs /opt/rechoose.log; writes
# /opt/audit.{md,json}; touches /opt/RECHOOSE_DONE.
set -euxo pipefail
exec >>/opt/rechoose.log 2>&1
rm -f /opt/RECHOOSE_DONE
R=/opt/moviewords
UV=/root/.local/bin/uv
cd $R && git pull -q
if [ -f /tmp/mw_credits.tar.zst ]; then
  (cd $R/data/work && zstd -dc /tmp/mw_credits.tar.zst | tar -x)
  find $R/data/work -name '._*' -delete
fi
cd $R/pipeline
time $UV run python -u -m moviewords_pipeline.cli count --workers 8
time $UV run python scripts/audit_quality.py --out /opt/audit.json > /opt/audit.md
touch /opt/RECHOOSE_DONE

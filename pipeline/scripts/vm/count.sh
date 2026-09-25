#!/usr/bin/env bash
# Index + sharded count on the VM. Run as root, detached:
#   sudo setsid bash count.sh </dev/null >/dev/null 2>&1 &
# Logs /opt/count.log (+ /opt/count.shardK.log); touches /opt/COUNT_DONE.
#
# NEVER `exec > >(tee log)` in a script that uses a bare `wait`: wait also
# waits on the tee process substitution and deadlocks (cost ~1h, 2026-09-24).
set -euxo pipefail
exec >>/opt/count.log 2>&1
cd /opt/moviewords/pipeline
UV=/root/.local/bin/uv
N=${N:-8}                       # one per vCPU - parsing is GIL-bound
time $UV run python -m moviewords_pipeline.cli index
pids=()
for k in $(seq 0 $((N - 1))); do
  $UV run python -u -m moviewords_pipeline.cli count --workers 2 --shard "$k/$N" \
    > "/opt/count.shard$k.log" 2>&1 &
  pids+=($!)
done
for p in "${pids[@]}"; do wait "$p"; done      # wait on the shards only
tail -qn 1 /opt/count.shard*.log
# picks up anything a shard failed, then writes word_counts / movie_stats /
# selection.parquet from the warm cache (~3 min)
time $UV run python -u -m moviewords_pipeline.cli count --workers 8
touch /opt/COUNT_DONE

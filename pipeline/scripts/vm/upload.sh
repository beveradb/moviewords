#!/usr/bin/env bash
# Publish webdata/out to R2 from the VM (additive; purges the edge cache).
# Run as root, detached:
#   sudo setsid bash upload.sh </dev/null >/dev/null 2>&1 &
# Logs /opt/upload.log; touches /opt/UPLOAD_DONE. Posters are unchanged by a
# recount and aren't on the VM, so upload_r2.sh skips them with a warning.
# ~1.5h for ~770k small files when most changed; much less otherwise.
set -euo pipefail
exec >>/opt/upload.log 2>&1
source /tmp/mw_r2.env
rclone version | head -1          # must be >= 1.65 (bootstrap.sh installs one)
cd /opt/moviewords/pipeline
time bash scripts/upload_r2.sh    # RCLONE_RETRIES=1 by default there
touch /opt/UPLOAD_DONE

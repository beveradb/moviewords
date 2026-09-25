#!/usr/bin/env bash
# Archive the VM's grown data/work to R2 (see docs/PIPELINE-RESTORE.md,
# "Refreshing the archive"). Run as root, detached:
#   sudo NAME=moviewords-work-cache-2026-09-25-fpv2 setsid bash archive.sh </dev/null >/dev/null 2>&1 &
# NAME is required - a date-only name would overwrite that day's archive.
# Logs /opt/archive.log; touches /opt/ARCHIVE_DONE once R2 has a verified copy.
set -euxo pipefail
exec >>/opt/archive.log 2>&1
: "${NAME:?set NAME}"
set +x; source /tmp/mw_r2.env; set -x
rm -f /opt/ARCHIVE_DONE
cd /opt/moviewords/data
tar -I "zstd -T0 -8" -cf "/tmp/$NAME.tar.zst" work
(cd /tmp && sha256sum "$NAME.tar.zst" > "$NAME.tar.zst.sha256")
rclone copy "/tmp/$NAME.tar.zst" r2:moviewords-pipeline-cache/
rclone copy "/tmp/$NAME.tar.zst.sha256" r2:moviewords-pipeline-cache/
rclone check "/tmp/$NAME.tar.zst" r2:moviewords-pipeline-cache/ --one-way
touch /opt/ARCHIVE_DONE

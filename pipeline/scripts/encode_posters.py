"""Encode data/out/posters/<imdb_id>.jpg to a sibling <imdb_id>.avif.

The app serves posters through <picture>: AVIF first (~45% smaller than the
TMDB w342 JPEG at q60), JPEG as the fallback, so both files are published.
Resumable: posters that already have an .avif are skipped. Requires `avifenc`
(libavif; `brew install libavif` / `apt install libavif-bin`). TMDB serves a
few posters as WebP despite the .jpg name, which avifenc can't read - those go
through ImageMagick (`magick`) to PNG first.

Every .jpg MUST get an .avif: a browser that picks the AVIF <source> does not
fall back to the JPEG on a 404, it just shows the text placeholder.

Run: cd pipeline && uv run python scripts/encode_posters.py [--quality 60] [--workers N]
"""
import argparse
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from moviewords_pipeline import config  # noqa: E402

# q60 at speed 6: visually indistinguishable from the source JPEG at poster
# display sizes; q50 started smoothing dark film-grain textures.
DEFAULT_QUALITY = 60


def pending(poster_dir):
    """JPEGs in poster_dir that have no .avif sibling yet, sorted."""
    return sorted(p for p in poster_dir.glob("*.jpg")
                  if not p.with_suffix(".avif").exists())


def avifenc_cmd(src, dst, quality=DEFAULT_QUALITY):
    # -j 1: parallelism comes from encoding many files at once, not threads
    return ["avifenc", "-q", str(quality), "-s", "6", "-j", "1", str(src), str(dst)]


def is_webp(path):
    with open(path, "rb") as f:
        head = f.read(12)
    return head[:4] == b"RIFF" and head[8:12] == b"WEBP"


def encode_one(src, quality=DEFAULT_QUALITY):
    dst = src.with_suffix(".avif")
    # avifenc infers formats from extensions, so temp files keep theirs
    tmp = src.with_name(f"{src.stem}.part.avif")
    png = src.with_name(f"{src.stem}.part.png")
    try:
        if is_webp(src):
            subprocess.run(["magick", str(src), str(png)], check=True,
                           capture_output=True)
            src_for_enc = png
        else:
            src_for_enc = src
        subprocess.run(avifenc_cmd(src_for_enc, tmp, quality), check=True,
                       capture_output=True)
        tmp.rename(dst)
        return "encoded"
    except (subprocess.CalledProcessError, OSError) as exc:  # never kill the batch
        tmp.unlink(missing_ok=True)
        print(f"avif {src.name}: {exc}", flush=True)
        return "failed"
    finally:
        png.unlink(missing_ok=True)


def encode_all(poster_dir, quality=DEFAULT_QUALITY, workers=None):
    """Encode every pending poster; returns an outcome tally. Raises if any
    poster failed, so a pipeline run can't go on to publish a JPEG whose
    AVIF is missing."""
    todo = pending(poster_dir)
    if todo and shutil.which("avifenc") is None:
        raise RuntimeError("avifenc not found - install libavif")
    tally = {}
    with ThreadPoolExecutor(max_workers=workers or os.cpu_count()) as pool:
        for i, outcome in enumerate(pool.map(lambda p: encode_one(p, quality), todo)):
            tally[outcome] = tally.get(outcome, 0) + 1
            if (i + 1) % 1000 == 0:
                print(f"{i + 1}/{len(todo)} {tally}", flush=True)
    if tally.get("failed"):
        raise RuntimeError(f"{tally['failed']} poster(s) failed to encode: {tally}")
    return tally


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, default=config.OUT_DIR / "posters")
    parser.add_argument("--quality", type=int, default=DEFAULT_QUALITY)
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args()
    print(f"done: {encode_all(args.dir, args.quality, args.workers)}")


if __name__ == "__main__":
    main()

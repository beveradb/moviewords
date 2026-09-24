"""Build + bake every MPAA rating slice (trends stage only: per-word trend JSONs,
year-totals.json, year-films.json) under webdata/out/all/rating/<code>/.
Assumes webdata/in/all/ holds the published inputs + ratings.parquet.

  uv run python scripts/bake_all_ratings.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import build_rating_slice as slice_mod  # noqa: E402
import rebuild_web_data as rwd  # noqa: E402

WEBDATA = Path(__file__).resolve().parent.parent / "webdata"


def main():
    all_in = WEBDATA / "in" / "all"
    for code in slice_mod.RATING_CODES:
        t0 = time.time()
        n = slice_mod.build_rating_slice(all_in, all_in / "rating" / code,
                                         all_in / "ratings.parquet", code)
        rwd.set_corpus("all", rating=code)
        rwd.OUT.mkdir(parents=True, exist_ok=True)
        rwd.stage_trends(rwd.connect())
        print(f"  {code}: {n} films, baked in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()

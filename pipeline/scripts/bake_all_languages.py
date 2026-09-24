"""Bake every per-language slice under webdata/out/all/lang/<code>/, then write
the languages.json manifest. Assumes the published all/ inputs are already
mirrored under webdata/in/all/ (scripts/fetch_published.sh all).

  uv run python scripts/bake_all_languages.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import build_lang_slice as slice_mod  # noqa: E402
import build_languages_manifest as manifest_mod  # noqa: E402
import rebuild_web_data as rwd  # noqa: E402

WEBDATA = Path(__file__).resolve().parent.parent / "webdata"


def option_codes(manifest: list[dict]) -> list[str]:
    return [o["code"] for o in manifest]


def main():
    all_in = WEBDATA / "in" / "all"
    manifest = manifest_mod.build(
        all_in / "movies.parquet",
        WEBDATA / "out" / "all" / "json" / "languages.json")
    codes = option_codes(manifest)
    print(f"baking {len(codes)} languages: {', '.join(codes)}")
    for code in codes:
        t0 = time.time()
        src_codes = slice_mod.CODES.get(code, [code])
        n = slice_mod.build_slice(all_in, all_in / "lang" / code, src_codes)
        rwd.set_corpus("all", lang=code)
        rwd.OUT.mkdir(parents=True, exist_ok=True)
        # "movies" (json/movie/<id>.json) and "words" (json/words/<id>.json) are
        # deliberately skipped here: films have one original_language and one
        # canonical word list, so per-film JSON stays global under all/ and is
        # never baked per language (see Global Constraints in
        # docs/superpowers/plans/2026-09-15-corpus-language-filter-pipeline.md).
        for name in rwd.STAGES:
            if name in ("movies", "words"):
                continue
            rwd.STAGES[name](rwd.connect())
        print(f"  {code}: {n} films, baked in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env bash
# Derive + stage + bake every web output from data/work, on the VM. Does NOT
# upload (see upload.sh). Run as root, detached:
#   sudo setsid bash bake.sh </dev/null >/dev/null 2>&1 &
# Logs /opt/bake.log; touches /opt/BAKE_DONE. ~75 min on n2-highmem-8
# (derive en 11 + all 16, web rebuild en 10 + all 17, languages ~15,
# ratings ~5). Every output the site reads is rebuilt - including
# year-films.json, all/rating/* and json/words/* - so a republish never
# leaves a view on stale data.
set -euxo pipefail
exec >>/opt/bake.log 2>&1
R=/opt/moviewords
cd $R/pipeline
UV=/root/.local/bin/uv
D=$R/data/out
WI=$R/pipeline/webdata/in
WO=$R/pipeline/webdata/out

time $UV run python -m moviewords_pipeline.cli derive --corpus en
time $UV run python -m moviewords_pipeline.cli derive --corpus all
$UV run python scripts/build_movies_index.py --corpus en
$UV run python scripts/build_movies_index.py --corpus all

rm -rf "$WI" "$WO"
for c in en all; do
  if [ $c = en ]; then src=$D; win=$WI; wout=$WO; else src=$D/all; win=$WI/all; wout=$WO/all; fi
  mkdir -p "$win/signature" "$wout/words_by_movie" "$wout/words_by_word"
  # rebuild_web_data inputs (the layout fetch_published.sh mirrors)
  ln -s "$src/movies.parquet" "$win/movies.parquet"
  ln -s "$src/word_year.parquet" "$win/word_year.parquet"
  ln -s "$src/words_by_movie/data.parquet" "$win/words_by_movie.parquet"
  cp "$src/json/signature/decades.json" "$src/json/signature/genres.json" "$win/signature/"
  # published parquets + derive's JSON (movie pages, boards, movies-index...)
  cp "$src/movies.parquet" "$src/word_year.parquet" "$src/word_meta.parquet" "$wout/"
  cp "$src/words_by_movie/data.parquet" "$wout/words_by_movie/"
  cp "$src/words_by_word/data.parquet" "$wout/words_by_word/"
  cp -r "$src/json" "$wout/"
done
ln -s "$D/all/word_year_lang.parquet" "$WI/all/word_year_lang.parquet"
cp "$D/all/word_year_lang.parquet" "$WO/all/"

time $UV run python scripts/rebuild_web_data.py --corpus en
time $UV run python scripts/rebuild_web_data.py --corpus all
time $UV run python scripts/bake_all_languages.py
$UV run python scripts/fetch_ratings.py --stage parquet --cache $R/data/work/tmdb_release
time $UV run python scripts/bake_all_ratings.py
du -sh "$WO"; find "$WO" -type f | wc -l
touch /opt/BAKE_DONE

from collections import Counter

from moviewords_pipeline.consensus import choose, fingerprint, gate

FILM = ("the you to a and i it of that is in what me we this he for my your "
        "on don't know right just get go here with was be have not are so "
        "cassio desdemona handkerchief moor lieutenant venice general honest").split()
OTHER = ("the you to a and i it of that is in what me we this he for my your "
         "odin hugo desi basketball coach dunk school locker gym mvp").split()


def _counts(words, n):
    """n tokens cycling through `words` (so every word has a similar count)."""
    return Counter(words[i % len(words)] for i in range(n))


def _fp(words, n, bytes_per_word=24.5):
    counts = _counts(words, n)
    return fingerprint(counts, int(n * bytes_per_word))


def _pick(cands, runtime=90):
    return choose([(name, fp) for name, fp in cands], runtime)


def test_fingerprint_fields():
    fp = _fp(FILM, 8000)
    assert fp["tokens"] == 8000
    assert 20 < fp["bytes_per_word"] < 30
    assert fp["stop_share"] > 0.4
    assert fp["commentary_rate"] == 0
    assert "the" not in fp["vec"] and "cassio" in fp["vec"]


def test_fingerprint_vec_keeps_only_the_top_content_words(monkeypatch):
    from moviewords_pipeline import config
    monkeypatch.setattr(config, "FINGERPRINT_WORDS", 3)
    fp = fingerprint(Counter({"cassio": 9, "moor": 8, "venice": 7, "iago": 1, "the": 50}), 2000)
    assert set(fp["vec"]) == {"cassio", "moor", "venice"}


def test_gate_flags_wrong_language():
    viet = Counter({"toi": 400, "khong": 330, "co": 260, "ong": 250, "the": 30})
    assert gate(fingerprint(viet, 30_000)) == "not-english"


def test_gate_flags_dense_commentary_but_not_a_film_about_films():
    talk = FILM + "movie film scene shot director actor camera".split()
    assert gate(_fp(talk, 12_000, bytes_per_word=14)) == "commentary"
    # same vocabulary at normal density: a film about film-making (a
    # Hollywood satire, a documentary) is not a commentary track
    assert gate(_fp(talk, 12_000, bytes_per_word=24)) is None


def test_gate_flags_sparse_and_tiny_files():
    assert gate(_fp(FILM, 1000, bytes_per_word=80)) == "sparse"
    assert gate(_fp(FILM, 150)) == "tiny"
    assert gate(_fp(FILM, 8000)) is None


def test_majority_beats_a_larger_wrong_film():
    """Othello 1951: the O (2001) upload is the largest file, but seven
    genuine rips agree with each other."""
    cands = [("o2001", _fp(OTHER, 9000))] + [(f"real{i}", _fp(FILM, 8000 + i)) for i in range(7)]
    name, info = _pick(cands)
    assert name.startswith("real")
    assert info["reason"] == "consensus" and info["cluster"] == 7


def test_commentary_track_is_never_picked_even_if_ranked_first():
    talk = FILM + "movie film scene shot director actor camera".split()
    cands = [("commentary", _fp(talk, 20_000, bytes_per_word=14)),
             ("rip", _fp(FILM, 9000))]
    name, info = _pick(cands)
    assert name == "rip"
    assert info["rejected"] == {"commentary": "commentary"}


def test_most_typical_length_wins_inside_the_cluster():
    """A doubled file and a partial rip have the same content as the real
    rips - pick the one nearest the cluster's median length."""
    cands = [("double", _fp(FILM, 16_000)), ("full_a", _fp(FILM, 8100)),
             ("full_b", _fp(FILM, 8000)), ("full_c", _fp(FILM, 7900)),
             ("partial", _fp(FILM, 3000))]
    name, _ = _pick(cands)
    assert name == "full_b"


def test_ties_break_by_rank_order():
    cands = [("first", _fp(FILM, 8000)), ("second", _fp(FILM, 8000))]
    assert _pick(cands)[0] == "first"


def test_no_agreement_falls_back_to_rank_order():
    """Three independent translations that don't agree: no majority to
    follow, so the size ranking decides."""
    a = "the you to a and i arvind liyana doctor aunt power leave".split()
    b = "the you to a and i aravind liya love brother girl want".split()
    c = "the you to a and i rama sita village temple king war".split()
    name, info = _pick([("a", _fp(a, 7000)), ("b", _fp(b, 7000)), ("c", _fp(c, 7000))])
    assert name == "a" and info["reason"] == "rank"


def test_two_disagreeing_files_take_the_rank_first_usable_one():
    name, info = _pick([("x", _fp(OTHER, 9000)), ("y", _fp(FILM, 8000))])
    assert name == "x" and info["reason"] == "rank"


def test_single_file_is_taken():
    name, info = _pick([("only", _fp(FILM, 5000))])
    assert name == "only" and info["reason"] == "single"


def test_gates_relax_when_every_file_fails_them():
    """Musicals are sparse in every file (lyrics are stripped) - keep one."""
    cands = [("a", _fp(FILM, 2000, bytes_per_word=90)), ("b", _fp(FILM, 1500, bytes_per_word=95))]
    name, info = _pick(cands)
    assert name == "a" and info["relaxed"] is True


def test_nothing_parseable_returns_none():
    assert _pick([("empty", fingerprint(Counter(), 5000))]) == (None, {"reason": "none"})


def test_doubled_pick_swaps_for_its_half_size_twin():
    """Two-file cluster of a double + its single copy: the median can't
    separate them, so the > MAX_COUNTED_WPM guard does."""
    cands = [("double", _fp(FILM, 30_000)), ("single", _fp(FILM, 15_000))]
    name, info = _pick(cands, runtime=100)
    assert name == "single" and info["reason"] == "doubled"

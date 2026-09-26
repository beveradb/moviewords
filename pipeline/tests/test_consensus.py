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


def _translation(extra, n=8000):
    """A distinct translation of the same film: FILM plus its own wording
    (content cosine to other translations ~0.9 - agrees, but not a copy)."""
    return _fp(FILM + extra.split(), n)


def test_identical_copies_of_a_wrong_file_count_as_one_vote():
    """Baahubali 2: three identical uploads of an unrelated film must not
    outvote genuine translations that merely agree with each other."""
    from moviewords_pipeline.consensus import cosine
    genuine = [_translation("mother"), _translation("mahishmati"),
               _translation("devasena")]
    assert all(0.85 <= cosine(a["vec"], b["vec"]) < 0.98
               for a in genuine for b in genuine if a is not b)
    wrong = [_fp(OTHER, 8700) for _ in range(3)]
    cands = [(f"wrong{i}", fp) for i, fp in enumerate(wrong)] + \
            [(f"real{i}", fp) for i, fp in enumerate(genuine)]
    name, info = _pick(cands)
    assert name.startswith("real") and info["cluster"] == 3


def test_identical_genuine_reuploads_beat_a_single_wrong_file():
    """Nothing agrees across texts, but the genuine text has 4 uploads."""
    cands = [("wrong", _fp(OTHER, 9000))] + [(f"real{i}", _fp(FILM, 8000)) for i in range(4)]
    name, info = _pick(cands)
    assert name.startswith("real") and info["reason"] == "consensus"


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


# --- v3: hard gates, quality flags, tiers ----------------------------------

def _q(**over):
    """Quality features of an ordinary, human-made subtitle file."""
    q = {"toks_per_line": 5.2, "cap_start": 0.98, "end_punct": 0.97, "mt": 0,
         "style": {}}
    return q | over


def _qfp(words, n, **q):
    fp = _fp(words, n)
    fp["q"] = _q(**q)
    return fp


ASR = {"toks_per_line": 22.0, "cap_start": 0.4, "end_punct": 0.2}


def test_film_about_film_making_keeps_its_commentary_like_files():
    """Every file reads as commentary: in practice a documentary about film
    (Life Itself, QT8, Milius) whose real dialogue is dense film talk -
    kept, as the gates relax."""
    talk = FILM + "movie film scene shot director actor camera".split()
    name, info = _pick([("a", _fp(talk, 20_000, bytes_per_word=14)),
                        ("b", _fp(talk, 20_100, bytes_per_word=14))])
    assert name == "a" and info["relaxed"] is True and info["tier"] == "ok"


def test_auto_captions_lose_to_a_human_file():
    cands = [("asr", _qfp(FILM, 9000, **ASR)), ("human", _qfp(FILM, 8000))]
    name, info = _pick(cands)
    assert name == "human" and info["tier"] == "ok" and info["flags"] == []
    assert info["flagged"] == {"asr": ["asr"]}


def test_only_auto_captions_keeps_the_film_at_low_tier():
    name, info = _pick([("asr", _qfp(FILM, 9000, **ASR))])
    assert name == "asr" and info["tier"] == "low" and info["flags"] == ["asr"]


def test_opus_machine_translated_flag_is_a_quality_flag():
    name, info = _pick([("mt", _qfp(FILM, 9000, mt=1))])
    assert info["tier"] == "low" and info["flags"] == ["machine-translated"]


def test_every_agreeing_file_machine_translated_is_low_tier():
    """tt1027683: six uploads of one machine translation agree with each
    other - consensus can't vouch for them."""
    cands = [(f"mt{i}", _qfp(FILM, 8000 + i, mt=1)) for i in range(6)]
    name, info = _pick(cands)
    assert info["reason"] == "consensus" and info["tier"] == "low"


def test_wrong_cast_file_loses_to_one_naming_the_characters():
    """Lady Luck 1946: two identical uploads of a modern film beat the one
    genuine file on the files tie-break; the genuine one names the cast."""
    film = {"cast": frozenset({"cassio", "desdemona", "moor", "venice"}), "english": True}
    cands = [("wrong_a", _qfp(OTHER, 9000)), ("wrong_b", _qfp(OTHER, 9000)),
             ("real", _qfp(FILM, 8000))]
    name, info = choose(cands, 90, film)
    assert name == "real" and info["tier"] == "ok"
    assert info["flagged"] == {"wrong_a": ["wrong-cast"], "wrong_b": ["wrong-cast"]}


def test_naming_none_of_the_cast_is_no_evidence_on_its_own():
    """Narrated films (Stereo), unnamed characters, TMDB role descriptions:
    a lone file that names none of the cast is kept at tier ok."""
    film = {"cast": frozenset("brabantio cassio desdemona lodovico roderigo".split()),
            "english": True}
    name, info = choose([("only", _qfp(OTHER, 9000))], 90, film)
    assert info["tier"] == "ok" and info["flags"] == []


def test_style_model_only_judges_english_original_films(monkeypatch):
    """Human translations of foreign films read as 'translationese' to the
    style model (Ben and Charlie scored 0.999) - only OPUS's own flag
    counts for them."""
    from moviewords_pipeline import quality
    monkeypatch.setattr(quality, "mt_score", lambda q, tokens: 0.99)
    cands = [("only", _qfp(FILM, 9000))]
    assert choose(cands, 90, {"english": True})[1]["flags"] == ["machine-translated"]
    assert choose(cands, 90, {"english": False})[1]["tier"] == "ok"
    assert choose(cands, 90, None)[1]["tier"] == "ok"
    flagged_by_opus = [("only", _qfp(FILM, 9000, mt=1))]
    assert choose(flagged_by_opus, 90, {"english": False})[1]["tier"] == "low"


def test_fingerprints_without_quality_features_are_never_flagged():
    name, info = _pick([("old", _fp(FILM, 9000))])
    assert info["tier"] == "ok" and info["flags"] == []


def test_near_wordless_film_keeps_its_tiny_file():
    """Silent Movie (1976) says one word; every upload is tiny."""
    name, info = _pick([("a", _fp(["non"], 3)), ("b", _fp(["non"], 3))])
    assert name == "a" and info["relaxed"] is True and info["tier"] == "ok"


def test_profanity_in_a_production_code_era_film_is_an_anachronism():
    """Showdown (1963): "Tell your fucking dogs to don't get too close." -
    a re-translation. Distant Drums, Reefer Madness: the same."""
    film = {"english": True, "year": 1963, "documentary": False}
    swears = _qfp(FILM, 9000, profanity={"fucking": 1})
    clean = _qfp(FILM, 8000)
    name, info = choose([("swears", swears), ("clean", clean)], 90, film)
    assert name == "clean" and info["flagged"] == {"swears": ["anachronism"]}
    assert choose([("swears", swears)], 90, film)[1]["flags"] == ["anachronism"]


def test_profanity_is_no_anachronism_in_documentaries_later_films_or_translations():
    """Portrait of Jason, Warrendale (1967 documentaries), Chelsea Girls
    (1966): genuine. A translated film's subtitle words aren't its own."""
    swears = [("only", _qfp(FILM, 9000, profanity={"fuck": 3, "shit": 2}))]
    for film in ({"english": True, "year": 1963, "documentary": True},
                 {"english": True, "year": 1966, "documentary": False},
                 {"english": False, "year": 1950, "documentary": False}):
        assert choose(swears, 90, film)[1]["tier"] == "ok", film
    mild = [("only", _qfp(FILM, 9000, profanity={"damn": 4, "hell": 2}))]
    assert choose(mild, 90, {"english": True, "year": 1950})[1]["tier"] == "ok"


def test_shit_is_an_anachronism_in_a_production_code_era_film_too():
    """Passage to Marseille (1944): two uploads have "ANOTHER! / SHIT." where
    the other three have "Another! / Hi, Grand-Pere." (a transcription slip)."""
    film = {"english": True, "year": 1944, "documentary": False}
    slip = _qfp(FILM, 9000, profanity={"shit": 1})
    clean = _qfp(FILM, 8900)
    name, info = choose([("slip", slip), ("clean", clean)], 90, film)
    assert name == "clean" and info["flagged"] == {"slip": ["anachronism"]}


def test_verified_genuine_profanity_is_no_anachronism():
    """The Connection (1961): read line by line, genuine - its "shit" (heroin
    slang) is why New York's censors banned it."""
    film = {"english": True, "year": 1961, "documentary": False, "profanity_verified": True}
    only = [("only", _qfp(FILM, 9000, profanity={"shit": 9, "bullshit": 1}))]
    assert choose(only, 90, film)[1]["tier"] == "ok"


def test_chosen_files_full_counts_catch_family_words_the_fingerprint_lacks():
    """Tripoli (1950): "shithead" isn't on the published profanity list, so
    only the chosen file's full counts show it."""
    from moviewords_pipeline.consensus import check_chosen_counts
    film = {"english": True, "year": 1950, "documentary": False}
    info = {"tier": "ok", "flags": []}
    info = check_chosen_counts(info, {"shithead": 1, "the": 50}, film)
    assert info["tier"] == "low" and info["flags"] == ["anachronism"]
    ok = check_chosen_counts({"tier": "ok", "flags": []}, {"shithead": 1},
                             film | {"profanity_verified": True})
    assert ok["tier"] == "ok"

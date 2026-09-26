from scripts_path import add_scripts_to_path  # noqa: F401


def test_file_naming_another_films_cast_is_a_hit():
    """Daddy-Long-Legs (1919) carried Ah! My Goddess: The Movie."""
    import scan_cast_crossfilm as s
    casts = {"tt0010040": {"judy", "jervis", "pendleton"},
             "tt0270128": {"belldandy", "keiichi", "urd", "skuld"}}
    vecs = {"tt0010040": {"belldandy": 40, "keiichi": 30, "skuld": 12, "moon": 9},
            "tt0270128": {"belldandy": 41, "keiichi": 29, "urd": 10}}
    hits = s.scan(vecs, casts)
    assert [(h["imdb_id"], h["other_id"], h["other"]) for h in hits] == [
        ("tt0010040", "tt0270128", 3)]


def test_common_words_and_shared_names_are_not_evidence():
    """"frank"/"grace" are English words; a name in many cast lists (john,
    mary...) says nothing; a file naming its own cast is never a hit."""
    import scan_cast_crossfilm as s
    many = {f"tt{i:07d}": {"jervis"} for i in range(5)}
    casts = {"tt0000100": {"frank", "grace", "hope", "keiichi2"},
             "tt0000200": {"zorblax"}, **many}
    vecs = {"tt0000200": {"frank": 9, "grace": 5, "hope": 4, "jervis": 3},
            "tt0000100": {"keiichi2": 5, "zorblax": 4}}
    assert s.scan(vecs, casts, min_other=1) == []

from pathlib import Path

from moviewords_pipeline.subtitle_parser import extract_text

FIX = Path(__file__).parent / "fixtures"


def _xml(*cues):
    body = "".join(f"<s id='{i}'>{cue}</s>" for i, cue in enumerate(cues, 1))
    return f"<?xml version='1.0' encoding='utf-8'?><document>{body}</document>".encode()


def test_extracts_dialogue_lines():
    text = extract_text((FIX / "sub_basic.xml").read_bytes())
    assert "Quarter Pounder" in text
    assert "Royale with Cheese" in text
    assert "00:00" not in text  # no timestamps


def test_strips_noise():
    text = extract_text((FIX / "sub_noisy.xml").read_bytes())
    assert "<i>" not in text and "Previously on the show" in text
    assert "Subtitles by" not in text          # credit lines dropped
    assert "corrections by" not in text
    assert "door slams" not in text            # SDH cues dropped
    assert "la la la" not in text              # song lines dropped
    assert "Hello there" in text and "General Kenobi" in text


def test_malformed_xml_returns_empty():
    assert extract_text(b"<document><s>broken") == ""


def test_credit_regex_does_not_drop_dialogue_containing_sync_and_by():
    # "sync(ed)?\b.*\bby" used to greedily match any line with both words
    # anywhere in it, even unrelated dialogue. Only credit-style phrasing
    # ("Sync ... by NAME") should be dropped.
    text = extract_text(
        _xml("The clocks are all in sync, driven by an atomic clock.")
    )
    assert "clocks are all in sync" in text


def test_credit_regex_still_drops_sync_credit_line():
    text = extract_text(_xml("Sync and corrections by srjanapala"))
    assert "srjanapala" not in text
    assert text == ""


def test_music_regex_does_not_drop_dialogue_containing_hash():
    # Bare "#" used to be treated as a music marker anywhere in the line,
    # dropping ordinary dialogue that happens to include a number sign.
    text = extract_text(_xml("She lives in Suite #300."))
    assert "Suite #300" in text


def test_music_regex_drops_line_starting_with_hash_marker():
    # The srt convention "# la la #" uses a leading "#" as a music cue.
    text = extract_text(_xml("# la la #"))
    assert text == ""


def test_parenthetical_cue_removed_but_surrounding_dialogue_kept():
    text = extract_text(_xml("I have (some) doubts"))
    assert text == "I have doubts"


def test_leading_parenthetical_cue_removed_dialogue_kept():
    text = extract_text(_xml("(sighs) Fine."))
    assert text == "Fine."


def test_multi_speaker_dash_normalized_to_space():
    text = extract_text(_xml("- Hello there.\n- General Kenobi!"))
    assert text == "Hello there. General Kenobi!"


def test_hyphenated_word_untouched_by_dash_normalization():
    text = extract_text(_xml("It's a well-known fact - trust me."))
    assert text == "It's a well-known fact trust me."


def test_ssa_override_blocks_are_stripped():
    """SSA/ASS styling survives OPUS conversion as literal text ({\\cHFFFFFF}
    became the token "chffffff"; {\\fad(..)} "fad"; {\\pos(..)} "pos")."""
    text = extract_text(_xml(r"and scenes some {\cHFFFFFF}viewers may find",
                             r"{\fad(250,250)}Anna, wait!",
                             r"{\an1\pos(206,432)}Come here."))
    assert text == "and scenes some viewers may find\nAnna, wait!\nCome here."


def test_mangled_font_tags_and_nbsp_are_stripped():
    """OPUS drops the angle brackets of broken HTML tags, leaving
    `font color = "# 00ff00"` and entity names like nbsp as plain words."""
    text = extract_text(_xml('font color = "# 00ff00"  Anywhere in North East Syria.',
                             "font color=#ffff00 Four o'clock. /font",
                             "nbsp", "Really?&amp;nbsp;"))
    assert text == "Anywhere in North East Syria.\nFour o'clock.\nReally?"


def test_the_word_font_in_dialogue_survives():
    assert extract_text(_xml("Change the font, it's too small.")) == \
        "Change the font, it's too small."


def test_entity_stripping_keeps_amp_and_ocr_lt():
    assert extract_text(_xml("Turn the amp up. lt's fine &amp;quot;ok&amp;quot;")) == \
        "Turn the amp up. lt's fine ok"

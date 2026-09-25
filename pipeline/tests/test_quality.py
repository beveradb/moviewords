from collections import Counter

from moviewords_pipeline import quality
from moviewords_pipeline.wordcount import count_words_repaired


def _xml(sentences, meta=""):
    body = "".join(f'<s id="{i}"><w>{s}</w></s>' for i, s in enumerate(sentences, 1))
    return f'<?xml version="1.0" encoding="utf-8"?><document>{body}{meta}</document>'.encode()


def _features(text, raw=b"<document/>"):
    counts, repaired = count_words_repaired(text)
    return quality.features(raw, text, counts, repaired), sum(counts.values())


HUMAN = [
    "Where are you going?", "I don't know.", "It's late, Frank.",
    "You can't just leave.", "Watch me.", "There's nothing left here for me.",
    "- Frank!", "- What?", "I'm sorry.", "Don't be.",
] * 40

ASR = [
    "well now what would I do in Arizona oh lots of things he's very beautiful "
    "why don't you come alone I think you'd like it there",
    "you're the commanding officer Frank won't Bob get a kick though when he "
    "hears about this do you know what I think I'll do",
] * 60

MT = [
    "I do not know what you want of me.", "Did not you see her?",
    "It is not possible, she will not come.", "Do not forget, though, that there are men.",
    "We will see what he will do.", "But I am not afraid of these men.",
    "Give me and the cattle, you have to hurry up too!", "I will not go there, it is late.",
] * 40


def test_features_shape_of_human_subtitles():
    q, _ = _features("\n".join(HUMAN))
    assert q["toks_per_line"] < 6
    assert q["cap_start"] > 0.9 and q["end_punct"] > 0.9
    assert not quality.is_asr(q)


def test_features_flag_auto_captions():
    q, _ = _features("\n".join(ASR))
    assert q["toks_per_line"] > 18
    assert quality.is_asr(q)


def test_style_counts_function_words_and_contractions():
    q, _ = _features("\n".join(HUMAN))
    assert q["style"]["you"] > 0
    assert q["style"]["*n't"] == 3 * 40   # don't, can't, don't
    assert q["style"]["*'s"] == 2 * 40    # it's, there's
    assert "frank" not in q["style"]      # names are not style words


def test_mt_score_separates_machine_translated_from_human_dialogue():
    human, n_human = _features("\n".join(HUMAN))
    mt, n_mt = _features("\n".join(MT))
    assert quality.mt_score(mt, n_mt) > 0.7
    assert quality.mt_score(human, n_human) < 0.3


def test_mt_score_is_none_for_short_files():
    q, n = _features("\n".join(MT[:8]))
    assert quality.mt_score(q, n) is None


def test_machine_translated_flag_from_opus_meta():
    flagged = _xml(["Hi."], "<meta><subtitle><machine_translated>1</machine_translated></subtitle></meta>")
    clean = _xml(["Hi."], "<meta><subtitle><machine_translated>0</machine_translated></subtitle></meta>")
    assert quality.machine_translated_flag(flagged) == 1
    assert quality.machine_translated_flag(clean) == 0
    assert quality.machine_translated_flag(_xml(["Hi."], "<meta><subtitle/></meta>")) is None
    assert quality.machine_translated_flag(_xml(["Hi."])) is None


def test_features_measure_debris_and_ocr_repairs():
    q, _ = _features("Já vÃ©m. Что это? l'm here. lt's ok. l'll go. lf so.")
    assert q["non_latin_k"] > 0 and q["mojibake_k"] > 0
    assert q["ocr_repaired_k"] > 0


def test_features_are_json_serialisable():
    import json
    q, _ = _features("\n".join(HUMAN))
    json.dumps(q)
    assert isinstance(q["style"], dict) and Counter(q["style"])


def test_features_count_profanity_per_file():
    q, _ = _features("Fuck the cow yellow. Oh, shit. Hello there.")
    assert q["profanity"] == {"fuck": 1, "shit": 1}

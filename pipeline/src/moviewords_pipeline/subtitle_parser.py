import re
from xml.etree import ElementTree

TAG_RE = re.compile(r"<[^>]+>")

# Styling that survives OPUS conversion as literal text: SSA/ASS override
# blocks ({\cHFFFFFF}, {\fad(250,250)}, {\an1\pos(206,432)}) and HTML font
# tags whose angle brackets were dropped (`font color = "# 00ff00"`,
# `/font`). Left in, they count as words (chffffff, fad, pos). A font tag
# needs an attribute, so the dialogue word "font" survives.
SSA_RE = re.compile(r"\{\\[^}]*\}")
FONT_RE = re.compile(
    r"(?<![\w/])/?font(?:\s+(?:color|face|size)\s*=\s*(?:\"[^\"]*\"|'[^']*'|\S+))+"
    r"|(?<![\w])/font\b",
    re.IGNORECASE)
# HTML entities left as text. Only "nbsp" is safe to drop as a bare word -
# "amp" is a word and OCR'd files write "It's" as "lt's".
ENTITY_RE = re.compile(r"&(?:nbsp|amp|quot|lt|gt|#\d+);|\bnbsp\b", re.IGNORECASE)

# Cue delimiters: SDH subtitles use both (SIGHS)/(door slams) and [door slams]
# to mark non-dialogue cues. Parentheses are also occasionally used for
# genuine dialogue asides (e.g. "I have (some) doubts"), but across hundreds
# of thousands of real-world subtitle files, parenthetical content is far
# more often an SDH cue than dialogue worth keeping. We deliberately strip
# both bracket styles, accepting the rare loss of a parenthetical aside as
# the price of reliably dropping cues.
BRACKET_RE = re.compile(r"[\[(][^\])]*[\])]")   # [door slams], (sighs)

CREDIT_RE = re.compile(
    r"subtitles?\s+by|subs\s+by|"
    # Bounded + anchored so we only match credit-style phrasing like
    # "Sync(ed) ... by NAME" at the start of a line, not any dialogue that
    # happens to contain both "sync" and "by" (e.g. "in sync, driven by").
    r"^\s*sync\w*\b.{0,20}?\bby\b|"
    r"corrections?\s+by|"
    r"encoded\s+by|opensubtitles|addic7ed|www\.|https?://",
    re.IGNORECASE,
)

# ♪/♫ are unambiguous song markers wherever they appear. A bare "#" is only
# a music marker under the srt convention of a line starting with "#" (e.g.
# "# la la #") — matching "#" anywhere would drop ordinary dialogue like
# "Suite #300".
MUSIC_RE = re.compile(r"[♪♫]|^\s*#")

# Embedded multi-speaker dashes ("- Hello there. - General Kenobi!") should
# collapse to a single space once lines are joined, but hyphenated compound
# words (e.g. "well-known") must be left alone. A dash only counts as a
# speaker separator when preceded by whitespace or the start of the line.
DASH_SEP_RE = re.compile(r"(?:^|\s)-\s+")


def extract_text(xml_bytes):
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError:
        return ""
    lines = []
    for s in root.iter("s"):
        raw = " ".join("".join(s.itertext()).split())
        raw = TAG_RE.sub(" ", raw)          # literal <i> etc. embedded as text
        raw = SSA_RE.sub(" ", raw)
        raw = FONT_RE.sub(" ", raw)
        raw = ENTITY_RE.sub(" ", raw)
        if CREDIT_RE.search(raw) or MUSIC_RE.search(raw):
            continue
        raw = BRACKET_RE.sub(" ", raw)
        raw = DASH_SEP_RE.sub(" ", raw)
        raw = " ".join(raw.split())         # collapse whitespace left behind
        if raw:
            lines.append(raw)
    return "\n".join(lines)

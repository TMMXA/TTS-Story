"""CJK-aware, source-preserving text budgets, without tokenizer dependencies."""
from __future__ import annotations

import bisect
import re

# Han (including supplementary extensions), Japanese kana, Korean syllables/jamo.
CJK_CHAR_CLASS = (
    '\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff'
    '\U00020000-\U000323af\u3040-\u30ff\u31f0-\u31ff'
    '\u1100-\u11ff\u3130-\u318f\ua960-\ua97f\uac00-\ud7af'
)
CJK_RE = re.compile(f'[{CJK_CHAR_CLASS}]')
UNIT_RE = re.compile(f'[{CJK_CHAR_CLASS}]|[^\\s{CJK_CHAR_CLASS}]+')
SENTENCE_END_RE = re.compile(r'[。！？；.!?;]+[”’"\')\]]*|…{2,}[”’"\')\]]*')


def contains_cjk(text: str) -> bool:
    return bool(CJK_RE.search(text or ''))


def _units(text: str):
    # Punctuation alone between Han characters should not consume a word unit.
    return (m for m in UNIT_RE.finditer(text) if any(c.isalnum() for c in m.group()))


def count_text_units(text: str) -> int:
    """Count one unit per CJK character, plus whitespace-separated other words."""
    return sum(1 for _ in _units(text or ''))


def chunk_text_units(text: str, max_units: int = 4000) -> list[str]:
    """Split at paragraphs, then sentences, then unit boundaries.

    Joining the result exactly reconstructs the input, including all separators.
    Each chunk has at most max_units; an English word is never cut in half.
    """
    if not text:
        return []
    budget = max(1, int(max_units))
    starts = [m.start() for m in _units(text)]
    if len(starts) <= budget:
        return [text]
    paragraph_re = re.compile(r'\r?\n+' if contains_cjk(text) else r'\r?\n\s*\r?\n+')
    paragraphs = [m.end() for m in paragraph_re.finditer(text)]
    sentences = [m.end() for m in SENTENCE_END_RE.finditer(text)]
    result = []
    start = 0
    unit_index = 0
    while unit_index + budget < len(starts):
        limit = starts[unit_index + budget]
        end = None
        for boundaries in (paragraphs, sentences):
            index = bisect.bisect_right(boundaries, limit) - 1
            if (index >= 0 and boundaries[index] > start
                    and bisect.bisect_left(starts, boundaries[index]) - unit_index >= max(1, budget // 4)):
                end = boundaries[index]
                break
        end = end or limit
        result.append(text[start:end])
        start = end
        unit_index = bisect.bisect_left(starts, start)
    if start < len(text):
        result.append(text[start:])
    return result

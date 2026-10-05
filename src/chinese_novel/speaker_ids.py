"""Speaker tag grammar shared by parsing, repair and profile extraction.

IDs contain Unicode alphanumeric characters, underscores and hyphens, and
start with a non-decimal alphanumeric character. Numeric citations such as
``[1]`` are intentionally excluded. JS mirrors this with Unicode properties.
"""
import re
import unicodedata
from bisect import bisect_right

SPEAKER_NAME_PATTERN = r'[^\W\d_][\w-]*'
SPEAKER_BLOCK_PATTERN = rf'\[({SPEAKER_NAME_PATTERN})\](.*?)\[/\1\]'
TAG_PATTERN = rf'\[(/?)({SPEAKER_NAME_PATTERN})\]'


class SpeakerBlockSlices:
    """Keep slices parseable when a chapter boundary falls inside a speaker.

    The source is never edited. Only the sliced section receives the missing
    opening/closing tag and its existing delivery instruction. Binary lookup
    keeps section construction bounded for manuscripts with many blocks.
    """
    def __init__(self, source):
        self.source = source
        self.blocks = [m for m in re.finditer(SPEAKER_BLOCK_PATTERN, source, re.S | re.I)
                       if m[1].lower() not in {'direction', 'emotion'}]
        self.starts = [m.start(2) for m in self.blocks]

    def _at(self, offset, closing=False):
        index = bisect_right(self.starts, offset) - 1
        if index < 0:
            return None
        block = self.blocks[index]
        if (block.start(2) < offset <= block.end(2) if closing
                else block.start(2) <= offset < block.end(2)):
            return block
        return None

    def slice(self, start, end):
        value = self.source[start:end].strip()
        if not value:
            return value
        opening, closing = self._at(start), self._at(end, closing=True)
        if opening:
            direction = re.search(
                r'\[(direction|emotion)\](?:(?!\[/?(?:direction|emotion)\]).)*'
                r'\[/\1\]\s*$', self.source[:opening.start()], re.S | re.I,
            )
            value = (direction[0] if direction else '') + f'[{opening[1]}]' + value
        if closing:
            value += f'[/{closing[1]}]'
        return value


def normalize_speaker_id(value):
    """Preserve Unicode names while formatting a user-entered tag ID."""
    value = unicodedata.normalize('NFC', str(value or '')).strip().lower()
    value = re.sub(r'\s+', '-', value)
    value = re.sub(r'[^\w-]', '', value)
    value = re.sub(r'-+', '-', value).strip('-')
    return value if re.fullmatch(SPEAKER_NAME_PATTERN, value) else ''

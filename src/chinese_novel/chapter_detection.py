"""Line-anchored Chinese chapter headings, independent of English keywords."""
import re

CHINESE_CHAPTER_LABEL = '第*章'
_NUMBER = r'[0-9０-９〇零一二三四五六七八九十百千万两]+'
_HEADING = rf'第[ \t\u3000]*{_NUMBER}[ \t\u3000]*章(?=$|[ \t\u3000:：.．、—\-*]|\[/)[^\r\n]*'
_LINE = re.compile(rf'^[ \t\u3000]*({_HEADING})[ \t\u3000]*$')
_TAGGED_LINES = re.compile(
    rf'^\s*(?:\[[^\]\r\n]+\]\s*)*({_HEADING})\r?$', re.MULTILINE,
)
_INDEX = re.compile(rf'^第[ \t\u3000]*({_NUMBER})[ \t\u3000]*章')


def detect_heading(line):
    """Return the complete title and numbering for one plain heading line."""
    match = _LINE.fullmatch((line or '').strip())
    if not match:
        return None
    title = match[1].strip()
    return {'matched': True, 'type': 'chapter', 'language': 'zh',
            'index_text': _INDEX.match(title)[1], 'title': title}


def find_chinese_heading_matches(text):
    """Match source offsets, including markup prefixes accepted by sectioning."""
    return list(_TAGGED_LINES.finditer(text or ''))


def chinese_chapters_enabled(headings):
    """Old projects with Chapter selected gain Chinese support automatically."""
    return headings is None or any(str(h).lower() in {'chapter', CHINESE_CHAPTER_LABEL} for h in headings)

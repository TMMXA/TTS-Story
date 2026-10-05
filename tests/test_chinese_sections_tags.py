"""Chinese chapters and speaker IDs must survive the entire shared text path."""
import pytest

from src.tag_validation import tag_errors
from src.tag_validator import normalize_speaker_name, suggest_speaker_mapping, validate_and_fix_tags
from src.text_processor import TextProcessor


@pytest.mark.parametrize('name', ['旁白', '叶临渊', '林黛玉', 'Élise', 'alice-female', '角色_2', 'Ⅷ', '³号'])
def test_unicode_ids_are_detected_parsed_and_validated(name):
    text = f'[direction]轻声、克制。[/direction][{name}]“别来无恙。”[laugh][1][/{name}]'
    assert not tag_errors(text)
    processor = TextProcessor()
    assert processor.extract_speakers(text) == [name.lower()]
    segments = processor.parse_speaker_segments(text)
    assert segments[0]['speaker'] == name.lower()
    assert segments[0]['delivery_instruction'] == '轻声、克制。'
    assert segments[0]['text'] == '“别来无恙。”[laugh][1]'


def test_chinese_unbalanced_tags_are_visible_and_repair_offsets_do_not_drift():
    text = '[叶临渊]第一句。[/direction][林清雪]第二句。[/direction]'
    assert len(tag_errors(text)) == 2
    fixed, changes = validate_and_fix_tags(text)
    assert fixed == '[叶临渊]第一句。[/叶临渊][林清雪]第二句。[/林清雪]'
    assert len(changes) == 2
    assert not tag_errors(fixed)


def test_chinese_names_never_collapse_to_same_empty_alias():
    assert normalize_speaker_name('叶临渊') == '叶临渊'
    assert normalize_speaker_name('林清雪') == '林清雪'
    assert suggest_speaker_mapping(['叶临渊'], ['林清雪']) == {}


@pytest.mark.parametrize('heading', [
    '第一章', '第1章', '第１２章', '第十二章', '第一百零二章',
    '第一千零二章', '第 12 章', '第12章 风雪', '第12章：风雪', '第两百章 夜雨',
])
def test_chinese_heading_detector_and_shared_pipeline(heading):
    from src.chinese_novel.chapter_detection import detect_heading
    from app import split_text_into_book_sections, build_gemini_sections
    assert detect_heading(heading)['title'] == heading
    text = f'{heading}\n他推开了门。\n\n第二百零三章 夜雨\n她走进屋里。'
    sections = split_text_into_book_sections(text, ['chapter'])['sections']
    prep = build_gemini_sections(text, True, {'llm_local_chunk_size': 4000}, ['chapter'])
    assert [s['title'] for s in sections] == [heading, '第二百零三章 夜雨']
    assert [s['title'] for s in prep] == [s['title'] for s in sections]


@pytest.mark.parametrize('line', ['他翻到了第十二章。', '这是第12章里的内容。', '第十二章节的故事。'])
def test_chinese_prose_is_not_a_heading(line):
    from src.chinese_novel.chapter_detection import detect_heading
    assert detect_heading(line) is None


def test_chinese_selection_can_be_disabled_and_directed_boundaries_stay_balanced():
    from app import split_text_into_book_sections
    text = '\n'.join(f'[direction]轻声。[/direction]\n[旁白]\n第{i}章 风雪\n正文{i}。[/旁白]' for i in range(1, 4))
    sections = split_text_into_book_sections(text, ['第*章'])['sections']
    assert len(sections) == 3
    for section in sections:
        assert not tag_errors(section['content'])
        assert TextProcessor().parse_speaker_segments(section['content'])[0]['delivery_instruction'] == '轻声。'
    assert split_text_into_book_sections(text, [])['kind'] == 'none'


def test_chinese_profile_excerpts_and_directed_lock_preserve_ids_and_prose():
    from app import build_speaker_profile_excerpts
    from src.directed_output import lock_manuscript
    text = '[叶临渊]“别来无恙。”[/叶临渊]\n[旁白]他望着她。[/旁白]'
    assert 'Excerpts: “别来无恙。”' in build_speaker_profile_excerpts(text, ['叶临渊'])
    assert [b['speaker'] for b in lock_manuscript(text)['blocks']] == ['叶临渊', '旁白']


def test_crlf_chapter_offsets_point_to_original_source_and_titles_preserve_punctuation():
    from app import split_text_into_sections
    text = '扉页。\r\n\r\n  第１２章：风雪******\r\n正文。\r\n\r\n第十三章 山雨\r\n他来了。'
    sections = split_text_into_sections(text)
    assert [s['title'] for s in sections] == ['Title', '第１２章：风雪', '第十三章 山雨']
    for section in sections[1:]:
        assert text[section['heading_start']:section['heading_end']].strip() == section['heading']


def test_custom_marker_overlap_does_not_duplicate_chinese_chapter_boundary():
    from app import split_text_into_sections
    text = '第一章 风雪\n正文。\n第二章 夜雨\n正文。'
    assert len(split_text_into_sections(text, ['第', '第*章'])) == 2


def test_numeric_citations_are_not_locked_speaker_ids():
    from src.directed_output import lock_manuscript
    from src.structured_output import StructuredOutputError
    with pytest.raises(StructuredOutputError):
        lock_manuscript('[1]正文。[/1]')


def test_existing_case_insensitive_id_validation_agrees_with_parser_and_profiles():
    from app import build_speaker_profile_excerpts
    text = '[ÉLISE]她来了。[/élise]'
    assert not tag_errors(text)
    assert TextProcessor().parse_speaker_segments(text)[0]['speaker'] == 'élise'
    assert 'Excerpts: 她来了。' in build_speaker_profile_excerpts(text, ['élise'])


def test_profile_endpoint_reports_missing_chinese_name_instead_of_matching_empty_ids(monkeypatch):
    import app
    monkeypatch.setattr(app, 'load_config', lambda: {
        'llm_provider': 'local', 'gemini_speaker_profile_prompt': 'Analyze the speaker.',
    })
    monkeypatch.setattr(app, '_run_llm_prompt_with_failover', lambda *_: (
        '| Character Name | Full Description | Voice Type |\n| --- | --- | --- |\n'
        '| 叶临渊 | 年轻男子，沉稳内敛。 | 低沉男声 |',
        {'id': 'primary', 'provider': 'local', 'model': 'test'}, [],
    ))
    response = app.app.test_client().post('/api/gemini/speaker-profiles', json={
        'speakers': ['叶临渊', '林清雪'],
        'processed_text': '[叶临渊]原文。[/叶临渊][林清雪]另一句。[/林清雪]',
    })
    assert response.status_code == 200
    assert response.get_json()['missing_speakers'] == ['林清雪']


@pytest.mark.parametrize('headings', [
    ['第一章 风雪', '第二章 夜雨'], ['Chapter 1', 'Chapter 2'],
])
def test_one_speaker_block_spanning_headings_remains_parseable_in_each_section(headings):
    from app import split_text_into_sections
    text = f'[direction]轻声。[/direction]\n[旁白]扉页。\n{headings[0]}\n甲。\n{headings[1]}\n乙。[/旁白]'
    sections = split_text_into_sections(text)
    assert [s['title'] for s in sections] == ['Title', *headings]
    assert len(sections) == 3
    parsed = []
    for section in sections:
        assert not tag_errors(section['content'])
        segments = TextProcessor().parse_speaker_segments(section['content'])
        assert segments and segments[0]['speaker'] == '旁白'
        assert segments[0]['delivery_instruction'] == '轻声。'
        parsed.extend(s['text'] for s in segments)
    assert ''.join(parsed).replace('\n', '') == f'扉页。{headings[0]}甲。{headings[1]}乙。'

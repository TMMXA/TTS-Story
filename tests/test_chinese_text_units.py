import pytest

from src.chinese_novel.text_units import count_text_units, chunk_text_units


@pytest.mark.parametrize('text,expected', [
    ('这是中文', 4), ('hello world', 2), ('这是 GPT model', 4),
    ('你好。世界！', 4), ('日本語です 한국어', 8), ('', 0),
], ids=['han', 'english', 'mixed', 'punctuation', 'kana-hangul', 'empty'])
def test_mixed_units(text, expected):
    assert count_text_units(text) == expected


@pytest.mark.parametrize('text', [
    ('中文段落。\n下一段？\n' * 1000),
    '长' * 12500,
    ('中文与 English words 混合。' * 1500),
    ('A sentence has several English words.\n\n' * 1000),
], ids=['single-newlines', 'unbroken', 'mixed-long', 'english-long'])
def test_chunks_are_bounded_and_preserve_source(text):
    chunks = chunk_text_units(text, 4000)
    assert ''.join(chunks) == text
    assert all(count_text_units(chunk) <= 4000 for chunk in chunks)
    assert len(chunks) > 1


def test_single_newline_and_chinese_sentence_boundaries():
    assert chunk_text_units('第一段。\n第二段。\n第三段。', 6) == [
        '第一段。\n第二段。\n', '第三段。',
    ]
    assert chunk_text_units('第一句。第二句！第三句？', 6) == ['第一句。第二句！', '第三句？']


def test_small_hard_split_does_not_duplicate_or_drop_characters():
    source = '甲乙丙丁戊己庚辛壬癸'
    assert chunk_text_units(source, 3) == ['甲乙丙', '丁戊己', '庚辛壬', '癸']


def test_llm_chunks_include_read_only_preceding_context():
    from app import build_gemini_sections
    source = '文' * 9500
    sections = build_gemini_sections(source, False, {'novel_settings': {'language': 'Chinese'}})
    assert [count_text_units(section['content']) for section in sections] == [4000, 4000, 1500]
    assert sections[0]['context'] == ''
    assert sections[1]['context'] == '文' * 300
    assert ''.join(section['content'] for section in sections) == source


def test_cjk_tts_word_chunks_are_bounded_and_single_line_sentences_split():
    from src.text_processor import TextProcessor
    processor = TextProcessor(chunk_size=100)
    source = '这是测试。' * 1000
    chunks = processor.chunk_text(source)
    assert all(count_text_units(chunk) <= 100 for chunk in chunks)
    assert ''.join(chunks) == source
    assert processor._split_into_sentences('你好。再见！') == ['你好。', '再见！']


def test_overlap_can_be_disabled_and_english_keeps_legacy_budget():
    from app import _resolve_llm_chunk_size, build_gemini_sections
    assert _resolve_llm_chunk_size({'llm_local_chunk_size': 500}, 'English prose.') == 500
    sections = build_gemini_sections('字' * 8500, False, {'novel_settings': {'context_overlap': 0}})
    assert all(section['context'] == '' for section in sections)


def test_cjk_character_strategy_never_overflows_to_a_distant_sentence_end():
    from src.text_processor import TextProcessor
    processor = TextProcessor(chunk_strategy='characters', char_soft_limit=450,
                              char_hard_limit=500, allow_sentence_overflow=True)
    source = '长' * 2500 + '。'
    chunks = processor.chunk_text(source)
    assert all(len(chunk) <= 500 for chunk in chunks)
    assert ''.join(chunks) == source


def test_heading_before_a_long_unbroken_paragraph_stays_with_body():
    source = '第一章 山雨\n\n' + '文' * 9000
    chunks = chunk_text_units(source, 4000)
    assert chunks[0].startswith('第一章 山雨\n\n文')
    assert count_text_units(chunks[0]) == 4000
    assert ''.join(chunks) == source

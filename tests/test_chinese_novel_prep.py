import pytest
from itertools import chain, repeat

from src.chinese_novel.prompts import (
    normalize_novel_settings, compose_novel_prompt, preserve_source_markup,
    with_chinese_novel_presets,
    join_novel_sections,
)


def test_novel_defaults_and_invalid_values():
    settings = normalize_novel_settings({'language': 'Chinese', 'chunk_size': 99999,
                                         'context_overlap': -1, 'narrative_mode': 'bad'})
    assert settings['chunk_size'] == 12000
    assert settings['context_overlap'] == 0
    assert settings['narrative_mode'] == 'auto'
    assert normalize_novel_settings()['chunk_size'] == 4000


def test_prompt_marks_context_input_only_and_uses_alias_memory():
    prompt = compose_novel_prompt({'content': '“你来了。”', 'context': '叶临渊推门。'}, '', [],
        {'language': 'Chinese', 'narrative_mode': 'first_person', 'first_person_protagonist': '叶临渊'},
        [{'display_name': '叶临渊', 'aliases': ['叶兄']}])
    assert '只用于理解，禁止输出' in prompt
    assert '叶兄' in prompt and '叶临渊' in prompt
    assert '第一人称' in prompt and 'CURRENT SOURCE' in prompt


def test_first_person_examples_separate_other_dialogue_from_narrated_actions():
    from src.chinese_novel.prompts import FIRST_PERSON_RULES, CHINESE_NOVEL_PROMPT
    source = '林清雪站在窗边，她轻声说：“叶兄，你总算回来了。”我笑了笑。'
    output = '[叶临渊]林清雪站在窗边，她轻声说：[/叶临渊][林清雪]“叶兄，你总算回来了。”[/林清雪][叶临渊]我笑了笑。[/叶临渊]'
    assert output in FIRST_PERSON_RULES
    assert '主角不能替别人说对白' in FIRST_PERSON_RULES
    assert '而不是把整段分给一个 speaker' in CHINESE_NOVEL_PROMPT
    assert preserve_source_markup(source, output, {'language': 'Chinese', 'narrative_mode': 'first_person',
                                                  'first_person_protagonist': '叶临渊'}) == output


def test_guard_restores_original_spacing_and_keeps_direction_separate():
    source = '我推开门。\n\n“你来了。”'
    result = preserve_source_markup(source,
        '[叶临渊]我推开门。[/叶临渊]\n[direction]轻声而克制。[/direction]\n[叶临渊]“你来了。”[/叶临渊]',
        {'language': 'Chinese'})
    assert result == '[叶临渊]我推开门。[/叶临渊][direction]轻声而克制。[/direction]\n\n[叶临渊]“你来了。”[/叶临渊]'


@pytest.mark.parametrize('response', [
    '[旁白]他推开门。[/旁白]', '[旁白]我推开门。[/旁白]解释',
    '[旁白]我推开门。[/叶临渊]', '[旁白]前文。我推开门。[/旁白]',
])
def test_guard_rejects_rewrite_explanations_bad_tags_and_overlap(response):
    with pytest.raises(ValueError):
        preserve_source_markup('我推开门。', response, {'language': 'Chinese'})


def test_guard_rejects_untagged_prose_that_parser_would_drop():
    with pytest.raises(ValueError):
        preserve_source_markup('我推开门。你好。', '[旁白]我推开门。[/旁白]你好。', {'language': 'Chinese'})


def test_heading_is_excluded_from_prompt_and_reattached_exactly():
    source = '第１２章：风雪\r\n\r\n我推开门。'
    prompt = compose_novel_prompt({'content': source}, novel_settings={'language': 'Chinese'})
    assert '第１２章' not in prompt
    assert preserve_source_markup(source, '[旁白]我推开门。[/旁白]', {'language': 'Chinese'}) == (
        '第１２章：风雪\r\n\r\n[旁白]我推开门。[/旁白]')


def test_inserted_expression_is_not_silently_erased():
    with pytest.raises(ValueError):
        preserve_source_markup('你好。', '[旁白][sigh]你好。[/旁白]', {'language': 'Chinese'})


def test_alias_and_first_person_tags_use_one_voice():
    result = preserve_source_markup('我推开门。你好。',
        '[旁白]我推开门。[/旁白][叶兄]你好。[/叶兄]',
        {'language': 'Chinese', 'narrative_mode': 'first_person', 'first_person_protagonist': '叶临渊'},
        [{'display_name': '叶临渊', 'aliases': ['叶兄']}])
    assert result == '[叶临渊]我推开门。你好。[/叶临渊]'


def test_consecutive_narration_shares_one_block_without_changing_paragraphs():
    source = '开篇。\r\n\r\n下一段。\n最后一段。\n'
    response = '[旁白]开篇。[/旁白][旁白]下一段。[/旁白][旁白]最后一段。[/旁白]'
    assert preserve_source_markup(source, response) == '[旁白]' + source.rstrip('\n') + '[/旁白]\n'


def test_compaction_keeps_direction_scope_and_role_changes_for_tts():
    from src.text_processor import TextProcessor
    source = '他醒来。\n他叹气：“你好。”\n他推门。\n他走远。'
    response = ('[旁白]他醒来。[/旁白][旁白]他叹气：[/旁白]'
                '[direction]低沉、克制。[/direction][叶临渊]“你好。”[/叶临渊]'
                '[旁白]他推门。[/旁白][旁白]他走远。[/旁白]')
    result = preserve_source_markup(source, response)
    segments = TextProcessor().parse_speaker_segments(result)
    assert [segment['speaker'] for segment in segments] == ['旁白', '叶临渊', '旁白']
    assert segments[1]['delivery_instruction'] == '低沉、克制。'
    assert all('delivery_instruction' not in segment for segment in (segments[0], segments[2]))
    assert segments[0]['text'] == '他醒来。\n他叹气：'
    assert segments[2]['text'] == '他推门。\n他走远。'
    assert '[/叶临渊]\n[旁白]他推门。' in result


def test_leading_source_whitespace_stays_before_opening_speaker_tag():
    source = '\r\n  原文。\n'
    assert preserve_source_markup(source, '[旁白]原文。[/旁白]') == '\r\n  [旁白]原文。[/旁白]\n'


def test_formatting_preserves_literal_expression_cues_and_their_whitespace():
    source = '原文[sigh]\n 下一句。'
    assert preserve_source_markup(source, '[旁白]' + source + '[/旁白]') == '[旁白]' + source + '[/旁白]'


@pytest.mark.parametrize('control', ['direction', 'emotion'])
def test_same_speaker_compaction_does_not_cross_delivery_changes(control):
    response = f'[旁白]第一段。[/旁白][{control}]低沉。[/{control}][旁白]第二段。[/旁白]'
    assert preserve_source_markup('第一段。第二段。', response) == response


def test_dangling_narrator_tag_is_rejected_instead_of_compacted_away():
    with pytest.raises(ValueError, match='no matching closing tag'):
        preserve_source_markup('原文。', '[旁白]原文。[/旁白][旁白]')


@pytest.mark.parametrize('name', ['default', 'Default', 'DEFAULT'])
def test_default_voice_placeholder_is_not_an_accepted_novel_role(name):
    with pytest.raises(ValueError, match='unassigned voice placeholder'):
        preserve_source_markup('“站住。”', f'[{name}]“站住。”[/{name}]')


def test_alias_cannot_canonicalize_a_role_to_default_placeholder():
    with pytest.raises(ValueError, match='unassigned voice placeholder'):
        preserve_source_markup('“站住。”', '[裴语涵]“站住。”[/裴语涵]',
                               character_registry=[{'display_name': 'default', 'aliases': ['裴语涵']}])


@pytest.mark.parametrize('canonical', ['叶 临渊', '[叶临渊]', 'direction', 'emotion', '123'])
def test_guard_rejects_canonical_ids_that_parser_cannot_speak(canonical):
    settings = {'language': 'Chinese', 'narrative_mode': 'first_person',
                'first_person_protagonist': canonical}
    with pytest.raises(ValueError, match='canonical speaker ID'):
        preserve_source_markup('我推开门。', '[旁白]我推开门。[/旁白]', settings)
    with pytest.raises(ValueError, match='canonical speaker ID'):
        preserve_source_markup('你好。', '[叶兄]你好。[/叶兄]', {'language': 'Chinese'},
                               [{'display_name': canonical, 'aliases': ['叶兄']}])


def test_builtin_presets_preserve_user_edits_and_are_idempotent():
    edited = [{'id': 'chinese-novel', 'title': 'Mine', 'prompt': 'custom'}]
    presets = with_chinese_novel_presets(edited)
    assert presets[0] == edited[0]
    assert len(presets) == 3
    assert with_chinese_novel_presets(presets) == presets


def test_section_endpoint_preserves_heading_and_refuses_changed_source(monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module, 'load_config', lambda: {'llm_provider': 'local'})
    profile = {'id': 'primary', 'provider': 'local', 'name': 'test', 'model': 'test'}
    responses = chain(['[旁白]我推开门。[/旁白]'], repeat('[旁白]他推开门。[/旁白]'))
    prompts = []
    def run(prompt, *args, **kwargs):
        prompts.append(prompt)
        return next(responses), profile, []
    monkeypatch.setattr(app_module, '_run_llm_prompt_with_failover', run)
    payload = {'content': '第一章 山雨\n我推开门。', 'context': '叶临渊站在门前。',
               'novel_settings': {'language': 'Chinese'}}
    client = app_module.app.test_client()
    good = client.post('/api/gemini/process-section', json=payload)
    assert good.status_code == 200
    assert good.json['result_text'] == '第一章 山雨\n[旁白]我推开门。[/旁白]'
    assert '第一章 山雨' not in prompts[0]
    assert '禁止输出' in prompts[0]
    bad = client.post('/api/gemini/process-section', json=payload)
    assert bad.status_code == 400 and bad.json['retryable'] is False


def test_prep_progress_retains_settings_and_active_profile(monkeypatch, tmp_path):
    import app as app_module
    monkeypatch.setattr(app_module, 'PREP_PROGRESS_DIR', tmp_path)
    client = app_module.app.test_client()
    payload = {'text_hash': 'novel_123', 'outputs': ['done'], 'sections': [{'context': '前文'}],
               'novel_settings': {'language': 'Chinese', 'narrative_mode': 'first_person',
                                  'first_person_protagonist': '叶临渊'},
               'character_registry': [{'display_name': '叶临渊', 'aliases': ['叶兄']}],
               'active_profile': 'backup_1'}
    payload.update(prompt_override='用户指定预设', last_failure='source mismatch at offset 100')
    payload['source_locked_prep'] = True
    assert client.post('/api/prep-progress/save', json=payload).json['success']
    loaded = client.get('/api/prep-progress/load?text_hash=novel_123').json['progress']
    assert loaded['novel_settings']['first_person_protagonist'] == '叶临渊'
    assert loaded['character_registry'] == payload['character_registry']
    assert loaded['active_profile'] == 'backup_1'
    assert loaded['prompt_override'] == payload['prompt_override']
    assert loaded['last_failure'] == payload['last_failure']
    assert loaded['source_locked_prep'] is True


def test_sections_only_builds_bounded_chunks_without_inference(monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module, 'load_config', lambda: {'llm_provider': 'local'})
    def fail(*args, **kwargs):
        pytest.fail('Sections endpoint must not call the model')
    monkeypatch.setattr(app_module, '_run_llm_prompt_with_failover', fail)
    response = app_module.app.test_client().post('/api/gemini/sections', json={
        'text': '第一章 山雨\n' + '我推开门。' * 300,
        'novel_settings': {'language': 'Chinese', 'chunk_size': 1000}})
    assert response.status_code == 200
    assert response.json['count'] > 1
    assert any(section['context'] for section in response.json['sections'][1:])


@pytest.mark.parametrize('endpoint', ['/api/gemini/process', '/api/gemini/process-full'])
def test_legacy_prep_paths_preserve_source_and_reject_rewrites(monkeypatch, endpoint):
    import app as app_module
    monkeypatch.setattr(app_module, 'load_config', lambda: {'llm_provider': 'local'})
    profile = {'id': 'primary', 'provider': 'local', 'name': 'test', 'model': 'test'}
    responses = chain(['[叶临渊]我推开门。[/叶临渊]'], repeat('[叶临渊]他推开门。[/叶临渊]'))
    monkeypatch.setattr(app_module, '_run_llm_prompt_with_failover', lambda *args, **kwargs: (next(responses), profile, []))
    client = app_module.app.test_client()
    payload = {'text': '第一章 山雨\n我推开门。', 'novel_settings': {'language': 'Chinese'}}
    assert client.post(endpoint, json=payload).json['result_text'] == '第一章 山雨\n[叶临渊]我推开门。[/叶临渊]'
    assert client.post(endpoint, json=payload).status_code == 400


@pytest.mark.parametrize('source,contents', [
    (' \r\n第一章 山雨\r\n第一段。\n第二段。\n\n\n第二章 故人\n第三段。 \n',
     ['第一章 山雨\r\n第一段。\n第二段。', '第二章 故人\n第三段。']),
    ('\n甲乙丙丁戊己。\n', ['甲乙丙', '丁戊己。']),
    ('甲。\n甲。\n\n甲。', ['甲。', '甲。', '甲。']),
])
def test_join_restores_exact_section_separators_and_outer_whitespace(source, contents):
    import re
    sections = [{'content': content} for content in contents]
    outputs = [preserve_source_markup(content, '[旁白]' + content + '[/旁白]', {'language': 'Chinese'})
               if not content.startswith('第') else content.splitlines(keepends=True)[0] + '[旁白]' + content.split('\n', 1)[1] + '[/旁白]'
               for content in contents]
    result = join_novel_sections(source, sections, outputs)
    assert re.sub(r'\[/?旁白\]', '', result) == source


def test_join_errors_instead_of_falling_back_to_duplicated_raw_source():
    with pytest.raises(ValueError):
        join_novel_sections('原文。', [{'content': '不存在。'}], ['[旁白]不存在。[/旁白]'])
    with pytest.raises(ValueError):
        join_novel_sections('原文。', [{'content': '原文。'}], [])


def test_backend_full_assembly_preserves_mixed_newlines_and_chunk_boundaries(monkeypatch):
    import re
    import app as app_module
    monkeypatch.setattr(app_module, 'load_config', lambda: {'llm_provider': 'local'})
    profile = {'id': 'primary', 'provider': 'local', 'name': 'test', 'model': 'test'}
    source = ' \r\n第一章 山雨\r\n' + '文' * 2100 + '\n\n\n第二章 故人\n正文。 \n'
    sections = app_module.build_gemini_sections(source.strip(), True, {'novel_settings': {'language': 'Chinese', 'chunk_size': 1000}})
    replies = []
    from src.chinese_novel.prompts import _heading_prefix
    for section in sections:
        _, body = _heading_prefix(section['content'])
        replies.append('[旁白]' + body + '[/旁白]')
    replies = iter(replies)
    monkeypatch.setattr(app_module, '_run_llm_prompt_with_failover', lambda *args, **kwargs: (next(replies), profile, []))
    response = app_module.app.test_client().post('/api/gemini/process', json={
        'text': source, 'novel_settings': {'language': 'Chinese', 'chunk_size': 1000}})
    assert response.status_code == 200
    assert re.sub(r'\[/?旁白\]', '', response.json['result_text']) == source


@pytest.mark.parametrize('endpoint,key', [('/api/gemini/process-section', 'content'), ('/api/gemini/process', 'text')])
def test_heading_only_sections_are_preserved_without_model_calls(monkeypatch, endpoint, key):
    import app as app_module
    monkeypatch.setattr(app_module, 'load_config', lambda: {'llm_provider': 'local'})
    monkeypatch.setattr(app_module, '_run_llm_prompt_with_failover', lambda *args, **kwargs: pytest.fail('Heading-only input must not call model'))
    source = '第一章 山雨\r\n'
    if key == 'text':
        monkeypatch.setattr(app_module, 'build_gemini_sections', lambda *args: [{'content': source, 'title': '第一章 山雨', 'source': 'section'}])
    response = app_module.app.test_client().post(endpoint, json={key: source, 'novel_settings': {'language': 'Chinese'}})
    assert response.status_code == 200
    assert response.json['result_text'] == source
    assert response.json['llm_profile_used'] is None


def test_section_endpoint_keeps_source_trailing_separator(monkeypatch):
    import re
    import app as app_module
    monkeypatch.setattr(app_module, 'load_config', lambda: {'llm_provider': 'local'})
    profile = {'id': 'primary', 'provider': 'local', 'name': 'test', 'model': 'test'}
    monkeypatch.setattr(app_module, '_run_llm_prompt_with_failover', lambda *args, **kwargs: ('[旁白]正文。[/旁白]', profile, []))
    source = '正文。\r\n\n'
    response = app_module.app.test_client().post('/api/gemini/process-section', json={'content': source, 'novel_settings': {'language': 'Chinese'}})
    assert re.sub(r'\[/?旁白\]', '', response.json['result_text']) == source


@pytest.mark.parametrize('endpoint', ['/api/gemini/process', '/api/gemini/process-full'])
def test_auto_chinese_book_keeps_latin_subsections_under_source_protection(monkeypatch, endpoint):
    import app as app_module
    monkeypatch.setattr(app_module, 'load_config', lambda: {'llm_provider': 'local'})
    chinese = '原文中文。'
    latin = 'Original English passage.'
    sections = [{'content': chinese, 'source': 'chunk', 'context': ''},
                {'content': latin, 'source': 'chunk', 'context': chinese}]
    monkeypatch.setattr(app_module, 'build_gemini_sections', lambda *args: sections)
    profile = {'id': 'primary', 'provider': 'local', 'name': 'test', 'model': 'test'}
    calls = []
    def generate(prompt, config, **kwargs):
        body = prompt.rsplit('CURRENT SOURCE（只标注以下原文）：\n', 1)[-1]
        calls.append((body, config['novel_settings']['language']))
        response = '[旁白]' + chinese + '[/旁白]' if body == chinese else '[narrator]CHANGED[/narrator]'
        return response, profile, []
    monkeypatch.setattr(app_module, '_run_llm_prompt_with_failover', generate)
    response = app_module.app.test_client().post(endpoint, json={
        'text': chinese + '\n\n' + latin, 'novel_settings': {'language': 'auto'}})
    assert response.status_code == 400
    assert response.json['success'] is False
    assert 'result_text' not in response.json
    assert len(calls) >= 3  # Invalid prose and span annotations must never bypass the source guard.
    assert calls[0][0] == chinese
    assert all(body == latin for body, _ in calls[1:3])
    assert all(language == 'Chinese' for _, language in calls)

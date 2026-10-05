import pytest

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
    assert result == '[叶临渊]我推开门。[/叶临渊][direction]轻声而克制。[/direction][叶临渊]\n\n“你来了。”[/叶临渊]'


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
        '第１２章：风雪\r\n[旁白]\r\n我推开门。[/旁白]')


def test_inserted_expression_is_not_silently_erased():
    with pytest.raises(ValueError):
        preserve_source_markup('你好。', '[旁白][sigh]你好。[/旁白]', {'language': 'Chinese'})


def test_alias_and_first_person_tags_use_one_voice():
    result = preserve_source_markup('我推开门。你好。',
        '[旁白]我推开门。[/旁白][叶兄]你好。[/叶兄]',
        {'language': 'Chinese', 'narrative_mode': 'first_person', 'first_person_protagonist': '叶临渊'},
        [{'display_name': '叶临渊', 'aliases': ['叶兄']}])
    assert result == '[叶临渊]我推开门。[/叶临渊][叶临渊]你好。[/叶临渊]'


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
    responses = iter(['[旁白]我推开门。[/旁白]', '[旁白]他推开门。[/旁白]'])
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
    assert client.post('/api/prep-progress/save', json=payload).json['success']
    loaded = client.get('/api/prep-progress/load?text_hash=novel_123').json['progress']
    assert loaded['novel_settings']['first_person_protagonist'] == '叶临渊'
    assert loaded['character_registry'] == payload['character_registry']
    assert loaded['active_profile'] == 'backup_1'


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
    responses = iter(['[叶临渊]我推开门。[/叶临渊]', '[叶临渊]他推开门。[/叶临渊]'])
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

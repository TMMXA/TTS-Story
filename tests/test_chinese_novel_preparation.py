import re

import pytest

from src.chinese_novel.preparation import prepare_chinese_novel, NovelPreparationError


PROFILE = {'id': 'primary', 'provider': 'local', 'model': 'test', 'name': 'Test'}


def body_from_prompt(prompt):
    return prompt.rsplit('CURRENT SOURCE（只标注以下原文）：\n', 1)[1]


def marked(body, speaker='旁白'):
    return f'[{speaker}]{body}[/{speaker}]'


def test_success_preserves_source_and_reports_metadata():
    source = '第一章 风雪\r\n\r\n正文。\n'
    result = prepare_chinese_novel(source, generate=lambda prompt: (marked(body_from_prompt(prompt)), PROFILE, []),
                                  novel_settings={'language': 'Chinese'})
    assert re.sub(r'\[/?旁白\]', '', result['result_text']) == source
    assert result['profile'] == PROFILE
    assert result['diagnostics']['calls'] == 1


def test_heading_only_does_not_call_model():
    result = prepare_chinese_novel('第一章 山雨\n', generate=lambda prompt: pytest.fail('heading called model'))
    assert result['result_text'] == '第一章 山雨\n'
    assert result['diagnostics']['calls'] == 0


def test_one_correction_retry_recovers_source_without_accepting_rewrite():
    calls = []
    def generate(prompt):
        calls.append(prompt)
        return (marked('改文。') if len(calls) == 1 else marked(body_from_prompt(prompt)), PROFILE, [])
    result = prepare_chinese_novel('原文。', generate=generate)
    assert result['result_text'] == marked('原文。')
    assert len(calls) == 2
    assert '校验' in calls[1]
    assert result['diagnostics']['retries'] == 1


def test_adaptive_split_preserves_exact_source_and_shares_speaker_context():
    source = '甲' * 600 + '\r\n\n' + '乙' * 600
    calls = []
    def generate(prompt):
        body = body_from_prompt(prompt)
        calls.append((body, prompt))
        if len(body.strip()) > 300:
            return marked(body.strip()[:-1]), PROFILE, []
        return marked(body, '叶临渊'), PROFILE, []
    result = prepare_chinese_novel(source, generate=generate, novel_settings={'language': 'Chinese', 'context_overlap': 300})
    assert re.sub(r'\[/?叶临渊\]', '', result['result_text']) == source
    assert result['diagnostics']['splits'] > 0
    assert all(body.strip() for body, _ in calls)
    successful = [(body, prompt) for body, prompt in calls if len(body.strip()) <= 300]
    assert '叶临渊' in successful[1][1]
    assert 'PRECEDING CONTEXT' in successful[1][1]


def test_accepted_left_child_is_not_regenerated_when_right_child_splits():
    source = '甲' * 500 + '乙' * 500
    calls = []
    def generate(prompt):
        body = body_from_prompt(prompt)
        calls.append(body)
        if len(body) > 500 or (body.startswith('乙') and len(body) > 250):
            return marked(body[:-1]), PROFILE, []
        return marked(body), PROFILE, []
    result = prepare_chinese_novel(source, generate=generate)
    assert calls.count('甲' * 500) == 1
    assert re.sub(r'\[/?旁白\]', '', result['result_text']) == source


def test_provider_failure_propagates_without_retry_or_split():
    calls = []
    def generate(prompt):
        calls.append(prompt)
        raise RuntimeError('HTTP 429')
    with pytest.raises(RuntimeError, match='429'):
        prepare_chinese_novel('文' * 2000, generate=generate)
    assert len(calls) == 1


def test_generate_configuration_valueerror_is_not_treated_as_model_output():
    with pytest.raises(ValueError, match='invalid configuration'):
        prepare_chinese_novel('文' * 2000, generate=lambda prompt: (_ for _ in ()).throw(ValueError('invalid configuration')))


def test_invalid_canonical_configuration_fails_before_model_call():
    with pytest.raises(ValueError):
        prepare_chinese_novel('正文。', generate=lambda prompt: pytest.fail('invalid config called model'),
            novel_settings={'narrative_mode': 'first_person', 'first_person_protagonist': '[主角]'})


def test_total_call_budget_is_bounded_and_diagnostics_do_not_include_story():
    source = '隐私正文' * 1000
    calls = []
    def generate(prompt):
        calls.append(prompt)
        return '', PROFILE, []
    with pytest.raises(NovelPreparationError) as error:
        prepare_chinese_novel(source, generate=generate, max_calls=5)
    assert len(calls) == 5
    assert source[:4] not in str(error.value)
    assert source[:4] not in str(error.value.diagnostics)


def test_typed_provider_truncation_uses_bounded_recovery():
    from src.llm_output import LLMOutputTruncatedError
    calls = []
    def generate(prompt):
        body = body_from_prompt(prompt)
        calls.append(body)
        if len(body) > 500:
            raise LLMOutputTruncatedError('output length limit')
        return marked(body), PROFILE, []
    source = '文' * 1000
    result = prepare_chinese_novel(source, generate=generate)
    assert re.sub(r'\[/?旁白\]', '', result['result_text']) == source
    assert result['diagnostics']['errors'][0]['kind'] == 'truncated'
    assert len(calls) == 4


def test_accepted_metadata_and_provider_failure_history_survive_splits():
    failure = {'profile_id': 'bad', 'error': 'HTTP 503'}
    def generate(prompt):
        body = body_from_prompt(prompt)
        response = marked(body[:-1]) if len(body) > 500 else marked(body)
        return response, PROFILE, [failure]
    result = prepare_chinese_novel('文' * 1000, generate=generate)
    assert result['profile'] == PROFILE
    assert failure in result['failures']


def test_persistent_bad_small_segment_raises_instead_of_narrator_fallback():
    with pytest.raises(NovelPreparationError) as error:
        prepare_chinese_novel('文' * 250, generate=lambda prompt: (marked('改' * 250), PROFILE, []))
    assert error.value.diagnostics['calls'] == 2
    assert error.value.diagnostics['splits'] == 0


@pytest.mark.parametrize('prefer_locked,expected_calls', [(False, 3), (True, 1)])
def test_locked_role_recovery_assembles_original_prose_and_actual_dialogue_owner(prefer_locked, expected_calls):
    import json
    source = '她问：“你来了？”我点头。'
    calls = []
    def generate(prompt):
        calls.append(prompt)
        if 'LOCKED SPANS JSON:\n' not in prompt:
            return '[旁白]改写的正文。[/旁白]', PROFILE, []
        spans = json.loads(prompt.rsplit('LOCKED SPANS JSON:\n', 1)[1])
        return json.dumps({'annotations': [{'id': span['id'],
            'speaker': '林清雪' if span['kind'] == 'dialogue' else '旁白'} for span in spans]}, ensure_ascii=False), PROFILE, []
    result = prepare_chinese_novel(source, generate=generate, span_recovery=True,
        prefer_source_locked=prefer_locked, novel_settings={'language': 'Chinese'})
    assert re.sub(r'\[/?(?:旁白|林清雪)\]', '', result['result_text']) == source
    assert '[林清雪]“你来了？”[/林清雪]' in result['result_text']
    assert len(calls) == expected_calls
    assert result['diagnostics']['calls'] == expected_calls
    assert result['diagnostics']['source_locked_parts'] == 1

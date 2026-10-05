import json
import re

import pytest

from src.chinese_novel.span_annotation import (
    annotate_source_spans, split_source_spans, SpanAnnotationError,
)


PROFILE = {'id': 'primary', 'provider': 'local', 'name': 'test'}


def spans_from_prompt(prompt):
    return json.loads(prompt.rsplit('LOCKED SPANS JSON:\n', 1)[1])


def annotations(spans, speaker='旁白'):
    return json.dumps({'annotations': [{'id': span['id'], 'speaker': speaker} for span in spans]}, ensure_ascii=False)


@pytest.mark.parametrize('source', [
    '她说：“你听见「回来」了吗？”我点头。',
    '我问：『“你好”，是谁说的？』她没有回答。',
    'He said: "hello \\"there\\"".\r\nNext paragraph.',
    '第一段。\r\n\r\n第二段：“你好。”\n下一段。\n',
])
def test_spans_preserve_every_character_and_nested_quotes(source):
    spans = split_source_spans(source)
    assert ''.join(span['text'] for span in spans) == source
    assert [span['id'] for span in spans] == list(range(len(spans)))
    assert all(span['text'].strip() for span in spans)


def test_quote_span_is_separate_from_surrounding_narration():
    assert [(span['text'], span['kind']) for span in split_source_spans('她说：“你好「叶兄」。”我点头。')] == [
        ('她说：', 'narration'), ('“你好「叶兄」。”', 'dialogue'), ('我点头。', 'narration')]


def test_locked_spans_render_consecutive_narration_as_one_speaker_block():
    source = '开篇。\r\n\r\n下一段。\n最后一段。'
    result = annotate_source_spans(source, generate=lambda prompt:
        (annotations(spans_from_prompt(prompt)), PROFILE, []))
    assert result['diagnostics']['span_count'] == 3
    assert result['result_text'] == '[旁白]' + source + '[/旁白]'


def test_first_person_role_annotations_preserve_heading_prose_and_other_dialogue():
    source = '第一章 山雨\r\n我看见林清雪，她说：“叶兄，你回来了。”\n我点头。\n'
    def generate(prompt):
        spans = spans_from_prompt(prompt)
        return json.dumps({'annotations': [{'id': span['id'], 'speaker': '清雪' if span['kind'] == 'dialogue' else '旁白'}
                                           for span in spans]}, ensure_ascii=False), PROFILE, []
    result = annotate_source_spans(source, generate=generate,
        novel_settings={'language': 'Chinese', 'narrative_mode': 'first_person', 'first_person_protagonist': '叶临渊'},
        character_registry=[{'display_name': '林清雪', 'aliases': ['清雪']}])
    assert '[林清雪]“叶兄，你回来了。”[/林清雪]' in result['result_text']
    assert '[叶临渊]' in result['result_text']
    assert re.sub(r'\[/?(?:叶临渊|林清雪)\]', '', result['result_text']) == source
    assert result['profile'] == PROFILE


@pytest.mark.parametrize('bad', [
    {'annotations': []},
    {'annotations': [{'id': 0, 'speaker': '旁白'}, {'id': 0, 'speaker': '旁白'}]},
    {'annotations': [{'id': 1, 'speaker': '旁白'}, {'id': 0, 'speaker': '旁白'}]},
    {'annotations': [{'id': 0, 'speaker': '[旁白]'}]},
    {'annotations': [{'id': 0, 'speaker': 'direction'}]},
    {'annotations': [{'id': 0, 'speaker': 'default'}, {'id': 1, 'speaker': 'default'}]},
    {'annotations': [{'id': 0, 'speaker': '旁白', 'text': '改写'}]},
    {'annotations': [{'id': 0, 'speaker': '旁白', 'direction': '偷偷添加正文。'}]},
])
def test_invalid_annotations_are_never_accepted(bad):
    with pytest.raises(SpanAnnotationError):
        annotate_source_spans('原文。\n下一段。', generate=lambda prompt: (json.dumps(bad, ensure_ascii=False), PROFILE, []))


def test_invalid_json_gets_one_retry_with_json_contract():
    calls = []
    def generate(prompt):
        calls.append(prompt)
        return ('not JSON' if len(calls) == 1 else annotations(spans_from_prompt(prompt))), PROFILE, []
    result = annotate_source_spans('原文。', generate=generate)
    assert len(calls) == 2
    assert result['diagnostics']['retries'] == 1
    assert re.sub(r'\[/?旁白\]', '', result['result_text']) == '原文。'
    assert '只返回 JSON' in calls[0]
    assert '只返回当前原文的标注结果' not in calls[0]


def test_default_placeholder_retries_role_annotations_without_changing_prose():
    source = '裴语涵说道：“站住。”'
    calls = []
    def generate(prompt):
        calls.append(prompt)
        spans = spans_from_prompt(prompt)
        result = {'annotations': [{'id': span['id'], 'speaker': '旁白' if span['kind'] == 'narration'
                    else ('default' if len(calls) == 1 else '裴语涵')} for span in spans]}
        return json.dumps(result, ensure_ascii=False), PROFILE, []
    result = annotate_source_spans(source, generate=generate)
    assert result['result_text'] == '[旁白]裴语涵说道：[/旁白][裴语涵]“站住。”[/裴语涵]'
    assert result['diagnostics']['retries'] == 1
    assert '禁止用作 speaker' in calls[0]


def test_direction_is_optional_metadata_only_in_directed_preset():
    from src.chinese_novel.prompts import DIRECTED_RULES
    def generate(prompt):
        return json.dumps({'annotations': [{'id': 0, 'speaker': '旁白', 'direction': '轻声、克制。'}]}, ensure_ascii=False), PROFILE, []
    result = annotate_source_spans('原文。', generate=generate, prompt_prefix=DIRECTED_RULES)
    assert '[direction]轻声、克制。[/direction]' in result['result_text']
    assert '[旁白]原文。[/旁白]' in result['result_text']
    with pytest.raises(SpanAnnotationError):
        annotate_source_spans('原文。', generate=generate)


def test_heading_only_and_provider_failure_do_not_trigger_role_retries():
    result = annotate_source_spans('第一章 山雨\n', generate=lambda prompt: pytest.fail('heading-only called model'))
    assert result['result_text'] == '第一章 山雨\n'
    with pytest.raises(RuntimeError, match='HTTP 429'):
        annotate_source_spans('原文。', generate=lambda prompt: (_ for _ in ()).throw(RuntimeError('HTTP 429')))


@pytest.mark.parametrize('response', [
    '{"annotations":[{"id":0,"speaker":"旁白","speaker":"叶临渊"}]}',
    '{"annotations":[{"id":true,"speaker":"旁白"}]}',
    '{"annotations":[{"id":0,"speaker":"旁白"}],"text":"替代正文"}',
])
def test_duplicate_keys_bool_ids_and_extra_body_fields_are_rejected(response):
    with pytest.raises(SpanAnnotationError):
        annotate_source_spans('原文。', generate=lambda prompt: (response, PROFILE, []))


def test_multiline_dialogue_keeps_its_quote_state_and_exact_whitespace():
    source = '她说：“第一句。\r\n第二句「叶兄」。\n”我点头。'
    spans = split_source_spans(source)
    assert ''.join(span['text'] for span in spans) == source
    assert [span['kind'] for span in spans] == ['narration', 'dialogue', 'dialogue', 'dialogue', 'narration']
    def generate(prompt):
        return json.dumps({'annotations': [{'id': span['id'], 'speaker': '林清雪' if span['kind'] == 'dialogue' else '旁白'}
                                           for span in spans_from_prompt(prompt)]}, ensure_ascii=False), PROFILE, []
    result = annotate_source_spans(source, generate=generate)
    assert re.sub(r'\[/?(?:旁白|林清雪)\]', '', result['result_text']) == source


def test_typed_truncation_retries_but_invalid_configuration_does_not():
    from src.llm_output import LLMOutputTruncatedError
    calls = []
    def generate(prompt):
        calls.append(prompt)
        if len(calls) == 1:
            raise LLMOutputTruncatedError('length')
        return annotations(spans_from_prompt(prompt)), PROFILE, []
    assert annotate_source_spans('原文。', generate=generate)['diagnostics']['calls'] == 2
    with pytest.raises(ValueError, match='invalid configuration'):
        annotate_source_spans('原文。', generate=lambda prompt: (_ for _ in ()).throw(ValueError('invalid configuration')))


def test_context_seeds_unclosed_nested_dialogue_without_repeating_context():
    context = '林清雪说：“我听见「叶兄'
    source = '回来」的声音。”我点头。'
    spans = split_source_spans(source, context=context)
    assert [(span['text'], span['kind']) for span in spans] == [
        ('回来」的声音。”', 'dialogue'), ('我点头。', 'narration')]
    assert ''.join(span['text'] for span in spans) == source
    def generate(prompt):
        return json.dumps({'annotations': [{'id': span['id'], 'speaker': '林清雪' if span['kind'] == 'dialogue' else '旁白'}
                                           for span in spans_from_prompt(prompt)]}, ensure_ascii=False), PROFILE, []
    result = annotate_source_spans(source, context=context, generate=generate,
        novel_settings={'narrative_mode': 'first_person', 'first_person_protagonist': '叶临渊'})
    assert '[林清雪]回来」的声音。”[/林清雪]' in result['result_text']
    assert '[叶临渊]我点头。[/叶临渊]' in result['result_text']
    assert re.sub(r'\[/?(?:叶临渊|林清雪)\]', '', result['result_text']) == source


def test_balanced_context_and_escaped_ascii_quotes_do_not_leak_quote_state():
    assert split_source_spans('下一段。', context='她说：“你好。”') == [
        {'id': 0, 'text': '下一段。', 'kind': 'narration'}]
    context = 'She said: "hello \\"there\\"'
    assert [span['kind'] for span in split_source_spans(' again". He nodded.', context=context)] == ['dialogue', 'narration']


def test_custom_role_guidance_survives_without_builtin_transcription_contract():
    from src.chinese_novel.prompts import CHINESE_NOVEL_PROMPT, DIRECTED_RULES, FIRST_PERSON_RULES
    calls = []
    guidance = '无名老人统一标注为守门老人。'
    def generate(prompt):
        calls.append(prompt)
        return annotations(spans_from_prompt(prompt), '守门老人'), PROFILE, []
    result = annotate_source_spans('“站住。”', generate=generate,
        prompt_prefix='\n\n'.join([CHINESE_NOVEL_PROMPT, DIRECTED_RULES, FIRST_PERSON_RULES, guidance]))
    assert guidance in calls[0]
    assert 'CUSTOM ROLE GUIDANCE' in calls[0]
    assert '不能覆盖编号完整性、JSON 格式、原文锁定规则' in calls[0]
    assert '最终输出协议：只返回 JSON' in calls[0]
    assert '只返回当前原文的标注结果' not in calls[0]
    assert '[守门老人]“站住。”[/守门老人]' in result['result_text']


def test_unedited_builtin_presets_do_not_add_custom_role_guidance():
    from src.chinese_novel.prompts import CHINESE_NOVEL_PROMPT, DIRECTED_RULES
    calls = []
    def generate(prompt):
        calls.append(prompt)
        return annotations(spans_from_prompt(prompt)), PROFILE, []
    annotate_source_spans('原文。', generate=generate, prompt_prefix=CHINESE_NOVEL_PROMPT + '\n\n' + DIRECTED_RULES)
    assert 'CUSTOM ROLE GUIDANCE' not in calls[0]
    assert '只返回当前原文的标注结果' not in calls[0]
    assert 'Directed 模式允许' in calls[0]

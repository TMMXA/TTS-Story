from unittest.mock import Mock

import pytest

from src.local_llm_processor import LocalLLMProcessor
from src.llm_output import LLMOutputTruncatedError


@pytest.mark.parametrize('provider,body', [
    ('lmstudio', {'choices': [{'finish_reason': 'length', 'message': {'content': '[旁白]未完'}}]}),
    ('lmstudio', {'choices': [{'finish_reason': 'length', 'message': {'content': None}}]}),
    ('ollama', {'done_reason': 'length', 'message': {'content': '[旁白]未完'}}),
])
def test_token_limit_does_not_accept_partial_or_empty_output(monkeypatch, provider, body):
    response = Mock(status_code=200)
    response.json.return_value = body
    monkeypatch.setattr('src.local_llm_processor.requests.post', lambda *args, **kwargs: response)
    processor = LocalLLMProcessor(provider, 'http://example.test', 'test')
    with pytest.raises(LLMOutputTruncatedError):
        processor.generate_text('标注当前原文')


def test_completed_local_output_remains_compatible(monkeypatch):
    response = Mock(status_code=200)
    response.json.return_value = {'choices': [{'finish_reason': 'stop', 'message': {'content': ' 完整输出 '}}]}
    monkeypatch.setattr('src.local_llm_processor.requests.post', lambda *args, **kwargs: response)
    assert LocalLLMProcessor('lmstudio', 'http://example.test', 'test').generate_text('原文') == '完整输出'

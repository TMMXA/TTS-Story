"""Bounded recovery for Chinese Prep without accepting changed source prose."""
from __future__ import annotations

import copy
import re

from src.llm_output import LLMOutputTruncatedError
from src.tag_validation import CONTROL_TAGS, speaker_names
from .prompts import (
    compose_novel_prompt, heading_only_source, join_novel_sections,
    normalize_novel_settings, preserve_source_markup,
)
from .speaker_ids import SPEAKER_NAME_PATTERN, UNASSIGNED_SPEAKER_ID
from .text_units import chunk_text_units, count_text_units


class NovelPreparationError(ValueError):
    """Recovery stopped; diagnostics contain counts and categories, never prose."""
    def __init__(self, message, diagnostics):
        super().__init__(message)
        self.diagnostics = copy.deepcopy(diagnostics)


def _validate_configuration(settings, registry):
    def valid(name):
        return (isinstance(name, str) and bool(re.fullmatch(SPEAKER_NAME_PATTERN, name))
                and name.casefold() not in CONTROL_TAGS | {UNASSIGNED_SPEAKER_ID})
    if settings['narrative_mode'] == 'first_person' and settings['first_person_protagonist']:
        if not valid(settings['first_person_protagonist']):
            raise ValueError('Chinese Novel first-person protagonist must be a valid speaker ID')
    if not isinstance(registry, list):
        raise ValueError('Chinese Novel character registry must be an array')
    for entry in registry:
        if not isinstance(entry, dict):
            raise ValueError('Chinese Novel character registry entries must be objects')
        name = entry.get('display_name') or entry.get('name')
        if name and not valid(name):
            raise ValueError('Chinese Novel character display name must be a valid speaker ID')
        aliases = entry.get('aliases') or []
        if not isinstance(aliases, list) or any(not isinstance(alias, str) for alias in aliases):
            raise ValueError('Chinese Novel character aliases must be an array of strings')


def _failure_kind(exc):
    if isinstance(exc, LLMOutputTruncatedError):
        return 'truncated'
    message = str(exc).lower()
    if 'empty' in message:
        return 'empty_output'
    if 'omitted' in message:
        return 'omitted_source'
    if 'changed' in message or 'repeated' in message:
        return 'source_mismatch'
    return 'invalid_markup'


def prepare_chinese_novel(content, *, generate, context='', novel_settings=None,
                          character_registry=None, prompt_prefix='', known_speakers=None,
                          min_units=250, max_calls=24, correction_attempts=1, span_recovery=False,
                          prefer_source_locked=False):
    """Try once, correct once, then split only failed source spans into smaller ones.

    ``generate(prompt)`` returns ``(text, public_profile, provider_failures)``.
    Provider/configuration errors propagate unchanged. Only invalid generated
    markup/prose and the typed output-truncation error permit bounded recovery.
    Accepted children remain accepted while a later child retries or splits.
    """
    settings = normalize_novel_settings(novel_settings)
    registry = [] if character_registry is None else character_registry
    _validate_configuration(settings, registry)
    min_units = max(1, int(min_units))
    max_calls = max(1, int(max_calls))
    correction_attempts = max(0, min(2, int(correction_attempts)))
    speakers = list(dict.fromkeys(str(name) for name in (known_speakers or [])
                                if name and str(name).casefold() != UNASSIGNED_SPEAKER_ID))
    failures, last_profile = [], None
    diagnostics = {'calls': 0, 'retries': 0, 'splits': 0, 'accepted_parts': 0,
                   'recovered': False, 'errors': [], 'source_locked_parts': 0}

    def stop(reason):
        raise NovelPreparationError(
            f'Chinese Novel preparation stopped: {reason}; '
            f'{diagnostics["calls"]} model calls, {diagnostics["accepted_parts"]} accepted parts. '
            'Source text was not changed.', diagnostics)

    def process(source, preceding):
        nonlocal last_profile
        heading = heading_only_source(source)
        if heading is not None:
            diagnostics['accepted_parts'] += 1
            return heading
        if not source.strip():
            return source
        last_kind = ''
        for attempt in range(0 if prefer_source_locked else 1 + correction_attempts):
            if diagnostics['calls'] >= max_calls:
                stop('model-call budget exhausted')
            prefix = prompt_prefix
            if attempt:
                diagnostics['retries'] += 1
                prefix += ('\n\n上次输出未通过原文或标签校验。重新标注当前原文，'
                           '逐字保留首尾文字、所有标点和顺序，确保全部正文在平衡的 speaker tags 内。'
                           '不要解释、补写或复制前文上下文；必须输出到原文最后一个字。')
                if last_kind == 'truncated':
                    prefix += '\n上次输出被截断；保持 direction 简洁，完整输出当前原文。'
            prompt = compose_novel_prompt({'content': source, 'context': preceding}, prefix,
                                          speakers, settings, registry)
            diagnostics['calls'] += 1
            response = ''
            try:
                response, profile, provider_failures = generate(prompt)
            except LLMOutputTruncatedError as exc:
                output_error = exc
            else:
                last_profile = profile
                failures.extend(provider_failures or [])
                try:
                    if not isinstance(response, str) or not response.strip():
                        raise ValueError('Chinese Novel empty model output')
                    accepted = preserve_source_markup(source, response, settings, registry)
                except ValueError as exc:
                    output_error = exc
                else:
                    diagnostics['accepted_parts'] += 1
                    for speaker in speaker_names(accepted):
                        if speaker not in speakers:
                            speakers.append(speaker)
                    return accepted
            last_kind = _failure_kind(output_error)
            diagnostics['errors'].append({'kind': last_kind,
                'source_units': count_text_units(source),
                'output_chars': len(response) if isinstance(response, str) else 0})

        if span_recovery or prefer_source_locked:
            from .span_annotation import annotate_source_spans, SpanAnnotationError
            def label_spans(prompt):
                if diagnostics['calls'] >= max_calls:
                    stop('model-call budget exhausted')
                diagnostics['calls'] += 1
                return generate(prompt)
            try:
                locked = annotate_source_spans(source, generate=label_spans, context=preceding,
                    novel_settings=settings, character_registry=registry,
                    prompt_prefix=prompt_prefix, known_speakers=speakers,
                    correction_attempts=correction_attempts)
            except SpanAnnotationError:
                last_kind = 'invalid_span_annotations'
                diagnostics['errors'].append({'kind': 'invalid_span_annotations',
                    'source_units': count_text_units(source), 'output_chars': 0})
            else:
                last_profile = locked['profile']
                failures.extend(locked['failures'])
                diagnostics['accepted_parts'] += 1
                diagnostics['source_locked_parts'] += 1
                accepted = locked['result_text']
                for speaker in speaker_names(accepted):
                    if speaker not in speakers:
                        speakers.append(speaker)
                return accepted

        units = count_text_units(source)
        if units <= min_units:
            stop(f'{last_kind} persisted at minimum segment size')
        target = max(min_units, (units + 1) // 2)
        children = chunk_text_units(source, target)
        if len(children) < 2:
            stop(f'{last_kind}; source could not be safely divided')
        diagnostics['splits'] += 1
        outputs, child_context = [], preceding
        for child in children:
            outputs.append(process(child, child_context))
            overlap = settings['context_overlap']
            child_context = (child_context + child)[-overlap:] if overlap else ''
        return join_novel_sections(source, [{'content': child} for child in children], outputs)

    result = process(content, context)
    diagnostics['recovered'] = bool(diagnostics['errors'])
    return {'result_text': result, 'profile': last_profile, 'failures': failures,
            'diagnostics': diagnostics}

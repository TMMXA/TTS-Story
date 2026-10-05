"""Run the real Prep/profile routes against an existing remote text model.

No model or engine installation is performed. Configuration is changed only in
this process. Outputs go to a caller-selected directory for manual review.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--input', type=Path, default=ROOT / 'tests/fixtures/chinese_novel_smoke.txt')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--preset', choices=['chinese-novel', 'chinese-novel-directed', 'chinese-novel-first-person'], default='chinese-novel')
    parser.add_argument('--protagonist', default='叶临渊')
    args = parser.parse_args()
    import app as application
    from src.chinese_novel.prompts import join_novel_sections, with_chinese_novel_presets
    from src.tag_validation import TAG
    from src.text_processor import TextProcessor
    config = dict(application.DEFAULT_CONFIG, llm_provider='local', llm_local_provider='lmstudio',
                  llm_local_base_url=args.base_url, llm_local_model=args.model,
                  llm_local_disable_reasoning=True, llm_local_max_tokens=6000,
                  llm_local_temperature=0.1, llm_backup_profiles=[])
    application.load_config = lambda: config
    client = application.app.test_client()
    source = args.input.read_text(encoding='utf-8')
    novel = {'language': 'Chinese', 'context_overlap': 300, 'chunk_size': 4000}
    if args.preset == 'chinese-novel-first-person':
        novel.update(narrative_mode='first_person', first_person_protagonist=args.protagonist)
    prompt = next(entry['prompt'] for entry in with_chinese_novel_presets([]) if entry['id'] == args.preset)
    registry = [{'display_name': '叶临渊', 'aliases': ['临渊', '叶兄', '叶公子']}]
    sections = client.post('/api/gemini/sections', json={
        'text': source, 'prefer_chapters': True, 'novel_settings': novel,
        'section_headings': ['chapter', '第*章'],
    }).get_json()
    if not sections.get('success'):
        raise RuntimeError(sections)
    outputs, speakers = [], []
    for index, section in enumerate(sections['sections'], 1):
        response = client.post('/api/gemini/process-section', json={
            **section, 'prompt_override': prompt, 'novel_settings': novel,
            'character_registry': registry, 'known_speakers': speakers,
        })
        payload = response.get_json()
        if not payload.get('success'):
            raise RuntimeError(f'Section {index}: {payload}')
        outputs.append(payload['result_text'])
        speakers = list(dict.fromkeys([*speakers, *payload['speakers']]))
        print(f'Section {index} accepted; speakers={speakers}', flush=True)
    prepared = join_novel_sections(source, sections['sections'], outputs)
    prose = re.sub(r'\[(direction|emotion)\][\s\S]*?\[/\1\]', '', prepared, flags=re.I)
    assert TAG.sub('', prose) == source, 'Prepared text changed source or whitespace'
    assert len(application.split_text_into_book_sections(prepared, ['chapter'])['sections']) == len(sections['sections'])
    assert TextProcessor().has_speaker_tags(prepared)
    segments = TextProcessor().parse_speaker_segments(prepared)
    if args.input.name == 'chinese_first_person_smoke.txt':
        for dialogue in ('“叶兄，你总算回来了。”', '“叶公子，前面就是村口了。”'):
            owners = [segment['speaker'] for segment in segments if dialogue in segment['text']]
            assert owners == ['林清雪'], f'Wrong speaker for {dialogue}: {owners}'
        if args.preset == 'chinese-novel-first-person':
            assert all(segment['speaker'] == args.protagonist for segment in segments
                       if '她指着不远处的炊烟。' in segment['text'] or '我叫叶临渊' in segment['text'])
    elif args.input.name == 'chinese_novel_smoke.txt':
        assert all(segment['speaker'] == '叶临渊' for segment in segments
                   if '“临渊羡鱼' in segment['text'] or '“终于出来了。”' in segment['text'])
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'prepared.txt').write_text(prepared, encoding='utf-8')
    profile_response = client.post('/api/gemini/speaker-profiles', json={
        'speakers': speakers, 'processed_text': prepared, 'context': source,
        'novel_settings': novel,
    })
    profile_payload = profile_response.get_json()
    (args.output / 'profiles.json').write_text(json.dumps(profile_payload, ensure_ascii=False, indent=2), encoding='utf-8')
    if not profile_payload.get('success'):
        raise RuntimeError(profile_payload)
    print('Chinese Prep and profile routes passed against remote model.', flush=True)


if __name__ == '__main__':
    main()

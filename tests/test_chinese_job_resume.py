"""Chinese clone jobs retain voice identity and audio across real queue checkpoints.

Only synthesis and final merging are mocked; parsing, chapter detection,
assignment transport, chunk metadata and the pause/resume pipeline run normally.
"""
from pathlib import Path
import wave

import pytest
import app as app_module


@pytest.mark.parametrize('engine_name', ['qwen3_clone', 'index_tts'])
def test_chinese_clone_job_pauses_twice_without_changing_reference_or_replaying_audio(
        monkeypatch, tmp_path, engine_name):
    job_id = 'chinese-resume-' + engine_name
    texts = ['他推开石门。', '“别来无恙。”', '她点了点头。',
             '夜雨落下。', '“我一直在等你。”', '他望向窗外。']
    speakers = ['旁白', '叶临渊', '林清雪', '旁白', '林清雪', '叶临渊']
    chapter_titles = ['第一章 风雪', '第２章 夜雨']
    lines = []
    for i, text in enumerate(texts):
        if i in {0, 3}:
            lines.append(chapter_titles[i // 3])
        lines.append(f'[{speakers[i]}]{text}[/{speakers[i]}]')
    source = '\n'.join(lines)
    assignments = {speaker: {'voice': '', 'prompt': f'reference-{index}.wav',
                    'extra': {'prompt_text': f'{speaker}的中文参考录音。'}}
                   for index, speaker in enumerate(dict.fromkeys(speakers))}
    rendered, manifests = [], []

    class Engine:
        sample_rate = 24000
        device = 'mock'

        def generate_batch(self, segments, voice_config, output_dir, speed=1,
                           progress_cb=None, chunk_cb=None):
            files, order = [], 0
            for si, segment in enumerate(segments):
                speaker = segment['speaker']
                assert voice_config[speaker] == assignments[speaker]
                for ci, text in enumerate(segment['chunks']):
                    target = Path(output_dir) / f'chunk_{order:06d}.wav'
                    with wave.open(str(target), 'wb') as wav:
                        wav.setnchannels(1)
                        wav.setsampwidth(2)
                        wav.setframerate(24000)
                        wav.writeframes((len(rendered) + 1).to_bytes(2, 'little') * 240)
                    rendered.append((speaker, text))
                    if len(rendered) in {2, 5}:
                        app_module.pause_flags[job_id] = True
                    progress_cb()
                    chunk_cb(ci, {'segment_index': si, 'chunk_index': ci, 'order_index': order}, str(target))
                    files.append(str(target))
                    order += 1
            return files

    monkeypatch.setattr(app_module, 'OUTPUT_DIR', tmp_path)
    for name in ('jobs', 'pause_flags', 'cancel_flags', 'cancel_events'):
        monkeypatch.setattr(app_module, name, {})
    monkeypatch.setattr(app_module, '_persist_job_state', lambda *args, **kwargs: None)
    monkeypatch.setattr(app_module, 'get_tts_engine', lambda *args, **kwargs: Engine())

    def merge(_job_id, entry, manifest):
        manifests.append(manifest)
        entry['status'] = 'completed'
    monkeypatch.setattr(app_module, '_merge_review_job', merge)
    config = {**app_module.DEFAULT_CONFIG, 'tts_engine': engine_name}
    data = {'job_id': job_id, 'text': source, 'config': config,
            'voice_assignments': assignments, 'total_chunks': 6,
            'review_mode': True, 'split_by_chapter': True, 'generate_full_story': True}
    entry = {'status': 'processing', 'total_chunks': 6, 'config_snapshot': config}
    app_module.jobs[job_id] = entry
    preserved = {}
    for expected in (2, 5, 6):
        data['resume_from_chunk_index'] = entry.get('resume_from_chunk_index', 0)
        entry['status'] = 'processing'
        app_module._process_audio_job(data)
        assert entry['processed_chunks'] == expected, entry.get('error')
        assert len(entry['chunks']) == expected
        for path, content in preserved.items():
            assert Path(path).read_bytes() == content
        preserved = {c['file_path']: Path(c['file_path']).read_bytes() for c in entry['chunks']}
        if expected < 6:
            assert entry['status'] == 'paused'
    assert rendered == list(zip(speakers, texts))
    assert entry['status'] == 'completed'
    assert [c['speaker'] for c in entry['chunks']] == speakers
    assert [c['text'] for c in entry['chunks']] == texts
    assert len(set(c['id'] for c in entry['chunks'])) == 6
    assert len(set(c['file_path'] for c in entry['chunks'])) == 6
    assert {Path(c['file_path']).parent.parent.name for c in entry['chunks']} == {'chapter_01', 'chapter_02'}
    for chunk in entry['chunks']:
        assert chunk['voice_assignment'] == assignments[chunk['speaker']]
    assert len(manifests[-1]['all_full_story_chunks']) == 6
    assert [c['title'] for c in manifests[-1]['chapters']] == chapter_titles

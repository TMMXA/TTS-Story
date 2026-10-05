from __future__ import annotations

import base64
import io
from types import SimpleNamespace

import numpy as np

import app as app_module
from src.chinese_novel.voice_design import (
    CHINESE_STANDARD_PREVIEW_TEXT,
    pad_voice_preview,
    resolve_voice_language,
)


def test_voice_language_honors_explicit_language_then_novel_then_source():
    assert resolve_voice_language({"language": "Chinese"}) == "Chinese"
    assert resolve_voice_language({"language": "English", "text": "中文"}) == "English"
    assert resolve_voice_language({"novel_settings": {"language": "Chinese"}}) == "Chinese"
    assert resolve_voice_language({"language": "Auto", "text": "你好，世界。"}) == "Chinese"
    assert resolve_voice_language({"text": "Hello, world."}) == "English"
    assert resolve_voice_language({"language": "Japanese"}) == "Japanese"


def test_chinese_preview_uses_cjk_length_and_chinese_padding():
    short = pad_voice_preview("终于出来了。", "Chinese")
    assert len(short) >= 60
    assert "The speaker" not in short
    assert "终于出来了。" in short
    assert pad_voice_preview(CHINESE_STANDARD_PREVIEW_TEXT, "Chinese") == CHINESE_STANDARD_PREVIEW_TEXT
    assert len(pad_voice_preview("A short line.", "English").split()) >= 40


def test_structured_chinese_profile_uses_chinese_language():
    instruction, language = app_module._build_qwen_voice_design_instruction({
        "gender": "Male", "voice_type": "低沉、清晰、平稳的青年男声", "language": "Chinese",
    })
    assert language == "Chinese"
    assert instruction.startswith("YOUNG ADULT MALE VOICE")


def test_chinese_profile_fallback_uses_mandarin_and_preserves_stable_voice():
    prompt = app_module.build_profile_voice_design_prompt({
        "name": "叶临渊", "voice": "青年男声，音色略干，语速平稳", "language": "Chinese",
        "description": "正在哭喊，十分悲伤。",
    })
    assert prompt.startswith("YOUNG ADULT MALE VOICE")
    assert "Standard Mandarin" in prompt
    assert "English" not in prompt
    assert "哭喊" not in prompt


def test_explicit_design_age_overrides_youthful_timbre_wording():
    prompt = app_module.build_profile_voice_design_prompt({
        "name": "叶临渊", "voice": "带少年感的清冽音色", "language": "Chinese",
        "voice_design_prompt": "YOUNG ADULT MALE VOICE. Clear tenor, measured pace, Standard Mandarin.",
    })
    assert prompt.startswith("YOUNG ADULT MALE VOICE")


def test_chinese_preview_worker_payload_is_chinese_and_exact(monkeypatch):
    captured = {}

    def fake_worker(payload):
        captured.update(payload)
        app_module.sf.write(payload["output_path"], [0.0] * (24_000 * 11), 24_000)
        return {"sample_rate": 24_000}

    monkeypatch.setattr(app_module, "_run_isolated_qwen_voice_design", fake_worker)
    monkeypatch.setattr(app_module, "_apply_voice_design_cleanup", lambda audio, _rate: audio)
    result = app_module._generate_voice_design_preview({
        "gender": "Male", "voice_type": "青年男声，低沉平稳", "text": "终于出来了。",
        "novel_settings": {"language": "Chinese"}, "seed": 37,
    }, {})
    assert captured["language"] == result["language"] == "Chinese"
    assert captured["text"] == result["preview_text"]
    assert "The speaker" not in captured["text"]
    assert result["seed"] == 37


def test_saved_chinese_reference_matches_generated_transcript(tmp_path, monkeypatch):
    buffer = io.BytesIO()
    app_module.sf.write(buffer, [0.0] * (24_000 * 11), 24_000, format="wav")
    saved = {}
    monkeypatch.setattr(app_module, "VOICE_PROMPT_DIR", tmp_path)
    monkeypatch.setattr(app_module, "_load_chatterbox_voice_entries", lambda: [])
    monkeypatch.setattr(app_module, "_save_chatterbox_voice_entries", lambda entries: saved.update(entries=entries))
    monkeypatch.setattr(app_module, "_set_voice_prompt_transcript", lambda path, text: saved.update(transcript=text))
    monkeypatch.setattr(app_module, "_serialize_chatterbox_voice", lambda entry: entry)
    text = "这是生成时实际使用的中文台词。"
    entry = app_module._save_voice_design_payload({
        "name": "叶临渊", "speaker": "叶临渊", "text": text, "preview_text": text,
        "language": "Chinese", "instruction": "YOUNG ADULT MALE VOICE. Standard Mandarin.",
        "seed": 37, "cleanup_applied": True,
        "audio_base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
    })
    assert saved["transcript"] == text
    assert entry["language"] == "Chinese"
    assert entry["voice_design"]["preview_text"] == text
    assert entry["voice_design"]["speaker"] == "叶临渊"
    assert entry["voice_design"]["seed"] == 37


def test_chinese_profile_request_supplies_default_when_prompt_empty(monkeypatch):
    prompts = []
    monkeypatch.setattr(app_module, "load_config", lambda: {"llm_provider": "local", "gemini_speaker_profile_prompt": ""})

    def fake_run(prompt, config):
        prompts.append(prompt)
        return ('| Character Name | Full Description | Voice Type | Voice Design Prompt |\n'
                '| --- | --- | --- | --- |\n'
                '| 叶临渊 | 沉静坚韧的青年男性。 | 低音青年男声，音色略干，节奏平稳 | YOUNG ADULT MALE VOICE. Low tenor, dry timbre, measured pace, Standard Mandarin. |',
                {"provider": "local", "name": "test"}, [])

    monkeypatch.setattr(app_module, "_run_llm_prompt_with_failover", fake_run)
    response = app_module.app.test_client().post("/api/gemini/speaker-profiles", json={
        "speakers": ["叶临渊"], "novel_settings": {"language": "Chinese"},
        "processed_text": "[叶临渊]终于出来了。[/叶临渊]",
    })
    assert response.status_code == 200
    assert "普通话" in prompts[0]
    assert response.get_json()["profiles"]["叶临渊"]["voice_design_language"] == "Chinese"


def test_clone_reuses_saved_chinese_reference_and_transcript_across_chunks(tmp_path, monkeypatch):
    from src.engines.qwen3_voice_clone_engine import Qwen3VoiceCloneEngine

    buffer = io.BytesIO()
    app_module.sf.write(buffer, np.zeros(24_000 * 11), 24_000, format="wav")
    monkeypatch.setattr(app_module, "VOICE_PROMPT_DIR", tmp_path)
    monkeypatch.setattr(app_module, "_voice_prompt_transcript_cache", None)
    monkeypatch.setattr(app_module, "_load_chatterbox_voice_entries", lambda: [])
    monkeypatch.setattr(app_module, "_save_chatterbox_voice_entries", lambda entries: None)
    monkeypatch.setattr(app_module, "_serialize_chatterbox_voice", lambda entry: entry)
    transcript = CHINESE_STANDARD_PREVIEW_TEXT
    voice = app_module._save_voice_design_payload({
        "name": "叶临渊", "speaker": "叶临渊", "text": transcript,
        "language": "Chinese", "cleanup_applied": True,
        "audio_base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
    })
    reference = str(tmp_path / voice["file_name"])
    calls = []

    def fake_clone(**kwargs):
        calls.append(kwargs)
        return [np.zeros(240, dtype=np.float32)], 24_000

    # Bypass initialization: the real adapter receives a fake model and reads
    # the saved transcript file; no model loader or ASR can be reached.
    engine = Qwen3VoiceCloneEngine.__new__(Qwen3VoiceCloneEngine)
    engine.model = SimpleNamespace(generate_voice_clone=fake_clone)
    engine.default_language = "English"
    engine.default_prompt = None
    engine.default_prompt_text = None
    engine._sample_rate = 24_000
    engine._transcript_cache = {}
    engine._transcripts_file = tmp_path / "transcripts.json"
    engine._asr_model = None
    engine.post_processor = SimpleNamespace(apply_post_pipeline=lambda audio, sr, fx: audio)
    engine._load_persistent_transcripts()
    segments = [
        {"speaker": "叶临渊", "chunks": ["第一章中的台词。", "同一角色的第二句。"]},
        {"speaker": "旁白", "chunks": ["山风迎面而来。"]},
        {"speaker": "叶临渊", "chunks": ["第二章中的台词。"]},
    ]
    assignments = {speaker: {"audio_prompt_path": reference, "extra": {"language": "Chinese"}}
                   for speaker in ("叶临渊", "旁白")}
    files = engine.generate_batch(segments, assignments, tmp_path / "chunks", group_by_speaker=True)
    assert len(files) == 4
    assert [kwargs["text"] for kwargs in calls] == ["第一章中的台词。", "同一角色的第二句。", "第二章中的台词。", "山风迎面而来。"]
    assert all(kwargs["language"] == "Chinese" for kwargs in calls)
    assert all(kwargs["ref_audio"] == reference for kwargs in calls)
    assert all(kwargs["ref_text"] == transcript for kwargs in calls)
    assert all(kwargs["x_vector_only_mode"] is False for kwargs in calls)
    assert [file.rsplit("chunk_", 1)[1] for file in files] == ["0000.wav", "0001.wav", "0002.wav", "0003.wav"]

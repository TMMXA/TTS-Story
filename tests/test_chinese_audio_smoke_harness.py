"""Offline contracts for the HTTP harness; no Flask or model imports."""

import base64
import importlib.util
import io
import json
import re
import struct
import wave
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "chinese_audio_smoke.py"
spec = importlib.util.spec_from_file_location("audio_smoke", SCRIPT)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def wav_bytes(value=100):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(struct.pack("<h", value) * 80_000)
    return buffer.getvalue()


def args(tmp_path):
    return smoke.parse_args(["--base-url", "http://localhost:5000", "--output", str(tmp_path),
                             "--timeout", "2", "--poll-interval", ".01"])


def test_voices_checkpoint_real_endpoint_contract_and_can_resume(tmp_path):
    class FakeHTTP(smoke.Harness):
        def __init__(self, arguments):
            super().__init__(arguments)
            self.requests, self.tasks, self.references = [], {}, {}

        def json(self, route, payload=None, *, method=None):
            self.requests.append((route, payload))
            if route == "/api/qwen3/voice-design/preview":
                task_id = f"task-{len(self.tasks)}"
                audio = wav_bytes(len(self.tasks) + 100)
                evidence = smoke.audio_evidence(audio, "wav")
                self.tasks[task_id] = {"audio_base64": base64.b64encode(audio).decode(),
                    "preview_text": payload["text"], "language": payload["language"], "seed": payload["seed"],
                    "instruction": payload["voice_design_prompt"], "wav_sha256": evidence["sha256"],
                    "duration_seconds": 10, "cleanup_applied": True}
                return {"success": True, "job_id": task_id}
            if route == "/api/qwen3/voice-design/save":
                task_id = f"task-{len(self.tasks)}"
                voice_id = f"voice-{len(self.references)}"
                voice = {"id": voice_id, "prompt_path": voice_id + ".wav", "language": payload["language"],
                    "transcript": payload["text"], "is_valid_prompt": True, "missing_file": False,
                    "voice_design": {key: payload[key] for key in
                        ("speaker", "seed", "instruction", "language", "preview_text", "candidate_group_id")},
                    "archived": False}
                self.references[voice_id] = voice
                self.tasks[task_id] = voice
                return {"success": True, "job_id": task_id}
            if route.startswith("/api/qwen3/voice-design/tasks/"):
                return {"success": True, "status": "completed", "result": self.tasks[route.rsplit("/", 1)[1]]}
            if route == "/api/qwen3/voice-design/candidates/approve":
                for voice_id in payload["candidate_ids"]:
                    selected = voice_id == payload["selected_id"]
                    self.references[voice_id]["archived"] = not selected
                    self.references[voice_id]["voice_design"]["approval_status"] = "approved" if selected else "rejected"
                return {"success": True, "voice": self.references[payload["selected_id"]]}
            if route == "/api/chatterbox-voices":
                return {"success": True, "voices": list(self.references.values())}
            raise AssertionError(route)

    harness = FakeHTTP(args(tmp_path))
    harness.voices()
    assert len(harness.references) == 4
    assert len(list(tmp_path.glob("*.wav"))) == 4
    persisted = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert "audio_base64" not in json.dumps(persisted)
    assert all(role["selected"]["transcript"] == smoke.PREVIEW_TEXT for role in persisted["roles"].values())
    before = sum(payload is not None for _, payload in harness.requests)
    harness.voices()
    assert sum(payload is not None for _, payload in harness.requests) == before


def test_unknown_post_outcome_blocks_duplicate_mutation_and_saved_response_recovers(tmp_path, monkeypatch):
    harness = smoke.Harness(args(tmp_path))
    def timeout(*args, **kwargs):
        raise smoke.SmokeError("Transport timed out")
    monkeypatch.setattr(harness, "json", timeout)
    with pytest.raises(smoke.SmokeError, match="timed out"):
        harness.post_once("generate", "/api/generate", {"text": "中文"})
    restarted = smoke.Harness(args(tmp_path))
    with pytest.raises(smoke.SmokeError, match="Unresolved POST"):
        restarted.post_once("generate", "/api/generate", {})
    restarted.state.pop("pending_post")
    restarted.state["last_post"] = {"operation": "generate", "response": {"job_id": "already-created"}}
    monkeypatch.setattr(restarted, "json", timeout)
    assert restarted.post_once("generate", "/api/generate", {})["job_id"] == "already-created"


def test_chunk_identity_accepts_local_chapter_order_but_rejects_duplicates_and_gaps():
    chunks = [{"id": f"{chapter}-{index}", "chapter_index": chapter, "order_index": index,
               "relative_file": f"chapter{chapter}/chunk{index}.wav"}
              for chapter in (0, 1) for index in (0, 1)]
    smoke.validate_chunk_identity(chunks)
    with pytest.raises(smoke.SmokeError, match="duplicated"):
        smoke.validate_chunk_identity(chunks + [chunks[0]])
    with pytest.raises(smoke.SmokeError, match="missing/replayed"):
        smoke.validate_chunk_identity([chunks[1], *chunks[2:]])


def test_audio_evidence_rejects_silence_and_error_document():
    with pytest.raises(smoke.SmokeError, match="zero samples"):
        smoke.audio_evidence(wav_bytes(0), "wav")
    with pytest.raises(smoke.SmokeError, match="MP3"):
        smoke.audio_evidence(b'{"error": "Audio not found"}' * 10, "mp3")
    assert smoke.audio_evidence(wav_bytes(100), "wav")["duration_seconds"] == 10


def test_pause_resume_checks_completed_audio_identity_before_regeneration(tmp_path):
    class FakeReviewHTTP(smoke.Harness):
        def __init__(self, arguments):
            super().__init__(arguments)
            self.state["job_id"] = "test-production"
            self.status, self.corrupt_saved_audio = "processing", False
            self.assignment = {speaker: {"audio_prompt_path": speaker + ".wav",
                                        "extra": {"language": "Chinese", "prompt_text": smoke.PREVIEW_TEXT}}
                               for speaker in ("旁白", "叶临渊")}
            self.records = []
            for chapter, body in enumerate(smoke.STORY.split("第二章 山外")):
                for index, match in enumerate(re.finditer(r"\[([^\]/]+)\](.*?)\[/\1\]", body)):
                    self.records.append({"id": f"{chapter}-{index}", "chapter_index": chapter,
                        "order_index": index, "speaker": match[1], "text": match[2],
                        "relative_file": f"chapter{chapter}/chunk{index}.wav",
                        "file_url": f"/static/audio/test/chapter{chapter}/chunk{index}.wav",
                        "voice_assignment": self.assignment[match[1]]})

        def assignments(self):
            return self.assignment

        def job(self):
            return {"status": self.status, "processed_chunks": 1 if self.status in {"processing", "paused"} else 8,
                    "total_chunks": 8, "engine": "qwen3_clone", "review_mode": True}

        def chunks(self):
            return {"chunks": self.records[:1] if self.status == "paused" else self.records}

        def post_once(self, operation, route, payload):
            assert route == "/api/jobs/test-production/pause"
            self.status = "paused"
            return {"success": True}

        def json(self, route, payload=None, *, method=None):
            assert route == "/api/jobs/test-production/details"
            return {"job": {"text": smoke.STORY.strip()}}

        def download(self, route, filename, kind):
            assert route.startswith("/static/audio/test/")
            return {"sha256": "rewritten" if self.corrupt_saved_audio else "unchanged", "file": filename}

    harness = FakeReviewHTTP(args(tmp_path))
    harness.pause()
    assert harness.state["paused_chunks"][0]["id"] == "0-0"
    assert harness.state["paused_chunks"][0]["audio"]["sha256"] == "unchanged"
    harness.status = "waiting_review"
    harness.review()
    # Production auto-finishes into the Library while retaining chunk review.
    harness.status = "completed"
    harness.review()
    harness.corrupt_saved_audio = True
    with pytest.raises(smoke.SmokeError, match="already completed chunk"):
        harness.review()


def test_completed_review_job_still_recompiles_after_regeneration(tmp_path, monkeypatch):
    harness = smoke.Harness(args(tmp_path))
    harness.state["job_id"] = "already-completed-review"
    calls = []
    monkeypatch.setattr(harness, "chunks", lambda: {"review": {"status": "completed"}})
    monkeypatch.setattr(harness, "job", lambda: {"status": "completed", "review_mode": True})
    def recompile(operation, route, payload):
        calls.append((operation, route, payload))
        return {"success": True}
    monkeypatch.setattr(harness, "post_once", recompile)
    harness.finish()
    assert calls == [("finish", "/api/jobs/already-completed-review/review/finish", {})]
    assert harness.state["completed_job"]["status"] == "completed"

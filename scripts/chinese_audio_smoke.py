"""Run real Chinese VoiceDesign/Clone HTTP queue checks against an existing server.

No Flask, speech engines, model loaders, SSH clients or credentials are imported.
Each phase checkpoints IDs in OUTPUT/state.json and can be resumed separately.
Example: python scripts/chinese_audio_smoke.py --base-url http://localhost:7860 \
    --output /tmp/chinese-audio-smoke --phase all --timeout 7200

The server's existing models must already be available. This leaves its test
references and production in place for listening/review; it never deletes them.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import re
import sys
import time
import uuid
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


PREVIEW_TEXT = (
    "当你听到这段声音时，应该能够清楚地感受到我的语气和声音特点。"
    "也许它与你最初想象的并不完全相同。请仔细听，"
    "我会从安静而克制的思考，逐渐转向清晰、坚定而有力量的表达。"
)
STORY = """第一章 石室

[旁白]山风还没有吹进石室，叶临渊站在石门之前，低头看着手中的古剑。[/旁白]
[叶临渊]我已经想好了。无论前方还有多少困难，都先走出去，再慢慢寻找答案。[/叶临渊]
[旁白]他收起长剑，沿着石阶向前走去。门外的天空正在一点一点亮起来。[/旁白]
[叶临渊]这里的路比我记忆中更加安静，但只要一直向前，总会找到熟悉的地方。[/叶临渊]

第二章 山外

[旁白]山风迎面而来，远处的村落升起了炊烟，脚下的道路通向清澈的河流。[/旁白]
[叶临渊]终于出来了。先到村子里问问情况，再决定接下来应该往哪里走。[/叶临渊]
[旁白]叶临渊抬头望向远处，整理好衣袖，沿着山路走进了清晨的阳光里。[/旁白]
[叶临渊]我会记住今天的风声。等一切平静下来，也许还能回到这里看看。[/叶临渊]
"""
ROLES = {
    "narrator": {
        "speaker": "旁白", "gender": "Neutral",
        "voice_type": "平稳、中性、清晰的叙述声线，节奏舒缓",
        "voice_design_prompt": "ADULT GENDER-NEUTRAL VOICE. Clear warm timbre, measured pace, Standard Mandarin, calm natural delivery.",
    },
    "protagonist": {
        "speaker": "叶临渊", "gender": "Male",
        "voice_type": "清冽的青年男声，低音域，略干的音色，语速平稳",
        "voice_design_prompt": "YOUNG ADULT MALE VOICE. Low clear tenor, slightly dry timbre, measured pace, Standard Mandarin, restrained delivery.",
    },
}
PHASES = ("voices", "generate", "pause", "resume", "review", "regen-chunk", "regen-speaker", "finish", "downloads")


class SmokeError(RuntimeError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise SmokeError(message)


def validate_chunk_identity(chunks: list[dict]) -> None:
    require(chunks, "No generated chunks")
    for field in ("id", "relative_file"):
        values = [chunk.get(field) for chunk in chunks]
        require(all(values) and len(set(values)) == len(values), f"Chunk {field} values are missing or duplicated")
    # Production order_index is local to each chapter, not global to the job.
    positions = [(chunk.get("chapter_index"), chunk.get("order_index")) for chunk in chunks]
    require(all(all(value is not None for value in position) for position in positions)
            and len(set(positions)) == len(positions), "Chunk chapter/order positions are missing or duplicated")
    for chapter in {position[0] for position in positions}:
        indices = sorted(position[1] for position in positions if position[0] == chapter)
        require(indices == list(range(len(indices))), f"Chapter {chapter} has missing/replayed chunk order indices")


def audio_evidence(data: bytes, kind: str) -> dict[str, Any]:
    """Check actual downloadable bytes; this does not judge speech naturalness."""
    require(len(data) > 128, "Downloaded audio is empty or implausibly small")
    evidence: dict[str, Any] = {"size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    if kind == "wav":
        try:
            with wave.open(io.BytesIO(data), "rb") as wav:
                frames = wav.readframes(wav.getnframes())
                require(wav.getframerate() > 0 and wav.getnframes() > 0, "Invalid WAV header")
                require(any(frames), "WAV contains only zero samples")
                evidence.update(duration_seconds=wav.getnframes() / wav.getframerate(),
                                sample_rate=wav.getframerate(), channels=wav.getnchannels())
        except wave.Error as exc:
            raise SmokeError(f"Invalid PCM WAV: {exc}") from exc
    elif kind == "mp3":
        require(data.startswith(b"ID3") or any(data[i] == 255 and data[i + 1] & 224 == 224
                                             for i in range(min(len(data) - 1, 16384))),
                "Download lacks an MP3 header/frame sync")
    return evidence


class Harness:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.output = args.output.resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        self.state_path = self.output / "state.json"
        self.base_url = args.base_url.rstrip("/")
        parsed = urlsplit(self.base_url)
        require(parsed.scheme in {"http", "https"} and parsed.netloc, "Provide an HTTP(S) Flask base URL")
        require(not parsed.username and not parsed.password and not parsed.query and not parsed.fragment,
                "Base URL must not contain credentials, query parameters or fragments")
        if self.state_path.exists():
            self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
            require(self.state["base_url"] == self.base_url, "State belongs to another server; use another output directory")
            require(self.state.get("candidates") == args.candidates,
                    "Candidate count differs from saved run; preserve --candidates or start a new output directory")
        else:
            self.state = {"base_url": self.base_url, "run_id": uuid.uuid4().hex[:12],
                          "created_at": datetime.now(timezone.utc).isoformat(), "candidates": args.candidates,
                          "completed_phases": [], "roles": {}, "events": []}
            (self.output / "story.txt").write_text(STORY, encoding="utf-8")
            self.save()

    def save(self) -> None:
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.state_path)

    def event(self, action: str, **details: Any) -> None:
        self.state["events"].append({"at": datetime.now(timezone.utc).isoformat(), "action": action, **details})
        self.save()
        print(f"[{action}] {json.dumps(details, ensure_ascii=False)}", flush=True)

    def json(self, route: str, payload: dict | None = None, *, method: str | None = None) -> dict:
        method = method or ("POST" if payload is not None else "GET")
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        request = Request(self.base_url + route, data=body, method=method,
                          headers={"Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urlopen(request, timeout=self.args.http_timeout) as response:
                value = json.load(response)
        except HTTPError as exc:
            raise SmokeError(f"{method} {route}: HTTP {exc.code}: {exc.read(2000).decode('utf-8', 'replace')}") from exc
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            raise SmokeError(f"{method} {route}: {exc}. A timed-out POST may have succeeded; do not blindly repeat it.") from exc
        require(value.get("success") is not False, f"{method} {route}: {value.get('error', value)}")
        return value

    def post_once(self, operation: str, route: str, payload: dict) -> dict:
        # Persist an unknown-outcome marker BEFORE mutation. Recovery requires
        # checking the server, avoiding silently submitting a duplicate GPU job.
        require(not self.state.get("pending_post"),
                f"Unresolved POST in state: {self.state.get('pending_post')}. Inspect the server and recover its ID before clearing this marker.")
        previous = self.state.get("last_post") or {}
        if previous.get("operation") == operation:
            return previous["response"]
        self.state["pending_post"] = {"operation": operation, "route": route,
                                      "at": datetime.now(timezone.utc).isoformat()}
        self.save()
        try:
            value = self.json(route, payload)
        except SmokeError as exc:
            # A returned HTTP error is a known failure; transport timeout is not.
            if "HTTP " in str(exc):
                self.state.pop("pending_post", None)
                self.save()
            raise
        self.state.pop("pending_post", None)
        # Caller writes IDs without further network I/O; include response here
        # so an interruption between these two writes still leaves recoverable ID.
        self.state["last_post"] = {"operation": operation, "response": value}
        self.save()
        return value

    def poll(self, label: str, fetch: Callable[[], dict], ready: Callable[[dict], bool]) -> dict:
        deadline = time.monotonic() + self.args.timeout
        previous = None
        while True:
            value = fetch()
            signature = (value.get("status"), value.get("processed_chunks"), value.get("progress"))
            if signature != previous:
                print(f"[{label}] status={signature[0]} chunks={signature[1]} progress={signature[2]}", flush=True)
                previous = signature
            if value.get("status") in {"failed", "cancelled", "interrupted", "deleted"}:
                self.state["last_failure"] = {"label": label, "response": value}
                self.save()
                raise SmokeError(f"{label}: {value.get('status')}: {value.get('error')}")
            if ready(value):
                return value
            if time.monotonic() >= deadline:
                raise SmokeError(f"{label}: timed out after {self.args.timeout}s; rerun this phase using its saved IDs")
            time.sleep(self.args.poll_interval)

    def task(self, task_id: str) -> dict:
        return self.poll(f"voice task {task_id}",
                         lambda: self.json(f"/api/qwen3/voice-design/tasks/{task_id}"),
                         lambda value: value.get("status") == "completed")["result"]

    def job(self) -> dict:
        require(self.state.get("job_id"), "Run generate first")
        job_id = self.state["job_id"]
        jobs = self.json("/api/queue")["jobs"]
        match = next((entry for entry in jobs if entry["job_id"] == job_id), None)
        require(match, f"Saved job {job_id} is absent from the server queue; inspect recovery before submitting another job")
        return match

    def chunks(self) -> dict:
        require(self.state.get("job_id"), "Run generate first")
        return self.json(f"/api/jobs/{self.state['job_id']}/chunks")

    def voices(self) -> None:
        for role_id, traits in ROLES.items():
            role = self.state["roles"].setdefault(role_id, {"speaker": traits["speaker"],
                "group_id": f"smoke-{self.state['run_id']}-{role_id}", "candidates": []})
            for index in range(self.args.candidates):
                if index >= len(role["candidates"]):
                    role["candidates"].append({"label": chr(65 + index), "requested_seed": self.args.seed + index * 101 + 1000 * len(self.state["roles"])})
                    self.save()
                candidate = role["candidates"][index]
                name = f"Chinese smoke {self.state['run_id']} {role_id} {candidate['label']}"
                payload = {**traits, "name": name, "language": "Chinese", "required_gender": True,
                           "text": PREVIEW_TEXT, "seed": candidate["requested_seed"]}
                if not candidate.get("preview_task_id"):
                    response = self.post_once(f"{role_id}-{index}-preview", "/api/qwen3/voice-design/preview", payload)
                    candidate["preview_task_id"] = response["job_id"]
                    self.save()
                wav_path = self.output / f"{role_id}-{candidate['label']}.wav"
                if not candidate.get("preview"):
                    result = self.task(candidate["preview_task_id"])
                    require(result["language"] == "Chinese", "VoiceDesign returned a non-Chinese language")
                    require(result["preview_text"] == PREVIEW_TEXT, "VoiceDesign changed/padded a sufficiently long Chinese preview")
                    audio = base64.b64decode(result["audio_base64"], validate=True)
                    evidence = audio_evidence(audio, "wav")
                    require(evidence["duration_seconds"] >= 10, "VoiceDesign sample is shorter than 10 seconds")
                    require(evidence["sha256"] == result["wav_sha256"], "Preview audio hash does not match server metadata")
                    wav_path.write_bytes(audio)
                    candidate["preview"] = {key: value for key, value in result.items() if key != "audio_base64"}
                    candidate["audio"] = evidence
                    self.save()
                    self.event("preview_verified", role=role_id, label=candidate["label"], **evidence)
                result = candidate["preview"]
                if not candidate.get("save_task_id"):
                    save_payload = {**payload, **result, "text": result["preview_text"],
                                    "audio_base64": base64.b64encode(wav_path.read_bytes()).decode("ascii"),
                                    "candidate_group_id": role["group_id"], "candidate_label": candidate["label"],
                                    "source_task_id": candidate["preview_task_id"], "approval_status": "pending"}
                    response = self.post_once(f"{role_id}-{index}-save", "/api/qwen3/voice-design/save", save_payload)
                    candidate["save_task_id"] = response["job_id"]
                    self.save()
                if not candidate.get("voice"):
                    candidate["voice"] = self.task(candidate["save_task_id"])
                    self.save()
                voice = candidate["voice"]
                metadata = voice.get("voice_design") or {}
                require(voice.get("language") == "Chinese" and metadata.get("language") == "Chinese", "Saved reference language mismatch")
                require(voice.get("transcript") == result["preview_text"] == metadata.get("preview_text"), "Reference transcript does not match generated preview")
                require(metadata.get("speaker") == traits["speaker"] and metadata.get("seed") == result["seed"], "Saved speaker/seed mismatch")
                require(metadata.get("instruction") == result["instruction"], "Saved instruction mismatch")
                require(voice.get("is_valid_prompt") and not voice.get("missing_file"), "Saved reference file is invalid")
            seeds = [candidate["preview"]["seed"] for candidate in role["candidates"]]
            hashes = [candidate["audio"]["sha256"] for candidate in role["candidates"]]
            require(len(set(seeds)) == len(seeds), "Candidates reused the same actual seed")
            require(len(set(hashes)) == len(hashes), "Candidates produced identical audio")
            if not role.get("selected"):
                require(self.args.approve_index < len(role["candidates"]), "--approve-index exceeds candidate count")
                selected = role["candidates"][self.args.approve_index]["voice"]
                response = self.post_once(f"{role_id}-approve", "/api/qwen3/voice-design/candidates/approve",
                                          {"selected_id": selected["id"], "candidate_group_id": role["group_id"],
                                           "candidate_ids": [item["voice"]["id"] for item in role["candidates"]]})
                role["selected"] = response["voice"]
                self.save()
        actual = {voice["id"]: voice for voice in self.json("/api/chatterbox-voices")["voices"]}
        for role in self.state["roles"].values():
            for candidate in role["candidates"]:
                voice = actual[candidate["voice"]["id"]]
                selected = voice["id"] == role["selected"]["id"]
                require(voice["voice_design"]["approval_status"] == ("approved" if selected else "rejected"), "Candidate approval state mismatch")
                require(bool(voice["archived"]) == (not selected), "Candidate archive state mismatch")

    def assignments(self) -> dict:
        require(all(self.state["roles"].get(role, {}).get("selected") for role in ROLES), "Run voices first")
        return {role["speaker"]: {"audio_prompt_path": role["selected"]["prompt_path"],
                                  "extra": {"language": "Chinese", "prompt_text": role["selected"]["transcript"]}}
                for role in self.state["roles"].values()}

    def generate(self) -> None:
        if self.state.get("job_id"):
            self.event("reuse_job", job_id=self.state["job_id"])
            return
        payload = {"text": STORY, "tts_engine": "qwen3_clone", "voice_assignments": self.assignments(),
                   "engine_options": {"default_language": "Chinese"}, "review_mode": True,
                   "split_by_chapter": True, "generate_full_story": True, "section_headings": ["第*章"],
                   "output_format": "mp3", "output_bitrate_kbps": 128, "acx_compliance": False}
        analyze = self.json("/api/analyze", {"text": STORY, "tts_engine": "qwen3_clone", "section_headings": ["第*章"]})
        require(analyze["statistics"]["section_detection"]["count"] == 2, "Expected exactly two Chinese chapters")
        response = self.post_once("generate", "/api/generate", payload)
        self.state["job_id"] = response["job_id"]
        self.state["generation_payload"] = payload
        self.save()
        self.event("generated", job_id=response["job_id"])

    def pause(self) -> None:
        if self.state.get("pause_observed"):
            return
        def can_pause(job: dict) -> bool:
            require(job.get("status") not in {"waiting_review", "completed"},
                    "Generation already finished before pause; use a fresh run for a genuine pause/resume check")
            return (job.get("status") == "paused" or
                    (job.get("status") == "processing" and
                     int(job.get("processed_chunks") or 0) >= self.args.pause_after_chunks))
        snapshot = self.poll("pause boundary", self.job, can_pause)
        if snapshot["status"] != "paused":
            require(int(snapshot.get("processed_chunks") or 0) < int(snapshot.get("total_chunks") or 0),
                    "All chunks completed before pause; do not claim the pause test passed")
            self.post_once("pause", f"/api/jobs/{self.state['job_id']}/pause", {})
        paused = self.poll("paused", self.job, lambda value: value.get("status") == "paused")
        require(int(paused.get("processed_chunks") or 0) > 0, "Pause must retain at least one generated chunk")
        require(int(paused.get("processed_chunks") or 0) < int(paused.get("total_chunks") or 0),
                "Pause completed after the final chunk; use a fresh run to test genuine partial resume")
        self.state["pause_observed"] = paused
        saved_chunks = self.chunks()["chunks"]
        require(saved_chunks, "Paused production has no persisted chunk metadata")
        snapshot = []
        for index, chunk in enumerate(saved_chunks):
            evidence = self.download(chunk["file_url"], f"paused-chunk-{index:03d}.wav", "wav")
            snapshot.append({key: chunk.get(key) for key in
                             ("id", "order_index", "chapter_index", "relative_file", "file_url", "speaker", "text")}
                            | {"audio": evidence})
        self.state["paused_chunks"] = snapshot
        self.save()
        self.event("pause_verified", processed_chunks=paused.get("processed_chunks"), total_chunks=paused.get("total_chunks"))

    def resume(self) -> None:
        require(self.state.get("pause_observed"), "Run pause first")
        job = self.job()
        if job["status"] == "paused":
            self.post_once("resume", f"/api/jobs/{self.state['job_id']}/resume", {})
        elif job["status"] not in {"queued", "processing", "waiting_review", "completed"}:
            raise SmokeError(f"Cannot resume job in status {job['status']}")
        self.state["resume_requested"] = True
        self.save()

    def review(self) -> None:
        def ready(job: dict) -> bool:
            if job.get("status") in {"waiting_review", "completed"}:
                require(job.get("review_mode") is True, "Completed production is not enabled for chunk review")
                return True
            return False
        snapshot = self.poll("clone generation", self.job, ready)
        require(snapshot.get("engine") == "qwen3_clone", "Generation used the wrong engine")
        require(snapshot.get("processed_chunks") == snapshot.get("total_chunks"), "Not all chunks were generated")
        details = self.json(f"/api/jobs/{self.state['job_id']}/details")["job"]
        require(details["text"] == STORY.strip(), "Queued source text changed")
        chunks = self.chunks()["chunks"]
        validate_chunk_identity(chunks)
        ordered = sorted(chunks, key=lambda chunk: (chunk["chapter_index"], chunk["order_index"]))
        require({chunk["chapter_index"] for chunk in chunks} == {0, 1}, "Expected chunk metadata for exactly two chapters")
        actual_text = "".join(chunk["text"] for chunk in ordered)
        expected_text = "".join(match[2] for match in re.finditer(r"\[([^\]/]+)\](.*?)\[/\1\]", STORY, re.DOTALL))
        require(re.sub(r"\s+", "", actual_text) == re.sub(r"\s+", "", expected_text),
                "Resumed chunks replayed, dropped or reordered source text")
        require([chunk["chapter_index"] for chunk in chunks] == sorted(chunk["chapter_index"] for chunk in chunks),
                "Chunk list is not in Chinese chapter order")
        require({chunk["speaker"] for chunk in chunks} == {"旁白", "叶临渊"}, "Chinese speaker IDs changed")
        assignments = self.assignments()
        for chunk in chunks:
            actual = chunk.get("voice_assignment") or {}
            expected = assignments[chunk["speaker"]]
            require(actual.get("audio_prompt_path") == expected["audio_prompt_path"], "Reference changed across chunks")
            require(actual.get("extra", {}).get("prompt_text") == expected["extra"]["prompt_text"], "Chunk transcript mismatch")
            require(actual.get("extra", {}).get("language") == "Chinese", "Chunk clone language mismatch")
        by_id = {chunk["id"]: chunk for chunk in chunks}
        for index, saved in enumerate(self.state.get("paused_chunks", [])):
            current = by_id.get(saved["id"])
            require(current, "A completed chunk disappeared during resume")
            for field in ("chapter_index", "order_index", "relative_file", "speaker", "text"):
                require(current.get(field) == saved[field], f"Pause/resume changed completed chunk {field}")
            evidence = self.download(current["file_url"], f"resumed-chunk-{index:03d}.wav", "wav")
            require(evidence["sha256"] == saved["audio"]["sha256"], "Resume regenerated/rewrote an already completed chunk")
        self.state["review_chunks"] = chunks
        self.save()
        self.event("review_verified", chunks=len(chunks))

    def regenerate(self, speaker: bool) -> None:
        chunks = self.chunks()["chunks"]
        selected = [chunk for chunk in chunks if chunk["speaker"] == "叶临渊"]
        require(selected, "No protagonist chunks are available")
        selected = selected if speaker else selected[:1]
        label = "speaker_regeneration" if speaker else "chunk_regeneration"
        recorded = self.state.setdefault(label, {})
        for chunk in selected:
            chunk_id = chunk["id"]
            if recorded.get(chunk_id, {}).get("completed"):
                continue
            if not recorded.get(chunk_id, {}).get("requested"):
                self.post_once(f"{label}-{chunk_id}", f"/api/jobs/{self.state['job_id']}/review/regen",
                               {"chunk_id": chunk_id, "text": chunk["text"], "engine": "qwen3_clone",
                                "voice": self.assignments()["叶临渊"]})
                recorded[chunk_id] = {"requested": True}
                self.save()
            def fetch() -> dict:
                response = self.chunks()
                return response.get("regen_tasks", {}).get(chunk_id, {"status": "missing"})
            result = self.poll(label, fetch, lambda value: value.get("status") == "completed")
            recorded[chunk_id].update(completed=True, task=result)
            self.save()
        self.event(label + "_verified", chunks=len(selected))
        final = {chunk["id"]: chunk for chunk in self.chunks()["chunks"]}
        for chunk in selected:
            require(final[chunk["id"]].get("regenerated_at"), "Completed regeneration lacks persisted regenerated_at")

    def finish(self) -> None:
        require(self.chunks()["review"].get("status") in {"waiting_review", "completed"}, "Review is not ready to finish")
        # Review-mode generation can auto-merge and move to the Library. The
        # regenerated chunks still require a real recompile even when its
        # queue status remains completed.
        self.post_once("finish", f"/api/jobs/{self.state['job_id']}/review/finish", {})
        completed = self.poll("merged", self.job, lambda value: value.get("status") == "completed")
        self.state["completed_job"] = completed
        self.save()

    def download(self, route: str, filename: str, kind: str) -> dict:
        try:
            with urlopen(self.base_url + route, timeout=self.args.http_timeout) as response:
                content_type = response.headers.get("Content-Type", "")
                data = response.read()
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise SmokeError(f"Download {route}: {exc}") from exc
        require("json" not in content_type and "html" not in content_type, "Download returned an error document")
        evidence = audio_evidence(data, kind)
        (self.output / filename).write_bytes(data)
        return {"route": route, "file": filename, "content_type": content_type, **evidence}

    def downloads(self) -> None:
        require(self.job()["status"] == "completed", "Run finish first")
        job_id = self.state["job_id"]
        library = self.json(f"/api/library/{job_id}/chunks")
        chapters = library["chapters"]
        require(len(chapters) == 2, "Merged production does not contain exactly two chapters")
        require([chapter["title"] for chapter in chapters] == ["第一章 石室", "第二章 山外"], "Chinese chapter titles changed")
        reports = [self.download(f"/api/download/{job_id}", "Full-Story.mp3", "mp3")]
        for index, chapter in enumerate(chapters, 1):
            require(chapter.get("relative_path"), "Missing chapter output path")
            route = f"/api/download/{job_id}?" + urlencode({"file": chapter["relative_path"]})
            reports.append(self.download(route, f"chapter-{index}.mp3", "mp3"))
        for index, chunk in enumerate(library["chunks"]):
            require(chunk.get("file_url"), "Missing generated chunk audio URL")
            reports.append(self.download(chunk["file_url"], f"chunk-{index:03d}.wav", "wav"))
        require(reports[0]["size_bytes"] > max(report["size_bytes"] for report in reports[1:3]),
                "Full Story download is not larger than either chapter; investigate fallback/merge")
        self.state["downloads"] = reports
        self.state["library"] = library
        self.save()
        self.event("downloads_verified", files=len(reports), job_id=job_id)

    def run(self, phase: str) -> None:
        if phase == "status":
            print(json.dumps({"job": self.job() if self.state.get("job_id") else None,
                              "completed_phases": self.state["completed_phases"],
                              "pending_post": self.state.get("pending_post")}, ensure_ascii=False, indent=2))
            return
        for current in PHASES if phase == "all" else (phase,):
            if current in self.state["completed_phases"]:
                self.event("phase_already_passed", phase=current)
                continue
            if current == "regen-chunk":
                self.regenerate(False)
            elif current == "regen-speaker":
                self.regenerate(True)
            else:
                getattr(self, current)()
            self.state["completed_phases"].append(current)
            self.save()
            self.event("phase_passed", phase=current)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", required=True, help="Existing TTS-Story Flask URL; not the LLM /v1 URL")
    parser.add_argument("--output", type=Path, required=True, help="Persistent run state and listening artifacts")
    parser.add_argument("--phase", choices=("all", "status", *PHASES), default="all")
    parser.add_argument("--timeout", type=float, default=7200, help="Maximum seconds per polling stage")
    parser.add_argument("--http-timeout", type=float, default=300, help="HTTP request timeout; finish merges synchronously")
    parser.add_argument("--poll-interval", type=float, default=2)
    parser.add_argument("--candidates", type=int, choices=(1, 2, 3), default=2)
    parser.add_argument("--approve-index", type=int, default=0, help="Zero-based candidate index to approve for the test")
    parser.add_argument("--seed", type=int, default=610005)
    parser.add_argument("--pause-after-chunks", type=int, default=1)
    args = parser.parse_args(argv)
    if min(args.timeout, args.http_timeout, args.poll_interval) <= 0:
        parser.error("Timeouts and poll interval must be positive")
    if args.pause_after_chunks < 1 or args.approve_index < 0 or args.approve_index >= args.candidates:
        parser.error("Require pause-after-chunks >= 1 and 0 <= approve-index < candidates")
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        harness = Harness(parse_args(argv))
        harness.run(harness.args.phase)
        print(f"State and audio artifacts: {harness.output}", flush=True)
        return 0
    except (SmokeError, KeyboardInterrupt) as exc:
        print(f"Smoke check stopped: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

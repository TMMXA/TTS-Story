"""Resolve full-story downloads across current and legacy audio layouts."""
from __future__ import annotations

import json
from pathlib import Path


def safe_audio_path(job_dir: Path, relative: str | None) -> Path | None:
    if not relative or not isinstance(relative, str):
        return None
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts:
        return None
    candidate = (job_dir / path).resolve()
    if candidate.is_relative_to(job_dir.resolve()) and candidate.is_file():
        return candidate
    return None


def resolve_full_story_download(job_dir: Path, metadata: dict | None, output_format: str = 'mp3') -> Path | None:
    metadata = metadata if isinstance(metadata, dict) else {}
    manifest = {}
    try:
        manifest = json.loads((job_dir / 'review_manifest.json').read_text(encoding='utf-8'))
        if not isinstance(manifest, dict):
            manifest = {}
    except (OSError, ValueError):
        pass
    paths = []
    for document in (metadata, manifest):
        entry = document.get('full_story') or {}
        if isinstance(entry, str):
            paths.append(entry)
        elif isinstance(entry, dict):
            paths.extend([entry.get('relative_path'), entry.get('output_file')])
            if entry.get('output_filename'):
                paths.append(str(Path(entry.get('chapter_dir') or '.') / entry['output_filename']))
        if document is manifest:
            for entry in document.get('chapters') or []:
                if isinstance(entry, dict) and str(entry.get('title') or '').lower() == 'full story':
                    paths.append(entry.get('relative_path'))
                    if entry.get('output_filename'):
                        paths.append(str(Path(entry.get('chapter_dir') or '.') / entry['output_filename']))
    paths.extend(['full-story/Full-Story.mp3', 'full-story/Full-Story.wav'])
    extensions = list(dict.fromkeys([output_format, 'mp3', 'wav', 'ogg']))
    paths.extend(f'full_story.{ext}' for ext in extensions)
    paths.extend(f'output.{ext}' for ext in extensions)
    for relative in paths:
        resolved = safe_audio_path(job_dir, relative)
        if resolved:
            return resolved
    return None

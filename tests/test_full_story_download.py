import json

import app as app_module


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, 'OUTPUT_DIR', tmp_path)
    monkeypatch.setattr(app_module, 'load_config', lambda: {'output_format': 'mp3'})
    job = tmp_path / 'story'
    job.mkdir()
    return app_module.app.test_client(), job


def test_full_story_download_without_metadata(tmp_path, monkeypatch):
    client, job = _client(tmp_path, monkeypatch)
    (job / 'full-story').mkdir()
    (job / 'full-story/Full-Story.mp3').write_bytes(b'full story audio')
    response = client.get('/api/download/story')
    assert response.status_code == 200
    assert response.data == b'full story audio'
    response.close()


def test_metadata_precedes_layout_fallback(tmp_path, monkeypatch):
    client, job = _client(tmp_path, monkeypatch)
    (job / 'selected.wav').write_bytes(b'metadata audio')
    (job / 'output.mp3').write_bytes(b'legacy audio')
    (job / 'metadata.json').write_text(json.dumps({'full_story': {'relative_path': 'selected.wav'}}))
    response = client.get('/api/download/story')
    assert response.data == b'metadata audio'
    response.close()


def test_manifest_path_when_metadata_stale(tmp_path, monkeypatch):
    client, job = _client(tmp_path, monkeypatch)
    (job / 'merged.wav').write_bytes(b'manifest audio')
    (job / 'metadata.json').write_text(json.dumps({'full_story': {'relative_path': 'missing.mp3'}}))
    (job / 'review_manifest.json').write_text(json.dumps({'full_story': {'relative_path': 'merged.wav'}}))
    response = client.get('/api/download/story')
    assert response.status_code == 200
    assert response.data == b'manifest audio'
    response.close()


def test_unsafe_metadata_is_ignored_and_legacy_output_still_works(tmp_path, monkeypatch):
    client, job = _client(tmp_path, monkeypatch)
    (tmp_path / 'outside.mp3').write_bytes(b'outside')
    (job / 'output.mp3').write_bytes(b'legacy audio')
    (job / 'metadata.json').write_text(json.dumps({'full_story': {'relative_path': '../outside.mp3'}}))
    response = client.get('/api/download/story')
    assert response.data == b'legacy audio'
    response.close()


def test_directory_is_not_downloaded(tmp_path, monkeypatch):
    client, job = _client(tmp_path, monkeypatch)
    response = client.get('/api/download/story?file=.')
    assert response.status_code == 404

# Chinese Novel validation — 2026-10-05

Validated in a lightweight Windows Python 3.12 virtual environment and Node 24.
Only ordinary application/test dependencies were installed. No text or speech
model, model runtime or engine environment was downloaded or deployed.

## Automated regression coverage

- Mixed CJK/English units, bounded LLM/TTS chunks, single-newline paragraphs,
  Chinese punctuation, unbroken long sentences and read-only context.
- Chinese numerals, full-width digits, spaced/colon titles, prose negatives,
  CRLF offsets, shared statistics/Prep boundaries and explicit detection disable.
- Unicode parsing, validation, repair, rename, profile excerpts, citations,
  control tags and speaker blocks crossing chapter boundaries.
- Chinese presets, source rewrite/omission/overlap rejection, complete markup,
  aliases, invalid canonical IDs, first-person protagonist, project settings,
  resume fingerprint and saved provider profile. Final assembly preserves
  section gaps, mixed newlines and outer whitespace; heading-only sections
  do not call the model.
- Mandarin VoiceDesign language, CJK preview padding, representative dialogue,
  seed/candidate persistence and exact generated reference transcript.
- Real Qwen Clone adapter with a fake synthesis model: persisted Chinese sample
  transcript and reference reused across nonconsecutive chunks, original order.
- Real job queue/parser/section/checkpoint code with fake Qwen Clone and IndexTTS
  synthesis: two pauses/resumes, no replay or audio overwrite, distinct chapter
  directories, stable assignment references, correct manifest.
- Full Story download without metadata, stale metadata/manifest paths, legacy
  output, path confinement and Unicode download filenames.

Final results: 207 relevant Python tests and all 25 executable JavaScript tests
passed. The broad lightweight Python run had 559 passes and 769 passing subtests,
with three existing unrelated failures. A one-million-Han-character chunking
check produced 250 bounded 4000-unit chunks, reconstructed the source exactly,
and completed in 1.48 seconds on this machine.

The broad suite retains these baseline limitations:

- `test_config_isolation`: the fork omits the ignored personal `sync-to-git.bat`.
- Two `test_help_center` subtests: IndexTTS help title differs from the manifest,
  and the article has no screenshot.
- `test_sync_to_repo.py` cannot collect because the fork omits the ignored
  personal `sync_to_repo.py`; excluded from broad runs.
- `test_index_tts_25.py` requires PyTorch; excluded from the lightweight broad
  run. New Chinese queue tests use a stub engine and run independently of it.

The original JS suites had five fixture failures from an omitted
`localai-models.js`. The fixtures now load the same helper as the real page.
Obsolete exact asset-version assertions were changed to minimum version checks,
so valid future cache-buster increments do not report false regressions.

## Remote text-model smoke tests

Used the user's existing LAN OpenAI-compatible text model
`Qwen3.8-27B-Uncensored` through the real Flask Prep and Profile routes:

| Preset | Fixture | Checks |
| --- | --- | --- |
| Chinese Novel | supplied two-chapter 石室/山外 example | chapters retained, source accepted, 旁白/叶临渊 stable, Mandarin profiles |
| Chinese Novel Directed | same two chapters | direction separated from speech, exact source accepted, stable tags/profiles |
| Chinese Novel First Person | two-chapter 重逢/归路 fixture | protagonist narration, 林清雪 dialogue, aliases as addressees, source accepted, stable profiles |

The first-person review initially found a paragraph containing another person's
dialogue incorrectly assigned to the protagonist. The prompt now explicitly
requires in-paragraph narration/dialogue separation; rerunning the remote test
passed explicit quote-owner assertions. Source validation proves fidelity, not
semantic attribution accuracy; users should review character assignments.
All three remote suites were rerun after the assembly fix and passed an
independent assertion that removing added markup exactly reconstructs the input,
including whitespace.

The local browser displayed Chinese speaker chips and novel controls correctly,
with no captured JavaScript errors. The temporary browser/server were stopped.

## Deferred real audio validation

The user confirmed no speech model service is currently available and explicitly
deferred real audio tests. Actual Mandarin naturalness, voice distinction,
cross-chapter timbre consistency and real VoiceDesign/Clone synthesis remain
unverified. Existing persistent/model directories and engine installers remain
unchanged. Run a real novel's 2–5 chapters on an existing deployment before
expanding to a full Character Book, relationships or complete UI localization.

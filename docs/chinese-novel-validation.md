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

Final results: 213 relevant Python tests and all 25 executable JavaScript tests
passed. The broad lightweight Python run had 565 passes and 769 passing subtests,
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

## Existing Docker deployment and real audio validation

After initially deferring audio tests, the user authorized updating an existing
Docker deployment and using its cached Qwen3 speech models. Deployed application
revision `0ff1827` on its existing Python 3.10/CUDA runtime. The derived image was
built offline from a Git bundle. The original image and a private backup of
configuration, application data, references and audio were retained for rollback.
All existing bind mounts and engine/model environments were reused. Configuration
was verified byte-for-byte unchanged; an existing 234-chunk production and its
Full Story remained accessible. No model weights were downloaded for this test.

The deployed HTTP Prep/Profile routes passed all three two-chapter text suites.
Real Qwen3 VoiceDesign/Clone HTTP queue validation then passed:

- Two roles (旁白 and 叶临渊), two Chinese VoiceDesign candidates each, using
  different seeds. Actual samples lasted 17.6–22.8 seconds. Generated audio hashes,
  actual language, original sample, instruction, speaker, seed and persisted
  transcript were checked. Only the test candidate groups were approved/archived.
- Two Chinese chapters, eight ordered Voice Clone chunks. Paused at 2/8, then
  resumed to 8/8. Completed chunk IDs, ordering, paths, text and audio SHA-256 were
  unchanged across resume; references and Chinese transcripts stayed consistent.
- One real single-chunk regeneration and regeneration of all four protagonist
  chunks, followed by an explicit recompile through `/review/finish`. The existing
  workflow auto-completes jobs first and supports review from the Library.
- Actual downloads of all eight WAV chunks, two chapter MP3s and Full Story MP3.
  Full Story was 52.802 seconds; chapter durations totalled 52.800 seconds.
- Actual M4B export returned AAC audio, 52.844 seconds, and chapter markers
  `第一章 石室` / `第二章 山外`, verified with FFprobe.
- Restarted the updated container after tests. Both the original 234-chunk job
  and the new eight-chunk job reloaded as completed, all ten voice entries
  remained available, and Full Story download still returned HTTP 200.

The reproducible `scripts/chinese_audio_smoke.py` uses only HTTP/standard-library
clients, checkpoints server IDs and audio evidence, and can resume individual
validation phases without resubmitting successful operations. Its six offline
contract tests include auto-completed Library review, pause/resume audio identity
and protection against duplicate POSTs after unknown transport outcomes.

IndexTTS has an installed environment on that server, but its checkpoints contain
only `pinyin.vocab`, without model weights. Its real synthesis remains untested;
the automated mocked queue coverage still applies. No additional engine/model
installation was started.

Audio files are valid and available for listening. Mandarin naturalness, perceived
voice distinction and cross-chapter timbre quality still require human listening;
reference reuse and non-silent audio do not establish those subjective properties.
Use a real novel's 2–5 chapters for editorial/voice approval before expanding to
a full Character Book, relationships or complete UI localization.

## Long Prep failure and recovery — 2026-10-06

Inspected the existing remote Prep checkpoint with 49 sections and two accepted
outputs. The next section had 2,173 characters. With the configured LAN model,
its response ended normally (`finish_reason=stop`) but inserted a repeated
dialogue sentence. The strict source guard rejected it. The browser hid the
actual error behind the generic `2 of 49 sections completed` resume notice.

Bounded correction and exact-source splitting recovered the next sections, but
the real section 15 still produced changed text at a roughly 200-character
size. Source-locked role annotation was therefore added: the model returns only
ordered span IDs, speakers and optional Directed delivery metadata; Python
assembles the original text and validates every result. Successful use is saved
and reused for subsequent sections. Auto language is frozen for the whole novel.

The separate private validation copy completed all **49/49 sections**, covering
**100,967 source characters** and 21 detected speaker IDs. Original accepted
output hashes were unchanged. All 49 outputs were independently rechecked for
source text, punctuation, whitespace and valid markup. The final 35-section
inference phase took 307.9 seconds. Original inter-section gaps are retained by
the UI assembly from its original full input; this checkpoint validation tests
the individual sections rather than recreating those unavailable input gaps.
The user's original two-section checkpoint file was not overwritten.

Application revision **f6b1e45** is deployed through the existing Docker mounts
and cached runtime. Config and the original Prep checkpoint have identical
before/after SHA-256 hashes. The original 234-chunk job and eight-chunk validation
job still load as completed. Real deployed HTTP tests also passed source-locked
Directed and First Person Prep/Profile fixtures, including other-character
dialogue ownership. Use `scripts/chinese_novel_smoke.py --source-locked` to repeat
these route checks.

The final targeted regression has **270 Python tests passing** and all nine
JavaScript test files passing. It covers invalid/truncated model output,
bounded recovery, complete/unique ordered annotation IDs, metadata injection,
nested and continued quotes, first-person voices, custom role preferences,
mixed-language source protection and saved strategy/error/prompt restoration.
Repository safety and whitespace checks passed. Speaker attribution across an
arbitrary novel still requires editorial review; exact source retention does
not establish semantic attribution or speech quality.

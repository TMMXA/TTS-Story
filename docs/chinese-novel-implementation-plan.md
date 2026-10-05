# Chinese Novel implementation plan

Target: first-stage Chinese Novel pipeline in the existing fork, starting at
`17242fc9620dff33c2a3af8072748bbb6e7d1bef`. Keep the queue, library, engines,
audio merger and persistent paths intact.

## Audit and baseline

- Shared section construction in `app.py` already serves statistics, preview,
  Prep, chapter generation and exports. Add an independent Chinese detector there.
- Tag handling includes validators, repair tools, chapter boundary balancing,
  profile excerpts and frontend rename/matching. Use one Unicode contract.
- LLM Prep has provider-independent section/prompt endpoints and sequential
  speaker memory. Add CJK bounded chunks and read-only preceding context.
- Existing VoiceDesign candidates, reference samples and transcript cache can
  persist Chinese metadata without changing Qwen Clone or model storage.
- Python baseline initially cannot collect three modules: missing scipy/Pillow,
  and `sync_to_repo.py` (ignored personal script absent from the fork). Install
  only ordinary test/runtime dependencies and exclude the absent script test.
- JS baseline has five failures in three suites because the fixtures omit
  `window.localAIEngineChoice`; record these separately from new regressions.

## Implementation tasks

1. Add regression fixtures/tests before implementation in each task.
2. Core: add `src/chinese_novel/text_units.py`, counting CJK characters plus
   non-CJK words. Preserve source separators while splitting on paragraphs,
   sentences and hard limits. Hook LLM and TTS word chunks; bounded Chinese
   defaults are 4000 units and 300 characters of read-only context.
3. Sections/tags: add Chinese chapter detection and shared Unicode speaker
   grammar, hook all production and repair paths, mirror grammar in JS.
4. Prep: add Chinese Novel, Directed and First Person presets, persist project
   novel settings, carry context and known characters, guard source preservation
   and reattach headings deterministically. Lightweight alias memory may reuse
   existing project JSON; full Character Book UI remains outside this stage.
5. Profiles/voices: supply Chinese profile defaults, stable Mandarin voice
   descriptions, Chinese sample and language resolution, CJK padding, optional
   representative dialogue, and exact generated transcript persistence.
6. Download: resolve metadata and manifest paths safely, then full-story and
   legacy layouts, with route tests for missing metadata and stale paths.
7. Integration: run core Python/JS regressions, test remote LLM on supplied
   Chinese fixture and multiple chapters, document workflow and limitations.

## Shared settings contract

Project/API `novel_settings`: `language` (auto/English/Chinese/Japanese/Korean),
`chunk_size` (4000 Chinese default), `context_overlap` (300 Chinese default),
`narrative_mode` (auto/third_person/first_person), `first_person_protagonist`.
Defaults live in the novel helper; old projects remain valid without the object.
Section `context` is input-only; accepted Prep output cannot repeat it.
Voice language resolves from explicit payload/project settings or CJK input.

## Verification boundary

No local text/speech models will be downloaded or deployed. Worker/engine tests
use mocks; real text inference can use the provided LAN OpenAI-compatible API.
Real VoiceDesign/Clone quality and live pause/resume audio tests require an
already running TTS service and cannot be claimed from mocked tests.

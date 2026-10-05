const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const main = fs.readFileSync(require('node:path').join(__dirname, '../static/js/main.js'), 'utf8');

for (const language of ['Chinese', 'auto']) test(`Prep ${language} keeps accepted output and guards Latin sections with saved settings`, async () => {
    const saved = {sections: [{content: '甲。'}, {content: 'Original English passage.'}], outputs: ['[旁白]甲。[/旁白]'],
        known_speakers: ['旁白'], active_profile: 'primary', prompt_override: '原预设',
        source_locked_prep: true,
        novel_settings: {language}, character_registry: []};
    const input = {value: '甲。Original English passage.'};
    let persisted, panel, request;
    const ctx = vm.createContext({console: {error() {}}, document: {getElementById: id => id === 'input-text' ? input : null},
        getEnabledSectionHeadings: () => [], getSelectedGeminiPromptOverride: () => '已改预设',
        isChineseNovelSettings: (settings, text) => settings.language === 'Chinese' || text.includes('甲'),
        getChineseNovelSettings: () => ({language: 'English'}), getChineseNovelRegistry: () => [],
        updateGeminiProgress() {}, _hidePrepResumePanel() {}, showNotification() {},
        resolveBookTitleFromSections: () => '', latestGeminiBookTitle: '',
        _showPrepResumePanel(...args) {panel = args;},
        async fetch(url, options) {
            const body = JSON.parse(options.body);
            if (url.endsWith('/save')) {persisted = body; return {ok: true, async json() {return {success: true};}};}
            request = body;
            return {status: 400, async json() {return {success: false, retryable: false, error: 'source mismatch at offset 18'};}};
        },
    });
    vm.runInContext(main.slice(main.indexOf('async function _savePrepProgress('), main.indexOf('async function _loadPrepProgress(')), ctx);
    vm.runInContext(main.slice(main.indexOf('async function _runGeminiPrep('), main.indexOf('function updateGeminiProgress(')), ctx);
    await ctx._runGeminiPrep(null, input.value, 'hash', saved);
    assert.equal(request.prompt_override, '原预设');
    assert.equal(request.novel_settings.language, 'Chinese');
    assert.equal(request.source_locked_prep, true);
    assert.equal(persisted.novel_settings.language, 'Chinese');
    assert.equal(persisted.prompt_override, '原预设');
    assert.equal(persisted.source_locked_prep, true);
    assert.match(persisted.last_failure, /offset 18/);
    assert.deepEqual(persisted.outputs, saved.outputs);
    assert.equal(panel[0], 1);
    assert.equal(panel[1], 2);
    assert.match(panel[5], /offset 18/);
    assert.equal(input.value, '甲。Original English passage.');
    assert.equal(saved.novel_settings.language, language);
});

test('successful source locking is checkpointed and reused for later sections', async () => {
    const input = {value: '甲。乙。'}, processRequests = [], saves = [];
    const ctx = vm.createContext({console, document: {getElementById: id => id === 'input-text' ? input : null},
        getEnabledSectionHeadings: () => [], getSelectedGeminiPromptOverride: () => '',
        getChineseNovelSettings: () => ({language: 'Chinese'}), getChineseNovelRegistry: () => [],
        isChineseNovelSettings: () => true,
        joinChineseNovelSections: (source, sections, outputs) => outputs.join(''),
        updateGeminiProgress() {}, _hidePrepResumePanel() {}, showNotification() {},
        resolveBookTitleFromSections: () => '', latestGeminiBookTitle: '',
        async _clearPrepProgress() {}, async analyzeText() {return false;},
        async fetch(url, options) {
            const body = JSON.parse(options.body);
            if (url.endsWith('/save')) {saves.push(body); return {ok: true, async json() {return {success: true};}};}
            processRequests.push(body);
            return {status: 200, async json() {return {success: true, result_text: `[旁白]${body.content}[/旁白]`,
                speakers: ['旁白'], llm_profile_used: {id: 'primary'}, preparation_diagnostics: {source_locked_parts: 1}};}};
        },
    });
    vm.runInContext(main.slice(main.indexOf('async function _savePrepProgress('), main.indexOf('async function _loadPrepProgress(')), ctx);
    vm.runInContext(main.slice(main.indexOf('async function _runGeminiPrep('), main.indexOf('function updateGeminiProgress(')), ctx);
    await ctx._runGeminiPrep(null, input.value, 'hash', {
        sections: [{content: '甲。'}, {content: '乙。'}], outputs: [], novel_settings: {language: 'Chinese'}, character_registry: []});
    assert.deepEqual(processRequests.map(p => p.source_locked_prep), [false, true]);
    assert.deepEqual(saves.map(p => p.outputs.length), [0, 1, 2]);
    assert.equal(saves[1].source_locked_prep, true);
    assert.equal(saves[2].outputs[0], saves[1].outputs[0]);
    assert.equal(input.value, '[旁白]甲。[/旁白][旁白]乙。[/旁白]');
});

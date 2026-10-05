const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const main = fs.readFileSync(require('node:path').join(__dirname, '../static/js/main.js'), 'utf8');

for (const language of ['Chinese', 'auto']) test(`Prep ${language} keeps accepted output and guards Latin sections with saved settings`, async () => {
    const saved = {sections: [{content: '甲。'}, {content: 'Original English passage.'}], outputs: ['[旁白]甲。[/旁白]'],
        known_speakers: ['旁白'], active_profile: 'primary', prompt_override: '原预设',
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
    assert.equal(persisted.novel_settings.language, 'Chinese');
    assert.equal(persisted.prompt_override, '原预设');
    assert.match(persisted.last_failure, /offset 18/);
    assert.deepEqual(persisted.outputs, saved.outputs);
    assert.equal(panel[0], 1);
    assert.equal(panel[1], 2);
    assert.match(panel[5], /offset 18/);
    assert.equal(input.value, '甲。Original English passage.');
    assert.equal(saved.novel_settings.language, language);
});

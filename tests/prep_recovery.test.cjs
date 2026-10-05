const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const main = fs.readFileSync(require('node:path').join(__dirname, '../static/js/main.js'), 'utf8');

test('Prep persists the real failure and resumes with the saved prompt, settings and accepted output', async () => {
    const saved = {sections: [{content: '甲。'}, {content: '乙。'}], outputs: ['[旁白]甲。[/旁白]'],
        known_speakers: ['旁白'], active_profile: 'primary', prompt_override: '原预设',
        novel_settings: {language: 'Chinese'}, character_registry: []};
    const input = {value: '甲。乙。'};
    let persisted, panel, request;
    const ctx = vm.createContext({console: {error() {}}, document: {getElementById: id => id === 'input-text' ? input : null},
        getEnabledSectionHeadings: () => [], getSelectedGeminiPromptOverride: () => '已改预设',
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
    assert.equal(persisted.novel_settings.language, 'Chinese');
    assert.equal(persisted.prompt_override, '原预设');
    assert.match(persisted.last_failure, /offset 18/);
    assert.deepEqual(persisted.outputs, saved.outputs);
    assert.equal(panel[0], 1);
    assert.equal(panel[1], 2);
    assert.match(panel[5], /offset 18/);
    assert.equal(input.value, '甲。乙。');
});

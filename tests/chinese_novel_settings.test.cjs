const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const fields = Object.fromEntries(['novel-language', 'novel-chunk-size', 'novel-context-overlap',
    'novel-narrative-mode', 'novel-first-person-protagonist', 'novel-character-registry', 'gemini-preset-select']
    .map(id => [id, {value: '', addEventListener(type, fn) { this.listener = fn; }}]));
const ctx = vm.createContext({window: {}, document: {getElementById: id => fields[id] || null,
    addEventListener(type, fn) {fn();}}, console, getSelectedGeminiPromptOverride: () => 'preset',
    enabledSectionHeadings: [], customSectionHeadings: [], latestGeminiBookTitle: '', voiceFxState: {},
    azureVoiceOptionState: {}, speakerReadyState: {}, speakerProfiles: {}, bulkVoiceGenerationState: null,
    normalizeVoiceDesignEngine: () => 'qwen', getVoiceAssignments: () => ({}), buildTurboSelectionMap: () => ({}),
    collectPerSpeakerControlValues: () => ({}), getAltWordRegistry: () => [], serializeVoiceDesignCandidateGroups: () => []});
vm.runInContext(fs.readFileSync(path.join(root, 'static/js/novel-settings.js'), 'utf8'), ctx);
const settings = {language: 'Chinese', chunk_size: 4000, context_overlap: 0,
    narrative_mode: 'first_person', first_person_protagonist: '叶临渊'};
ctx.applyChineseNovelSettings(settings);
const registry = [{display_name: '叶临渊', aliases: ['叶兄']}];
ctx.applyChineseNovelRegistry(registry);
assert.deepEqual(JSON.parse(JSON.stringify(ctx.getChineseNovelSettings())), settings);
assert.deepEqual(JSON.parse(JSON.stringify(ctx.getChineseNovelRegistry())), registry);
fields['gemini-preset-select'].value = 'chinese-novel-first-person';
fields['novel-language'].value = 'English';
fields['gemini-preset-select'].listener({target: fields['gemini-preset-select']});
assert.equal(ctx.getChineseNovelSettings().language, 'Chinese');
const main = fs.readFileSync(path.join(root, 'static/js/main.js'), 'utf8');
vm.runInContext(main.slice(main.indexOf('function resolveBookTitleFromSections('), main.indexOf('async function fetchSpeakerProfiles(')), ctx);
assert.equal(ctx.resolveBookTitleFromSections([{title: '第一章 石室'}, {title: '第１２章：故人'}]), '');
assert.equal(ctx.resolveBookTitleFromSections([{title: '山雨欲来'}, {title: '第一章 石室'}]), '山雨欲来');
vm.runInContext(main.slice(main.indexOf('function _geminiPrepHash('), main.indexOf('async function _savePrepProgress(')), ctx);
const original = ctx._geminiPrepHash('甲'.repeat(2500) + '一');
assert.notEqual(original, ctx._geminiPrepHash('甲'.repeat(2500) + '二'));
fields['novel-context-overlap'].value = '500';
assert.notEqual(original, ctx._geminiPrepHash('甲'.repeat(2500) + '一'));
vm.runInContext(main.slice(main.indexOf('function getProjectState('), main.indexOf('function renderProjectList(')), ctx);
const project = ctx.getProjectState();
ctx.applyChineseNovelSettings({language: 'English'});
ctx.applyChineseNovelRegistry([]);
ctx.applyChineseNovelSettings(project.novel_settings);
ctx.applyChineseNovelRegistry(project.character_registry);
assert.equal(ctx.getChineseNovelSettings().first_person_protagonist, '叶临渊');
assert.equal(ctx.getChineseNovelRegistry()[0].aliases[0], '叶兄');
for (const [source, contents] of [
    [' \r\n第一段。\n\n\n第二段。 \n', ['第一段。', '第二段。']],
    ['甲乙丙丁戊己。', ['甲乙丙', '丁戊己。']],
]) {
    const joined = ctx.joinChineseNovelSections(source, contents.map(content => ({content})),
        contents.map(content => `[旁白]${content}[/旁白]`));
    assert.equal(joined.replace(/\[\/?旁白\]/g, ''), source);
}
assert.throws(() => ctx.joinChineseNovelSections('原文', [{content: 'missing'}], ['output']));
const requests = [];
fields['input-text'] = {value: '我推开门。'};
Object.assign(ctx, {
    getEnabledSectionHeadings: () => [], updateGeminiProgress() {}, _hidePrepResumePanel() {},
    showNotification() {}, resolveBookTitleFromSections: () => '', currentStats: null,
    async _savePrepProgress() {}, async _clearPrepProgress() {}, async analyzeText() {return false;},
    async fetch(url, options) {
        requests.push({url, payload: JSON.parse(options.body)});
        return {async json() {
            return url.endsWith('/sections')
                ? {success: true, sections: [{content: '我推开门。', context: '前文。'}]}
                : {success: true, result_text: '[叶临渊]我推开门。[/叶临渊]', speakers: ['叶临渊']};
        }};
    },
});
vm.runInContext(main.slice(main.indexOf('async function _runGeminiPrep('), main.indexOf('function updateGeminiProgress(')), ctx);
ctx._runGeminiPrep(null, fields['input-text'].value, 'test_hash', null).then(() => {
    const payload = requests.find(request => request.url.endsWith('/process-section')).payload;
    assert.equal(payload.novel_settings.narrative_mode, 'first_person');
    assert.equal(payload.novel_settings.first_person_protagonist, '叶临渊');
    assert.equal(payload.character_registry[0].aliases[0], '叶兄');
    assert.equal(payload.context, '前文。');
    console.log('Chinese novel settings, presets, project state, payload and resume fingerprint passed');
}).catch(error => {console.error(error); process.exitCode = 1;});

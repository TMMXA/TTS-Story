const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const mainSource = fs.readFileSync(path.join(__dirname, '../static/js/main.js'), 'utf8');
const managerSource = fs.readFileSync(path.join(__dirname, '../static/js/voice-manager.js'), 'utf8');
function helpers({ language = 'Chinese', text = '', profile = {} } = {}) {
    const ctx = vm.createContext({ console, window: { getChineseNovelSettings: () => ({ language }) },
        document: { getElementById: id => id === 'input-text' ? { value: text } : null },
        findSpeakerProfile: () => ({ profile }), parseGenderFromSpeakerName: () => null,
    });
    vm.runInContext(mainSource.slice(mainSource.indexOf('const VOICE_DESIGN_STANDARD_PREVIEW_TEXT'),
        mainSource.indexOf('function createVoiceDesignCandidateSeed')), ctx);
    return ctx;
}

test('Chinese candidates use Mandarin profile, Chinese sample and explicit language', () => {
    const ctx = helpers({ profile: { voice: '低沉清晰的青年男声',
        voice_design_prompt: 'YOUNG ADULT MALE VOICE. Dry tenor, measured pace, Standard Mandarin.' } });
    const payload = ctx.buildSpeakerVoiceDesignPayload('叶临渊', '叶临渊');
    assert.equal(payload.language, 'Chinese');
    assert.equal(payload.gender, 'Male');
    assert.match(payload.text, /当你听到/);
    assert.doesNotMatch(payload.text, /With this line/);
});

test('explicit profile language overrides project and English workflow keeps its sample', () => {
    const profile = { voice: 'Warm alto', voice_design_language: 'English',
        voice_design_prompt: 'ADULT FEMALE VOICE. Warm alto, neutral English accent.' };
    const ctx = helpers({ profile });
    assert.equal(ctx.buildSpeakerVoiceDesignPayload('alice-female').language, 'English');
    assert.match(ctx.buildCharacterPreviewText('alice-female', profile), /With this line/);
});

test('auto mode detects Chinese source without requiring renamed speaker IDs', () => {
    const profile = { voice: 'Warm tenor', voice_design_prompt: 'ADULT MALE VOICE. Warm tenor.' };
    const ctx = helpers({ language: 'auto', text: '[叶临渊]这是中文小说。[/叶临渊]', profile });
    assert.equal(ctx.buildSpeakerVoiceDesignPayload('叶临渊').language, 'Chinese');
});

test('Chinese casting prefers a sufficient calm passage from the exact character', () => {
    const dialogue = '我们沿着石阶慢慢向前，穿过山谷的时候，天色已经渐渐亮了。前方还有很长的路，我想先找到一个可以落脚的地方，再仔细考虑接下来应该怎么做。只要大家平安无事，这些困难总能一步一步解决。';
    const ctx = helpers({ text: `[叶临渊]终于出来了！[/叶临渊]\n[林清雪]${'别人的声音。'.repeat(20)}[/林清雪]\n[叶临渊]${dialogue}[/叶临渊]` });
    assert.equal(ctx.buildCharacterPreviewText('叶临渊'), dialogue);
    assert.match(ctx.buildCharacterPreviewText('不存在的人'), /当你听到/);
});

test('Chinese casting skips brief interjections and highly excited lines', () => {
    const ctx = helpers({ text: `[叶临渊]${'救命！'.repeat(30)}[/叶临渊]` });
    assert.match(ctx.buildCharacterPreviewText('叶临渊'), /当你听到/);
});

test('profile restoration retains language and selected reference', () => {
    const ctx = helpers();
    Object.assign(ctx, { speakerProfiles: {}, normalizeSpeakerKey: value => value,
        normalizeVoiceDesignEngine: value => value || 'qwen3', buildLocalVoiceDesignPrompt: (_name, voice, prompt) => prompt || voice });
    vm.runInContext(mainSource.slice(mainSource.indexOf('function setSpeakerProfiles('),
        mainSource.indexOf('function findSpeakerProfile(')), ctx);
    ctx.setSpeakerProfiles({ '叶临渊': { name: '叶临渊', voice: '青年男声',
        voice_design_language: 'Chinese', selected_voice_id: 'voice-37', selected_voice_path: 'reference.wav' } });
    assert.equal(ctx.speakerProfiles['叶临渊'].voice_design_language, 'Chinese');
    assert.equal(ctx.speakerProfiles['叶临渊'].selected_voice_path, 'reference.wav');
});

test('manual save uses actual generated text and language even after controls change', async () => {
    let captured;
    const generatedText = '这是生成时实际朗读的中文文本。';
    const fields = { 'qwen-voice-name': { value: '叶临渊' }, 'qwen-voice-language': { value: 'English' },
        'qwen-voice-text': { value: 'Edited after generating.' }, 'qwen-voice-instruct': { value: 'Changed instruction' } };
    const ctx = vm.createContext({ console, document: { getElementById: id => fields[id] },
        qwenVoicePreview: { engine: 'qwen3', audio_base64: 'wav', result: {
            preview_text: generatedText, language: 'Chinese', instruction: 'Standard Mandarin.', cleanup_applied: true, seed: 37 } },
        getActiveVoiceCreationDesignEngine: () => 'qwen3',
        window: { getVoiceDesignEngineConfig: () => ({ saveUrl: '/save', taskUrl: () => '/task' }) },
        showToast() {}, pollQwenVoiceTask: async () => ({}), loadChatterboxVoices: async () => {},
        fetch: async (_url, options) => { captured = JSON.parse(options.body); return { json: async () => ({ success: true, job_id: 'task' }) }; },
    });
    vm.runInContext(managerSource.slice(managerSource.indexOf('async function saveQwenVoicePrompt('),
        managerSource.indexOf('async function pollQwenVoiceTask(')), ctx);
    await ctx.saveQwenVoicePrompt();
    assert.equal(captured.text, generatedText);
    assert.equal(captured.language, 'Chinese');
    assert.equal(captured.instruction, 'Standard Mandarin.');
    assert.equal(captured.cleanup_applied, true);
    assert.equal(captured.seed, 37);
});

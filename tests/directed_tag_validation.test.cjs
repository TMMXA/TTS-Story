const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

function context() {
    const textarea = { value: '', dispatchEvent() {} };
    const ctx = vm.createContext({
        console, setInterval: () => 0, Event: class {},
        fetch: async () => ({ json: async () => ({ success: false }) }),
        document: { addEventListener() {}, querySelectorAll: () => [],
            getElementById: id => id === 'input-text' ? textarea : null },
    });
    ctx.window = ctx;
    ctx.addEventListener = () => {};
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/js/main.js'), 'utf8'), ctx);
    return { ctx, textarea };
}

test('all wrong direction closers are visible and explicitly repairable', () => {
    const { ctx, textarea } = context();
    const speakers = ['narrator', 'lyra-female', 'kael-male'];
    const prefix = '[direction]Speak quietly.[/direction]\n';
    textarea.value = speakers.map(s => `${prefix}[${s}]Exact source words.[/direction]`).join('\n');
    assert.equal(ctx.getSpeakerTagIssues(textarea.value).length, 3);
    ctx._autoFixTagBalance();
    assert.equal(textarea.value, speakers.map(s => `${prefix}[${s}]Exact source words.[/${s}]`).join('\n'));
    assert.equal(ctx.getSpeakerTagIssues(textarea.value).length, 0);
});

test('warnings do not depend on a valid pair or include standalone expression cues', () => {
    const { ctx } = context();
    for (const text of ['[alice]Hello', '[/alice]', '[direction]Quiet.[/emotion]',
        '[narrator][direction]Quiet.[/direction]Hello.[/narrator]']) {
        assert.ok(ctx.getSpeakerTagIssues(text).length, text);
    }
    assert.equal(ctx.getSpeakerTagIssues('[direction]Warmly.[/direction][narrator]Hello [laugh] [question-en] [1].[/narrator]').length, 0);
});

test('Chinese IDs survive rename, matching, warnings and multiple repairs', () => {
    const { ctx, textarea } = context();
    assert.equal(ctx.formatSpeakerTagName(' 叶临渊 '), '叶临渊');
    assert.equal(ctx.formatSpeakerTagName('Élise Female'), 'élise-female');
    assert.equal(ctx.normalizeSpeakerLabel('林清雪'), '林清雪');
    assert.notEqual(ctx.normalizeSpeakerLabel('林清雪'), ctx.normalizeSpeakerLabel('叶临渊'));
    const speakers = ['旁白', '叶临渊', '林清雪'];
    textarea.value = speakers.map(s => `[${s}]原文。[1][laugh][/direction]`).join('\n');
    assert.equal(ctx.getSpeakerTagIssues(textarea.value).length, 3);
    ctx._autoFixTagBalance();
    assert.equal(textarea.value, speakers.map(s => `[${s}]原文。[1][laugh][/${s}]`).join('\n'));
    assert.equal(ctx.getSpeakerTagIssues(textarea.value).length, 0);
    assert.equal(ctx.getSpeakerTagIssues('[叶临渊]没有闭合。').length, 1);
    for (const name of ['Ⅷ', '³号', '角色_2', 'Élise']) {
        assert.equal(ctx.getSpeakerTagIssues(`[${name}]原文。[/${name}]`).length, 0);
        assert.equal(ctx.getSpeakerTagIssues(`[${name}]原文。`).length, 1);
    }
});

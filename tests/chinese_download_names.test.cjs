const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

test('chapter downloads preserve complete Chinese titles and remove invalid filename characters', () => {
    const context = vm.createContext({window: {}, document: {addEventListener() {}}});
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/js/library.js'), 'utf8'), context);
    assert.equal(context.buildChapterDownloadName({title: '第一百二十八章 山雨欲来', relative_path: 'chapter_128.mp3', chapter_number: 128}),
        'Chapter-128_第一百二十八章-山雨欲来.mp3');
    assert.equal(context.buildChapterDownloadName({title: 'Chapter 1: A/B?', relative_path: 'chapter_01.mp3', chapter_number: 1}),
        'Chapter-01_Chapter-1-AB.mp3');
});

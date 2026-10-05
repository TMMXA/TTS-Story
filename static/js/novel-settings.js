/* Project-level preparation controls; ordinary English workflows keep their settings. */
function getChineseNovelSettings() {
    const read = (id, fallback) => document.getElementById(id)?.value ?? fallback;
    const clamp = (value, fallback, low, high) => Math.max(low, Math.min(high, Number.parseInt(value, 10) || fallback));
    return {
        language: read('novel-language', 'auto'),
        chunk_size: clamp(read('novel-chunk-size', 4000), 4000, 1000, 12000),
        context_overlap: Math.max(0, Math.min(2000, Number.parseInt(read('novel-context-overlap', 300), 10) || 0)),
        narrative_mode: read('novel-narrative-mode', 'auto'),
        first_person_protagonist: read('novel-first-person-protagonist', '').trim(),
    };
}

function applyChineseNovelSettings(settings = {}) {
    const fields = {
        'novel-language': settings.language || 'auto',
        'novel-chunk-size': settings.chunk_size ?? 4000,
        'novel-context-overlap': settings.context_overlap ?? 300,
        'novel-narrative-mode': settings.narrative_mode || 'auto',
        'novel-first-person-protagonist': settings.first_person_protagonist || '',
    };
    Object.entries(fields).forEach(([id, value]) => {
        const element = document.getElementById(id);
        if (element) element.value = value;
    });
}

function getChineseNovelRegistry() {
    const text = document.getElementById('novel-character-registry')?.value?.trim() || '';
    if (!text) return [];
    const value = JSON.parse(text);
    if (!Array.isArray(value) || value.some(entry => !entry || typeof entry !== 'object' || !entry.display_name
        || (entry.aliases != null && (!Array.isArray(entry.aliases) || entry.aliases.some(alias => typeof alias !== 'string'))))) {
        throw new Error('Character aliases must be a JSON array of display_name and aliases.');
    }
    return value;
}

function applyChineseNovelRegistry(registry = []) {
    const element = document.getElementById('novel-character-registry');
    if (element) element.value = registry.length ? JSON.stringify(registry, null, 2) : '';
}

window.getChineseNovelSettings = getChineseNovelSettings;
function isChineseNovelSettings(settings, source = '') {
    const language = settings?.language || 'auto';
    return language === 'Chinese' || (language === 'auto' && /[\u3400-\u9fff]/.test(source));
}

function joinChineseNovelSections(source, sections, outputs) {
    if (sections.length !== outputs.length) throw new Error('Chinese Novel assembly failed: incomplete section outputs.');
    const parts = [];
    let cursor = 0;
    sections.forEach((section, index) => {
        const rawContent = section.content || '';
        const content = rawContent.trim();
        const output = outputs[index];
        if (!content || typeof output !== 'string' || !output) throw new Error('Chinese Novel assembly failed: empty section or output.');
        let start = source.indexOf(content, cursor);
        if (start < 0) throw new Error('Chinese Novel assembly failed: section cannot be located in original source.');
        let end = start + content.length;
        if (rawContent !== content) {
            const fullStart = start - (rawContent.length - rawContent.trimStart().length);
            const fullEnd = end + (rawContent.length - rawContent.trimEnd().length);
            if (fullStart < cursor || source.slice(fullStart, fullEnd) !== rawContent) {
                throw new Error('Chinese Novel assembly failed: section whitespace differs from original source.');
            }
            start = fullStart;
            end = fullEnd;
        }
        parts.push(source.slice(cursor, start), output);
        cursor = end;
    });
    parts.push(source.slice(cursor));
    return parts.join('');
}

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('gemini-preset-select')?.addEventListener('change', event => {
        if (event.target.value.startsWith('chinese-novel')) {
            document.getElementById('novel-language').value = 'Chinese';
            if (event.target.value === 'chinese-novel-first-person') {
                document.getElementById('novel-narrative-mode').value = 'first_person';
            }
        }
    });
});

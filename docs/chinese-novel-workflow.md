# Chinese Novel workflow / 中文小说工作流

本 fork 为现有 TTS-Story 增加中文小说处理入口，继续使用原来的 Project、
Job Queue、Audio Library、Review Chunks、重生成与音频导出。

## 开始制作

1. 导入 TXT / EPUB，选择 `Chinese Novel` 或 `Chinese Novel Directed`。
   `Auto` 会识别汉字内容；也可以展开「中文小说设置」明确选择 Chinese。
2. 检查自动章节识别。默认 `Chapter` 与 `第*章` 支持中文数字、半角/全角
   数字、空格及标题，例如 `第一百零二章 山雨`、`第 12 章：风雪`。
   「Review detected sections」、Prep 和音频输出使用相同章节边界。
3. 中文 Prep 默认 4000 text units，允许 1000–12000；一个 CJK 字符算一个
   unit，其他文本按词计数。长段落在句界或必要的硬边界切开。中文单换行
   也是段落边界；默认带上前文 300 字，仅帮助理解，不重复输出。
4. 有已知别名时，在可选人物表填入下面的 JSON。后续章节复用全名标签。
   小说设置、人物表和画像会随项目保存，旧项目无需迁移。

```json
[
  {"display_name": "叶临渊", "aliases": ["临渊", "叶兄", "叶公子"]},
  {"display_name": "林清雪", "aliases": ["清雪", "林姑娘"]}
]
```

人物全名和指定主角须能用作标签：Unicode 字母/非十进制字母数字开头，
后续为字母数字、`_` 或 `-`；不包含空格、方括号或保留控制名 `direction`、
`emotion`。当前仍以角色标签作 assignment key；完整内部 ID/Character Book
属于后续阶段。

5. 点击 Prep Text，然后检查角色归属。程序拒绝改写、漏字、重复前文、
   不匹配标签及未加角色标签的正文，并恢复原文空白。章节标题在模型请求
   外保留。语义上的说话者识别仍需人工复核，尤其是身份不明的对白。
6. 点击 Build Profiles。中文模式内置画像提示词：中文人物描述和稳定 Voice
   Type，普通话 Voice Design Prompt；当前情绪仅写在 passage direction。
7. 使用已有 Qwen3-TTS 运行环境生成候选，选择角色级 Voice Design Language
   为 Chinese 或 Auto。候选使用同一提示词、同一中文试听原文、不同 seed。
   优先选择足够长且平稳的真实台词，否则使用中文标准试听；短试听按 CJK
   字符补足，不追加英文。保存的是实际生成音频的原文、语言和 seed。
8. 审听并批准 reference voice，继续选择 Qwen3 Voice Clone / IndexTTS，
   通过原有队列逐章生成、暂停恢复、Review Chunks、重生成及 Full Story。

## 第一人称

选择 `Chinese Novel First Person`，设置 `First person`，填入主角全名。
主角叙述、内心独白与主角对白使用同一标签/声线；其他人的直接对白使用其
自己的标签。段内「她说」「她指着」等叙述动作与对白分开归属。方向提示
仍可在同一角色的不同 passage 之间改变。

## 存储与兼容

没有修改 `data/`、`audio/`、`static/samples/`、`models/`、`engines/`、
`hf_cache/`、`config.json` 的位置，也没有改变引擎安装或模型缓存机制。
新增设置是可选 JSON 字段，已有项目、voice prompts 和英文预设继续读取。
中文章节用不同的 `chapter_01`、`chapter_02` 目录，防止章节文件互相覆盖。
Full Story 下载优先使用 metadata / review manifest 的合法路径，再查找
`full-story/Full-Story.mp3` / WAV 和旧 `full_story.*` / `output.*` 布局。
中文章节和 M4B 的下载文件名保留中文标题。

## 验证记录

详见 [validation report](chinese-novel-validation.md)。可通过现有远程文本模型
重跑真实 Prep/Profile 路由（参数不会修改保存的 config）：

```powershell
python scripts/chinese_novel_smoke.py --base-url http://YOUR-SERVER/v1 --model YOUR-MODEL --output smoke-output
python scripts/chinese_novel_smoke.py --base-url http://YOUR-SERVER/v1 --model YOUR-MODEL --input tests/fixtures/chinese_first_person_smoke.txt --preset chinese-novel-first-person --output smoke-first-person
python scripts/chinese_novel_smoke.py --server-url http://YOUR-TTS-STORY:5000 --output deployed-text-smoke
python scripts/chinese_audio_smoke.py --base-url http://YOUR-TTS-STORY:5000 --output live-audio-smoke --phase all
```

已复用用户现有 Docker/Qwen3 模型完成真实 VoiceDesign、双章 Clone、暂停
恢复、单块/角色重生成、重新合并、MP3 下载与 M4B 中文章节导出。语音测试
脚本会创建专用候选组和测试任务、保留试听音频，不删除现有声音或任务。
它自动选择测试候选以验证流程；正式制作仍需人工试听、选声线与确认角色归属。
同一输出目录可用 `--phase voices` / `pause` / `resume` / `review` 等阶段恢复
验收，发生未知 POST 结果时须先核实服务端，避免重复提交 GPU 任务。
测试没有在本机下载或部署文本/语音模型。音色自然度和听感仍需人工评估。
完整中文 UI、人物关系、自动选角和完整 Character Book 不在此阶段。

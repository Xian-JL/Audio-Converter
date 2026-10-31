# Audio Converter · v0.7.2

[English](README.md) · [规格](SPEC.md) · [第三方来源](THIRD_PARTY.md)

本地音频转谱与钢琴伴奏工作台。支持 MP3/FLAC、原曲播放与下载、GF 演唱旋律转谱、人工定位第一拍、可变柱式和弦、情感器乐段、双谱表试听和导出。默认英文，可切换中文。音频只在本机处理。**无需 Oracle、云账号、服务器订阅或 API 密钥。公网部署已取消，GitHub 公开工程供各自下载到本机使用。**

## 首次安装（Windows）

先安装 **Python 3.11+** 和 **Node.js 22.12+** 或兼容更新版本，并确保命令可在终端运行。当前验证平台为 Windows；现有启动脚本不是 macOS/Linux 安装器。识别可使用 CPU，不要求独立显卡，较大的录音需要更多可用内存。

已安装 Git 时，在 PowerShell 中执行：

```powershell
git clone https://github.com/Xian-JL/Audio-Converter.git
cd Audio-Converter
.\Setup.cmd
```

没有 Git 也可以在仓库点击 **Code → Download ZIP**，解压后双击项目里的 **Setup.cmd**。

保持安装窗口开启，直到提示完成。安装会准备 Python 环境和前端依赖、下载缺失模型及 FFmpeg、验证音色资源、按需生成测试夹具并构建网页。获取缺失资源需要联网；重复运行会复用兼容包和已校验文件。模型大文件和依赖环境不随 GitHub 源码提交。

## Windows 离线便携包

已准备好的完整便携目录中直接双击 Start.cmd，无需 Python、Node.js 或再次安装。普通 GitHub 源码 ZIP 不含运行时和模型，仍按上面的首次安装流程使用。

维护者可在完成 Setup 与前端构建后生成便携目录：

```powershell
.venv\Scripts\python.exe scripts/package_portable.py --output release/LocalAudio-0.7.2 --zip release/LocalAudio-0.7.2.zip
```

输出目录须不存在。打包只收集运行所需资源和依赖闭包，包含许可证及 SHA-256 清单，不带用户歌曲、工程或任务缓存。离线包体积明显大于源码；将整个目录复制或压缩后交付，不要只复制启动文件。

## 日常启动

双击项目里的 **Start.cmd**，或在项目目录执行：

```powershell
.\Start.cmd
```

然后在浏览器打开 **http://127.0.0.1:8765**。使用期间保持服务终端开启；在终端按 **Ctrl+C** 可停止。首次安装完成后，日常只需运行 Start.cmd，可以离线处理音频。右上角点击“中文”切换界面语言。

不要直接双击 index.html。`npm run dev` 仅启动开发前端，不能代替 Start.cmd 启动的 Python 服务。

## 使用

左侧填写 BPM、拍号与调并应用，选择一个不超过 100 MB 的 MP3/FLAC。原曲可先播放和下载，分析完成后中间显示旋律谱。

若小节强拍不对，点击“定位小节第一拍”，在全曲不同位置选择 1–5 个确定的第一拍起音。右侧会列出时间与估算小节号；确认或修改每点的小节号，须随时间递增。可逐点试听、移除并重选，再点击“重构乐谱”。程序在相邻参考点之间分段校正，中段的修正不会推移后面已锚定的区间。原版与各重构版分别保留，五个参考点随工程保存；旧单点工程仍可打开。此操作修正谱面拍位，不改变 GF 音高与实际演奏时间，也不自动补回漏音。

在“和弦”任务页点击“生成柱式和弦”。有旋律时只配柱式和弦；可根据旋律在同一小节内换和弦，候选包括大七、小七、属七、半减七和减七等。表格按小节与拍位显示，可修改或锁定具体和声段，保留乐句和时间偏移设置。

切换到“器乐”任务页，连续至少两个完整小节没有旋律时，会列出前奏、间奏或尾奏区间；持续长音、短换气和不足一小节的尾部不会被当作可填充区间。勾选所需区间并调整起止小节，再点击“生成所选器乐段”。模型只在选中空白段创作，两手可自由使用旋律、和弦或琶音；有旋律的部分仍严格使用柱式和弦。“仅柱式和弦”和生成候选可随时切换。

器乐段可选择 EMO 或 MIDI Emotion，再选择情感方向与张力走向。默认预选“忧伤、有力量 / 逐渐增强”；这两个设置是实际模型条件，不会从调性自动猜测情感。切换已保存候选会显示对应设置，可保存多个结果试听比较。新作效果和情感吻合仍需听感判断，不是原曲器乐还原。

两模型均使用本机 CPU、离线推理，暂支持 4/4；其他拍号仍可使用柱式和弦。保留进度与真正取消，失败不会清空原候选。SetupTexture.cmd 准备两种模型，已有资源会复用；下载需要可访问 Google Drive，scripts/download_emotion_models.ps1 支持代理及断点续传。旧 AMT/AccoMontage 和上一版器乐候选仍可恢复试听，生成入口使用新的情感模型。

点击任意小节即可从该小节播放，也可通过小节选择框跳转。默认旋律/伴奏电平为 60/40。高音谱表为人声，谱面高八度书写、试听音高不变；低音谱表为新编伴奏。高音和低音可分别配置多乐器合奏。12 种本地采样乐器均提供原声、温暖、明亮、柔和四档处理音色，共 48 档；每层可设数量、启用、音量与声像。音色由既有真实采样处理生成，复用采样资源。每声部最多 8 层、16 件，单层最多 8 件；默认电平仍为 60/40。

点击“保存工程”保留完整 .acproject.json：原始 GF、每次修订/重构、各版和弦与伴奏、音色、音量、播放位置和循环范围。下次点击“打开工程”继续，无需重新分析。工程默认不含音频；需要原曲对照时点击“关联原音频”，选择当时完全相同的原文件。错误文件或损坏工程不会清空现有作品。刷新前请主动保存，页面不会自动保存歌曲或工程。

“编辑旋律”模式可点击高音谱音符，修改实际 MIDI 音高、起音和结束秒数，插入、删除、拆分或合并同音；每次修改另存版本，可撤销重做，原始 GF 始终保留。编辑后重新生成和弦。定位第一拍仍按原方法操作。

勾选“循环播放”，设置起止小节即可反复试听；点击范围外的小节会退出循环并从那里播放。两谱表音量可独立调整，默认 60/40。持续型弦管乐与管风琴支持采样延音；钢琴和拨弦乐器保留自然衰减。

器乐段的新增音符使用独立声部，原 GF 旋律和各定位点保持原样。保存工程后再次打开会直接恢复已有音符，不重新生成。

乐谱默认使用紧凑排版以增加每页小节数，也可选择标准密度。完整一页按中央区域的可用宽高等比缩放，窗口不需上下滚动；左右功能面板独立滚动，窄屏通过“音频／乐谱／工具”切换。网页和导出保持同一套 A4 页码。可在暂停时手动翻页；播放乐谱或原曲时会自动显示当前小节所在页。“下载此页 PNG”导出当前页，“导出全部页”一次下载包含各页 PNG 的 ZIP，文件按《曲名》Page_1.png、Page_2.png 顺序命名。PNG 为 2480×3508 像素，包含曲名、参数、当前音色及页码。图片替代原 MusicXML 下载。展开“打印与导出选项”可导出页码范围、取消进行中的导出，或打开 A4 打印/保存 PDF；PNG 带 300 dpi 标记。

桌面采用左中右三栏：左侧导入音频、打开工程和填写参数，中间保留播放与完整一页乐谱，右侧按“旋律、和弦、器乐、演奏、导出”切换任务。“保存工程”始终可用，切换任务保留草稿和正在生成的候选。“演奏”页包含乐器、音量及“谱面与播放”中的小节跳转、循环、页码与密度；“导出”页提供 PNG、ZIP 和打印。窄屏通过“音频／乐谱／工具”切换区域。分页浏览不改变音频位置，播放时自动跟随当前小节。

## EMO 乐句发展基线

EMO 现在按引入、发展与收束组织器乐乐句，保留主题，减少连续照搬的音型，并衔接后续旋律。原有情感与张力选项不变。新增 exports/EMO-呜-乐句发展示例.acproject.json：第三个候选标有“乐句发展”，旧两个候选、前奏和原旋律保持不变，可直接试听对比。对应间奏钢琴试听为 EMO-呜-间奏乐句发展试听.wav。此具体示例已经用户试听认可，0.7.2 保留其算法与文件；示例属于本机私有文件，不随 GitHub 源码发布。

## 新版对照示例

本机已准备 exports/情感器乐-呜-对照示例.acproject.json，打开后在“试听版本”切换 EMO 与 MIDI Emotion。“忧伤、有力量 / 逐渐增强”是明确指定的目标，是否贴合歌曲仍需试听。exports 下另有两份间奏钢琴试听 WAV，包含间奏前后各六秒旋律上下文，不是原录音。

## 谱面自动简化

旋律、第一拍校正和伴奏准备好后，系统自动简化最终谱面，再用于网页、PNG、ZIP 和打印。只合并严格等价的延音片段与合法休止，不改实际音高、重复起音或播放时间；跨小节延音、拍组和特殊标记受到保护。切换版本、编辑、重新定位或打开旧工程时自动重算，无需重新生成伴奏。复杂节奏可能仍保留多段延音，页数不保证减少。

## 配置合奏

例如在高音选择“小提琴”，数量填 4；低音保留“三角钢琴”，点击“添加低音乐器”再选择“大提琴”，即可同时播放四把小提琴旋律与钢琴/大提琴伴奏。每层可单独调整音色，展开“独立混音”调整音量与声像。合奏数量会自动做电平补偿，模拟实例间轻微音准、起音与声像差异。

保存工程同时保存合奏和页面密度。新文件使用工程格式 2；旧格式 1 可迁移为单件原声音色。打开工程不重跑识别，也不改变原 GF 音高和节奏。

## 维护与验证

当前路线与模块边界见 [ARCHITECTURE.md](ARCHITECTURE.md)，验证入口见 [tests/README.md](tests/README.md)。已过时的界面脚本归入 tests/legacy-ui，保留研究记录；0.7.2 使用 studio、layout 与 notation-ui 作为主要界面回归。

```powershell
npm.cmd run build
npm.cmd test
node tests/playback.mjs
node tests/export.mjs
node tests/notation-plan.mjs
```

网页回归使用独立的本机测试服务，不使用真实工作任务：保持正常网页服务在 8765，另开终端运行 `.venv\Scripts\python.exe -B tests/serve_ui.py 8770`；在执行回归的终端设置 `$env:QA_API_URL='http://127.0.0.1:8770'`。然后可运行 `node tests/notation-ui.mjs`、`node tests/pagination.mjs`、`node tests/downbeat.mjs`、`node tests/studio.mjs`；新布局与合奏使用 `node tests/v4.mjs`，其 API 已固定转发到测试服务。音色长音与压力检查需另启动 `npm run dev`，执行 `node tests/sound.mjs`、`node tests/ensemble-sound.mjs`。开发测试需另有 Playwright/Chromium，可用 PLAYWRIGHT_PACKAGE、TEST_BROWSER_PATH 指向现有安装，不增加产品依赖。公开音频夹具为合成静音；私人歌曲和实测旋律不提交仓库。

新增音色资源由 `scripts/instrument_resources.py` 准备，Setup.cmd 已包含；资源就绪后所有音色均可离线使用。模型修复分别运行 `setup-game.ps1` 或 `SetupTexture.cmd`，完整安装使用 `Setup.cmd`。保留 `.venv`、`node_modules`、`models`、`tools` 和 `dist`，可直接启动及继续构建；不要把这些运行资源当作旧实验删除。

## 项目边界

这是本机网页与本机 Python 服务，本机模式不上传音频。旋律识别和自动伴奏仍有误差；和声由旋律编写，不还原原曲伴奏。BPM、拍号、调及第一拍由用户确认。详细规范见 [SPEC.md](SPEC.md)，发布验证与清理记录见 [RELEASE.md](RELEASE.md)。

公开工程包含前端、Python 服务、下载脚本、测试、文档与许可来源；不提交模型权重、FFmpeg 程序、依赖环境、用户歌曲或其实测音符 JSON。Setup 会准备缺失资源，并在夹具缺失时生成确定性的合成测试数据，不覆盖本地已有实测夹具。

服务仅监听本机地址。另一台设备上的 `127.0.0.1` 指向那台设备自身；其他使用者需要各自在本机安装和启动。公开源码仓库不是共享的在线处理网站。

GitHub Actions 仅进行前端构建、Node 检查与轻量记谱/和弦回归，不下载大型模型；完整本机测试仍需安装资源。

## 更新与常见问题

更新前停止服务。使用 Git 的用户拉取新源码后运行 Setup.cmd，再运行 Start.cmd 并刷新网页；使用 ZIP 的用户解压新版到项目目录后运行 Setup.cmd。每次换歌不需要重装。

| 情况 | 处理方法 |
| --- | --- |
| 网页无法连接 | 确认 Start.cmd 终端仍在运行，并访问完整地址 `http://127.0.0.1:8765` |
| 提示缺少模型或资源 | 运行 Setup.cmd；GitHub 源码本身不包含模型权重 |
| 下载资源失败 | 检查能否连接对应上游来源，再运行 Setup.cmd，已完成的有效资源会复用 |
| 提示已有服务或端口 8765 被占用 | 使用已有应用，或关闭它的旧服务终端后重启 |
| 更新后提示重新启动服务 | 停止旧服务，重新运行 Start.cmd，再刷新网页 |
| 当前拍号不能生成器乐段 | 器乐生成目前支持 4/4，其他既有拍号仍可使用柱式和弦 |

## 借鉴的开源成果

| 项目 | 在本项目中的作用 | 许可与来源 |
| --- | --- | --- |
| [GAME](https://github.com/openvpi/GAME) | 歌唱旋律 ONNX 模型与适配的 GF 上下文分块驱动 | 1.0.3，MIT，许可证保留 |
| [Demucs](https://github.com/facebookresearch/demucs) / [ONNX 导出](https://github.com/StemSplit/demucs-onnx) | 增强人声分离 | MIT，固定导出与哈希保留 |
| [Ultimate Vocal Remover / MDX](https://github.com/Anjok07/ultimatevocalremovergui) | 原分离模型、配置和资料 | 下载来源与校验保留 |
| [AccoMontage2](https://github.com/billyblu2000/AccoMontage2) | 基本和弦资料与适配搜索 | MIT，固定提交及资料来源保留 |
| [EMO-Disentanger](https://github.com/Yuer867/EMO-Disentanger) | 默认情感器乐段生成及乐句发展适配 | MIT 源码，权重与数据范围单独记录 |
| [MIDI Emotion](https://github.com/serkansulun/midi-emotion) | 连续情感条件的对照生成引擎 | GPL-3.0-or-later 源码，保留原声明 |
| [Anticipatory Music Transformer](https://github.com/jthickstun/anticipation) | 历史器乐引擎与回归参考，既有结果继续可读 | Apache-2.0 源码与权重，固定提交与资源哈希 |
| [AccoMontage](https://github.com/zhaojw1998/AccoMontage) | 历史 VAE 实现及回归参考，已有结果继续可读 | MIT 源码，模型资料许可单独记录 |
| [Salamander / Tonejs audio](https://github.com/Tonejs/audio/tree/master/salamander) | Alexander Holm 的 Yamaha C5 钢琴采样 | CC BY 3.0，声明保留 |
| [tonejs-instruments](https://github.com/nbrosowsky/tonejs-instruments) | N. P. Brosowsky 整理的新增乐器采样 | 采样 CC BY 3.0，收集者及原贡献者声明保留 |
| [OpenSheetMusicDisplay](https://github.com/opensheetmusicdisplay/opensheetmusicdisplay) | 绘谱与分页 | BSD-3-Clause |
| [Tone.js](https://github.com/Tonejs/Tone.js) | 采样播放与共享时钟 | MIT |
| [FFmpeg](https://ffmpeg.org/) | 验证、解码与 MP3 转换 | 安装二进制的 GPLv3 声明保留，仓库不分发该二进制 |
| React、Vite、TypeScript、Flask、ONNX Runtime、PyTorch | 应用、构建与推理基础 | 各自上游许可 |

人工第一拍、时间映射、基本和弦规划、织体检索、记谱、界面及图片导出是集成与适配工作，不宣称从零训练模型，也不是未经改动的完整 AccoMontage。详细提交、哈希、素材与模型许可范围见 THIRD_PARTY 和各资源清单。

仓库设置为公开。本次未为原创部分另选项目许可证；第三方代码与素材继续适用各自原许可。原始训练曲目不因源码许可自动取得独立授权。

## 本地目录与清理

src、server、scripts、tests 保存源码与回归脚本；public、models、tools、vendor 保存采样、模型、媒体工具及上游来源，日常运行需要保留。已有 .venv 和 node_modules 复用，不为清理而重复安装。

dist 为当前网页构建；tests/output 为可重新生成的测试结果；release 保存另行制作的便携包；本版仅发布源码，没有重打便携包。tests/output 为可再生成的检查证据。已认可的 exports 工程与试听、模型原包、原始歌曲和历史作品应保留；只按明确范围清理可再生成的临时文件。真实歌曲与自己的 .acproject.json 请保存在项目目录之外，不提交到 GitHub。不要在运行任务期间清理 .runtime。

中央只保留单行播放/进度与最大化整页乐谱。小节跳转、循环范围、页码和页面密度统一收在右侧“演奏 → 谱面与播放”；透明翻页键仍紧邻谱面两侧。保持 A4 等比完整显示，因此宽高比例与屏幕不同时会保留必要留白。

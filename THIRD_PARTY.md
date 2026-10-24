# 第三方资源

## 旋律与分离

GAME 1.0.3 small ONNX 来自 https://github.com/openvpi/GAME ，驱动保持 GF 分块流程；许可证为 server/GAME-LICENSE.txt。模型仅从 models/game-small 读取，当前文件哈希与已复核整曲分析记录一致。

MDX 及增强 Demucs ONNX 的下载来源与哈希记录于 models/manifest.json、models/demucs-manifest.json。相应许可证保留于 models/demucs-LICENSE.txt 和 models/demucs-onnx-LICENSE.txt。MDX 配置与来源资料保留，用于原分离流程及资源验证。

## 和弦与织体

基本和弦使用 AccoMontage2 https://github.com/billyblu2000/AccoMontage2 ，提交 39184ae5cd8be1de289d116d12b69892a034f1b6。已转换的纯 JSON 资料位于 server/data/basic-harmony.json；vendor/AccoMontage2/SOURCE.json 记录生成输入的原始哈希，原输入与开发转换工具在收束时移除，MIT 许可证保留。

丰富伴奏使用 AccoMontage https://github.com/zhaojw1998/AccoMontage ，提交 9630afe08eb2e90b0b94fcf97154d9385fda5e4c。vendor/AccoMontage 只保留实际推理加载的四个原始模块，SOURCE.json 记录保留子集，MIT 许可证原文保留。模型、压缩候选库及官方资源下载地址/哈希记录于 models/accomontage/manifest.json。

短语检索、左手缩编和时间映射为本项目适配。源码许可证不自动等同于所有训练曲目材料的独立授权；此项目当前用于用户本机分析与试听。

## 音色、媒体工具与界面依赖

钢琴为 Alexander Holm 的 Salamander Yamaha C5 采样，CC BY 3.0，原文及固定来源位于 public/piano/LICENSE.txt、UPSTREAM-NOTICE.txt、manifest.json。由本地 Tone.js 播放。

FFmpeg/FFprobe 使用本地 tools 目录内程序，许可证保留于 tools/FFmpeg-LICENSE.txt。前端依赖及版本以 package-lock.json 为准，Python 直接需求见 requirements.txt 与 requirements-texture.txt。许可证随安装包保留，不裁剪正在使用的依赖包内容。

## 测试资料

公开仓库不包含用户歌曲及其实测音符 JSON。ui-upload.flac 和 ui-preview.mp3 为人工生成的静音。scripts/generate_test_fixtures.py 可生成确定性的合成音符夹具，不会覆盖本地已有文件。私有试听数据由 Git 忽略，不作为公开数据集发布。合成夹具用于软件回归，不用于音乐质量评价。

## v0.2 多乐器采样

新增采样来自 https://github.com/nbrosowsky/tonejs-instruments ，固定提交 622c2f1c32c8cfce4158ddc3eb26e518ddef37e5。仅使用采样，不引入上游加载器。源库声明采样为 CC BY 3.0，上游代码为 MIT。原 LICENSE.md、sample-source-info.txt 及各文件 SHA-256 保留于 public/instruments，构建时复制至本地 dist。

新增 11 种乐器，共 74 个锚点 MP3，15,376,302 字节（约 14.7 MiB）。候选映射由固定上游音符表提取，按音域选取锚点，间隔音由 Tone.Sampler 重采样。每种乐器使用真实采样，未用同一个合成器换名替代。与已有钢琴合计 12 种。处理与播放时只访问同源本机资源。

## v0.3 适配与便携运行时

音符编辑、工程格式、声部分配、乐句包络、重复动机复用和有限度 RMS 校准由本项目实现；没有新增识别模型，也没有修改保留的上游模块。持续型音色继续使用上述 CC BY 3.0 采样，在内存中构造循环和释放包络，来源说明不变。

便携包从本机已安装发行包的 RECORD 收集运行依赖闭包，并保留各 dist-info 的许可信息及 Python 根目录 LICENSE。包版本、文件大小和 SHA-256 记录于 bundle-manifest.json。仅移除测试、缓存和开发头文件，不移除许可证。构建脚本不下载或重新授权第三方模型；源码公开不代表本项目原创代码自动采用 MIT。

## v0.4 处理音色与合奏

原声、温暖、明亮、柔和四档使用上述既有采样和 Tone.js 的 EQ/包络，不新增采样来源。多件合奏复用采样文件，以独立播放实例、微小音分/起音/声像差异及电平补偿模拟多人效果。处理后的音色继续保留采样来源及 CC BY 3.0 署名；音色名称不表示新琴款或新演奏者录音。紧凑排版和适屏仍使用已有 OSMD，无新增前端依赖。

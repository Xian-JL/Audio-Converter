# Local use only / 仅本地使用

Updated 2026-10-23: public deployment was cancelled by the owner. No Oracle, Sites, Cloudflare Tunnel or other cloud-hosting setup is required or pending. The GitHub repository remains public for downloading and running the source locally.

2026-10-23：用户已取消公网部署。无需继续 Oracle 注册，也不再进行 Sites、Cloudflare Tunnel 或其他云主机配置。GitHub 继续公开源码，使用者各自在自己的电脑安装、运行。

## Installation and startup / 安装与启动

See [English local-use instructions](README.md) or [中文本地使用说明](README.zh-CN.md). On the tested Windows setup, run Setup.cmd once to install missing resources, then Start.cmd for everyday use. Open http://127.0.0.1:8765 and keep the service terminal running.

当前验证平台为 Windows。首次运行 Setup.cmd 准备资源，日常运行 Start.cmd，在浏览器打开 http://127.0.0.1:8765，保持服务终端开启。首次准备缺失资源需要联网，准备完成后可离线处理音频。

## Scope / 运行范围

The Python service listens on loopback, processes one local active task and uses local model/instrument resources. It has not been adapted into a public multi-user service. User audio and private listening-analysis JSON are not part of the public repository.

Python 服务监听本机回环地址，按当前单任务流程处理，使用本地模型及音色资源。没有将其改为公网多用户服务；用户音频和私有试听分析 JSON 不进入公开仓库。

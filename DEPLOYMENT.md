# Deployment status / 部署状态

Checked on 2026-10-23. The desktop application works locally; no public inference backend has been provisioned. The public GitHub repository is source distribution, not a claim of live public audio processing.

核查日期：2026-10-23。本机完整版可用，尚未配置公网推理主机。GitHub 公开工程不等于陌生设备已经能够在线完成全部处理。

## Why AI Price Atlas's free hosting is different

AI Price Atlas uses a Vinext/React Cloudflare Worker for pages and a light exchange-rate API. Its Python collectors run in GitHub Actions, write snapshots and then deploy those snapshots. The Worker does not host the Python collectors as persistent processes. Audio Converter must run separation, GF inference and texture generation on each visitor's new upload, which cannot be precomputed into a snapshot.

AI Price Atlas 的网页与轻量接口在 Worker，Python 采集在 GitHub Actions。本项目要对每个访客新上传的音频即时运行模型，不能照搬预生成快照的部署方式。

## Verified hosting constraints

| Platform | Confirmed conditions | Suitability |
| --- | --- | --- |
| Sites / Cloudflare Workers Free | Static/frontend hosting; Workers have 128 MB per isolate and 10 ms free CPU/request | Frontend or proxy, not the present inference process |
| Cloudflare Containers | Worker Paid plan; separately metered container usage | Possible full backend after adaptation; not a free equivalent of Atlas |
| Oracle Always Free A1 | Current official allowance equivalent to 2 OCPUs and 12 GB; home-region capacity constraints | Candidate free compute; account, capacity and ARM/Linux compatibility must be validated |
| Google Cloud Run | Monthly free allocation, billing for excess; billing/CPU lifecycle affects background tasks | Possible low-volume deployment after job-lifecycle adaptation; not guaranteed zero cost |
| Hugging Face Spaces | CPU Basic has no hourly fee, but new normal Docker/compute Spaces require a paid plan; free personal accounts may have up to two ZeroGPU Gradio Spaces | Do not call a new ordinary Docker Space free; ZeroGPU needs a different Gradio/compute integration |

Official sources: [Workers limits](https://developers.cloudflare.com/workers/platform/limits/), [Containers pricing](https://developers.cloudflare.com/containers/platform/pricing/), [Oracle Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm), [Cloud Run pricing](https://cloud.google.com/run/pricing), [Spaces overview](https://huggingface.co/docs/hub/en/spaces-overview). Eligibility and quotas may change; account access and capacity are not verified by documentation alone.

## Required architecture for public use

Sites can serve the frontend, with an authenticated server-to-server proxy to a separately hosted Python backend. The frontend must describe remote audio processing accurately instead of retaining the desktop-only privacy promise. Host address/credentials must stay in server-side secrets, never the public bundle.

Before exposure, jobs must be isolated by visitor/session. The existing desktop upload/reset lifecycle deliberately cancels the active local job; it must not cancel another visitor's job in shared hosting. Public deployment also needs bounded inference concurrency, upload/task limits, expiry/cleanup, Linux-compatible FFmpeg paths and origin/host configuration. These are required deployment changes, not configuration switches that have already been implemented.

公开部署需要独立的访客任务隔离、并发限制、清理与 Linux 运行环境，以及准确说明音频会传到处理主机。当前服务只允许本机来源，上传或重置会取消本机活跃任务；不能简单去掉来源限制就公开发布。

## Current next dependency

Choose and provide an accessible compute host/account before enabling full public inference. No paid plan or compute purchase is authorized or activated by the repository setup. Do not substitute a nonworking static copy for the complete application and call deployment complete.

下一步需要选定可用的算力主机或账号。仓库准备不会开通付费服务，也不把缺少后端的静态页面标成完整应用已部署。

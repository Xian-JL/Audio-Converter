# Deployment status / 部署状态

Checked on 2026-10-23. The desktop application works locally; no public inference backend has been provisioned. The public GitHub repository is source distribution, not a claim of live public audio processing.

Oracle was explicitly excluded by the owner on 2026-10-23. Do not continue its signup or treat an Oracle VM as the selected deployment target. The alternatives below remain subject to a compute-host choice.

核查日期：2026-10-23。本机完整版可用，尚未配置公网推理主机。GitHub 公开工程不等于陌生设备已经能够在线完成全部处理。

用户已于 2026-10-23 排除 Oracle 路线，不再继续其注册或实例创建。接下来在免费本机公网演示、具备资格的免费云端或其他付费主机之间确定部署目标。

## Why AI Price Atlas's free hosting is different

AI Price Atlas uses a Vinext/React Cloudflare Worker for pages and a light exchange-rate API. Its Python collectors run in GitHub Actions, write snapshots and then deploy those snapshots. The Worker does not host the Python collectors as persistent processes. Audio Converter must run separation, GF inference and texture generation on each visitor's new upload, which cannot be precomputed into a snapshot.

AI Price Atlas 的网页与轻量接口在 Worker，Python 采集在 GitHub Actions。本项目要对每个访客新上传的音频即时运行模型，不能照搬预生成快照的部署方式。

## Verified hosting constraints

| Platform | Confirmed conditions | Suitability |
| --- | --- | --- |
| Sites / Cloudflare Workers Free | Static/frontend hosting; Workers have 128 MB per isolate and 10 ms free CPU/request | Frontend or proxy, not the present inference process |
| Cloudflare Containers | Worker Paid plan; separately metered container usage | Possible full backend after adaptation; not a free equivalent of Atlas |
| Oracle Always Free A1 | Previously investigated; excluded by owner | Not a deployment target |
| Google Cloud Run | Monthly free allocation, billing for excess; billing/CPU lifecycle affects background tasks | Possible low-volume deployment after job-lifecycle adaptation; not guaranteed zero cost |
| Hugging Face Spaces | New ordinary Docker/compute Spaces require a paid plan. Free ZeroGPU hosting requires a verified personal account older than 30 days, in good standing; up to two Gradio Spaces | Requires eligibility and Gradio/ZeroGPU adaptation; not an immediate free Docker host |
| Cloudflare Quick Tunnel + owner computer | No Cloudflare account/domain needed for a temporary URL; the owner's computer supplies the compute | Free testing/demo route; computer must stay online. URL stops with the tunnel and is not a production hosting commitment |

Official sources: [Workers limits](https://developers.cloudflare.com/workers/platform/limits/), [Containers pricing](https://developers.cloudflare.com/containers/platform/pricing/), [Oracle Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm), [Cloud Run pricing](https://cloud.google.com/run/pricing), [Spaces overview](https://huggingface.co/docs/hub/en/spaces-overview). Eligibility and quotas may change; account access and capacity are not verified by documentation alone.

## Required architecture for public use

Sites can serve the frontend, with an authenticated server-to-server proxy to a separately hosted Python backend. The frontend must describe remote audio processing accurately instead of retaining the desktop-only privacy promise. Host address/credentials must stay in server-side secrets, never the public bundle.

Before exposure, jobs must be isolated by visitor/session. The existing desktop upload/reset lifecycle deliberately cancels the active local job; it must not cancel another visitor's job in shared hosting. Public deployment also needs bounded inference concurrency, upload/task limits, expiry/cleanup, Linux-compatible FFmpeg paths and origin/host configuration. These are required deployment changes, not configuration switches that have already been implemented.

公开部署需要独立的访客任务隔离、并发限制、清理与 Linux 运行环境，以及准确说明音频会传到处理主机。当前服务只允许本机来源，上传或重置会取消本机活跃任务；不能简单去掉来源限制就公开发布。

## Current next dependency

Choose between an owner-computer demo, an eligible cloud account, or a separately approved paid host before enabling public inference. An owner-computer demo needs an explicit choice because visitors' audio will be uploaded to that computer. No paid plan or compute purchase has been authorized or activated. Do not substitute a nonworking static copy for the complete application and call deployment complete.

下一步需要确定是否接受本机持续开机接收访客音频，或提供符合免费资格的其他云账号，或确定其他主机预算。未开通任何付费服务，也不把缺少后端的静态页面标成完整应用已部署。

Additional references: [ZeroGPU eligibility and quotas](https://huggingface.co/docs/hub/spaces-zerogpu), [Quick Tunnel lifecycle and testing-only scope](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).

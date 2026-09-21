# Folia 歌词视频工坊交接（Claude Code）

原始交接日期：2026-09-14；本次更新：2026-09-21

## 2026-09-21 接管快照（请优先阅读）

以下内容覆盖本文件后面的旧交接状态；旧记录保留用于历史背景，不要按旧日期的“接手后优先事项”重复操作。

- 当前本地项目仍是 `C:\Users\34862\Documents\飞牛\folia-video-studio`；NAS 部署目录是 `/vol1/1000/docker/folia-video-studio`，入口 `http://100.111.1.11:18081/`。
- 已正式部署 Folia `v0.7.7` / Docker Stack `1.0.26`，原生渲染器 revision `80c073490482303d4283d1d5205be7707c96179d`，补丁 profile `studio-font-outline-v1`。正式 API、网页、转录服务和原生渲染器均已健康。
- 效果页现在只保留 classic 和 Folia 原生；Folia 原生保留 13 个模式。历史 AMLL/Kinetic/旧 Folia 效果不改数据库，加载时回退 classic。
- Folia 原生新增统一主歌词描边：默认开启、黑色、3 px，可关闭，宽度 0–12 px，可调颜色；新增内置思源黑体/宋体/中文等宽字体、字重和 TTF/OTF/WOFF2 上传；预览、快速 MP4、透明 MOV 共用字体配置。
- 已切换新版 transcriber 镜像，事件 `folia_update_available` 已在正式容器中加载。用户授权过“打断再续”：切换时当前整场 ASR 没有从零重跑，已读取现成 transcript 并完成，后续自动队列已恢复。不要为验证再次取消、重跑或重新切片已有录播。
- 已做正式镜像回归，使用独立测试项目《离人赋_v077正式回归》，没有覆盖旧项目和旧成品：快速样片 1920×1080、30fps、H.264 + AAC，15 秒 450 帧经 `mpdecimate` 保留 417 帧；2:04.5 无全屏灰层，3 px 黑色主歌词描边可见；透明样片为 ProRes 4444 `yuva444p12le`、30fps、无音轨，2:04.5 Alpha 平均值约 0.8%，不是实色画布。测试输出：`/vol1/1000/video/Folia成片/芒芒_Mou/2026-09-21/高置信/离人赋_v077正式回归/`。
- 备份在 `/vol1/1000/docker/folia-video-studio-backups/20260921-v077/`，包括 compose、数据库、版本信息和字体目录。不要删除旧 `1.0.19` 镜像、旧成品、录播或切片。
- GitHub 尚未同步本次升级。NAS 上另有 git 工作副本 `/vol1/1000/docker/folia-git`，远端是私有仓库 `q1019161539/folia-`，当前 `main` 与 `origin/main` 停在 `b13078a`（2026-09-20）；部署目录 `/vol1/1000/docker/folia-video-studio` 本身不是 git 仓库。本次源码和文档需要先整理进正确仓库，再由用户明确授权后提交、推送；不要把 `.env`、`data/`、`models/`、`work/`、备份、媒体或密钥带入提交。
- 本次新增/修改的关键文件包括：`backend/folia_native.py`、`backend/font_assets.py`、`backend/folia_upstream.py`、`folia-renderer/patch_upstream_source.py`、`folia-renderer/Dockerfile`、`web/index.html`、`web/app.js`、`compose.yaml` 及相关 docs。正式部署前已通过后端 188 项、transcriber 30 项、前端语法和上游源码补丁校验；不要把压缩 bundle 字符串替换作为后续更新方式。
- 接手第一步应先重新读取 `AGENTS.md`、`docs/STATUS.md`、`docs/README.md` 和本文件，然后只读检查 NAS 容器和队列。不要重复构建、重启或渲染，除非先确认当前队列/重任务槽状态并得到用户授权。

## 开始前

请依次完整阅读：`AGENTS.md`、`docs/STATUS.md`、`docs/README.md`，然后只读当前相关的 `docs/modules/asr-alignment.md`、`docs/modules/automation.md` 和 `docs/deployment.md`。

- 本地项目：`C:\Users\34862\Documents\飞牛\folia-video-studio`
- 飞牛项目：`/vol1/1000/docker/folia-video-studio`
- ASR 数据：`/vol1/1000/docker/folia-asr-mvp`
- 网页：`http://100.111.1.11:18081/`

连接凭据不要写入仓库或日志；需要时向用户索取。

## 已完成并部署

本次目标是最小改动修复标准歌词“前半准确、后半漂移”。

- `backend/standard_timeline.py`
  - 全局 `shift_ms` 只作 fallback。
  - 新增 `interpolated_shift_ms()`，按多个可靠、单调的 ASR/LRC 锚点做分段线性插值。
  - 每行保存 `local_shift_ms`；直接锚点保留 `asr_start_ms/asr_end_ms`。
  - 候选置信度仍按紧密锚点簇判断；更宽的漂移锚点只接受 `text_score >= 0.8` 的强匹配，避免长 ASR 段的弱匹配把段起点误当行起点。
- `backend/word_timeline.py`
  - provider 字锚点按局部插值偏移筛选，不再只围绕单一全局 shift。
  - 行内有至少两个可靠 Qwen 锚点时，以真实 Qwen/provider 差值移动该行窗口，保留 Qwen 实际字时间。
- `backend/app.py`
  - 自动标准模式改为 `standard-piecewise`，报告局部偏移范围。
  - standard-LRC 行不再调用 `clamp_forced_words()` 锁回原时间窗口。
  - 有 ASR 证据的行优先使用实际 ASR 搜索窗口；无证据行使用局部 LRC 粗窗口 fallback。
  - Qwen 成功后用真实首尾字时间更新整行起止，即使该行有 `fixed_timeline`。
  - 行顺序保护比较起点，不再用上一句长音结束限制下一句；尾部标准化不移动可靠后句起点。
- `backend/app.py`、`transcriber/app/notify.py`
  - 自动流程最终通知分别统计成功、失败和跳过；部分失败也发送通知，不再静默进入下一场。

新增回归测试在 `backend/test_standard_timeline.py` 和 `backend/test_word_timeline.py`。

## 验证状态

- 后端单测：37/37。
- transcriber 单测：8/8。
- API、transcriber、AI worker、歌词服务均健康。
- 实测项目：《世界上的另一个我》，ID `a098c1c7c6aa496f8875702cc24c00fb`。
- 未重新 ASR、未重新切片、未修改原录播，只复用了现有数据。
- 候选仍为高置信 `netease:3383264482` / `DJ大大怪`。
- 全局 fallback shift `+2596 ms`；8 个锚点局部 shift `+1650～+3956 ms`；P90 残差 `1360 ms`。
- ForcedAligner 58/59；唯一失败行“心有灵犀的”因逐字时间过度压缩而保留粗时间。
- 最终有效歌词行起点倒序为 0，保留 6 处接唱/延音重叠。
- 成品目录：`/vol1/1000/video/Folia成片/芒芒_Mou/2026-09-14/高置信/世界上的另一个我/`

## 接手后优先事项

1. 不要重新执行上述项目的 ASR 或切片。
2. 若继续优化，先判断唯一 fallback 行是否值得调整短句压缩质量门槛；不要为追求 59/59 无条件接受坏字时间。
3. 再找一首已知后半段偏离的现有项目，只执行 standard timeline、force-align 和 render 做回归。
4. 保持“候选版本置信度”和“局部漂移锚点”职责分离，并先补测试再部署。

## 禁止事项

- 不重新启动已经完成的 14 首重跑。
- 不重复 ASR，不重新切片。
- 不修改或删除原录播。
- 不删除旧目录或旧成品。
- 不把密码、Webhook 或 Basic Auth 写入仓库、文档或日志。

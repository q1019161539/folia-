# Claude Code 交接：自动投稿与主播模板绑定

日期：2026-09-27

## 当前目标

Folia 自动成片后创建独立投稿准备任务，封面、标题、简介和 tags 整理完成后交给 BililiveTool。Phase 1 只读取 preset、格式化简介、冻结 payload 并调用 `validUploadParams`，全局 `AUTO_PUBLISH_ENABLED=0`，自动流程不得调用 `/api/bili/upload`。

本轮新增需求是在“锁定主播”的自动化规则里实时读取 BililiveTool 视频投稿模板，让每个主播显式选择一个 preset。后续投稿任务快照该选择，并继承 preset 简介。

## 已实现

- `automation_profiles` 增加 `publish_streamer`、`bililive_preset_id`、`bililive_preset_name`，均通过启动迁移添加。
- 自动化规则创建/编辑表单新增 BililiveTool 投稿模板下拉框，规则卡显示已绑定主播和模板。
- 新增只读 `GET /api/publish-presets`，真实调用 BililiveTool 3.18.0 的 `GET /api/preset/video`。
- 保存规则时再次读取指定 preset，拒绝不存在的 ID，不信任前端传来的模板名称。
- 创建 `publish_job` 时只从规则读取投稿主播和 preset ID；歌曲身份仍只取 `identified_title`、`identified_artist`、`identity_source`。
- 准备阶段优先使用 preset 的 `config.desc`，调用真实 `POST /api/bili/formatDesc` 展开 `{{now}}` 等变量；preset 简介为空才使用 Folia 固定简介。
- 从 preset 深拷贝完整 `config`，仍只覆盖 Folia 负责的 `title`、`desc`、`tag`、`cover`。
- payload 在校验前冻结；已有 payload、`ready` 或已完成任务不会因规则或 preset 后续变化被静默改写。
- 没有加入任何自动上传调用，`backend/publishing.py` 中仍不存在 `/api/bili/upload`。

## 线上状态

- NAS：`100.111.1.11`，部署目录 `/vol1/1000/docker/folia-video-studio`；认证信息只从现有环境取得，不写入代码、文档或 Git。
- API/Web 已于本轮重建并健康，`/healthz` 显示 `publish_enabled=true`、`auto_publish_enabled=false`。
- 芒芒规则 `bc87122ccfbb4403a15efafb3ae01cc6` 已显式绑定：
  - `publish_streamer=芒芒_Mou`
  - `bililive_preset_id=s9iw1rmff2`
  - `bililive_preset_name=芒芒_Mou`
- 真实模板列表当前包括：`default`、`ign19v4u95a（管珩心）`、`s9iw1rmff2（芒芒_Mou）`、`fgz0587t2u4（芒芒预设）`。
- 真实 `formatDesc` 验证已把 `{{now}}` 展开为 `2026.09.27`。
- BililiveTool 当前只有本轮人工验收的一个 B 站任务，没有因自动化模板功能新增上传任务。
- 人工验收视频《日不落》：BililiveTool 任务 `7e44efd0-3286-4c53-aeec-462d6738d27e`，AID `117342482861714`，BVID `BV1pBa86rEYc`，已开放浏览。
- 对应 Folia `publish_job`：`a36d3c3803e242c1845da66437c81ddc`，已记录 `completed/success`。
- 《日不落》是模板继承功能上线前冻结并人工提交的任务，因此它的线上简介和 payload 仍是旧 Folia 固定简介；不要静默改写历史投稿。
- 部署前代码与 SQLite 一致性备份：`/vol1/1000/docker/folia-video-studio-backups/20260927-preset-binding/`。

## 最后一个已写入源码、尚未重建上线的修正

首次部署后发现旧自动化规则的数据库列为空时，响应层会回退显示全局默认 `s9iw1rmff2`，导致其他主播看起来像已选“芒芒”模板。源码已经改为：

- `automation_profile_row()` 不再把空 preset 回退成全局默认。
- `ensure_publish_job()` 遇到规则尚未选择 preset 时返回 `None`，不创建准备任务；保存选择后由常驻对账补建。
- 新增回归断言，禁止 handoff 路径重新使用全局默认 preset。

这项修正已在 Windows 工作副本通过 32 项测试，但用户要求交接时尚未重新构建 NAS API。接手后第一步应确认 Git 中包含该修正，再在安全窗口仅重建 `studio-api`（Web 无需因这项修正重建）。

## 其他主播规则

除芒芒外的旧规则目前没有显式 preset。不要替它们自动选择芒芒模板。建议在页面逐条编辑：

- `小红泡-管珩心` 可由用户确认是否选择 `ign19v4u95a（管珩心）`。
- `赛蒂娅Sentia` 和清歌喵相关规则当前没有明显同名 BililiveTool preset，应由用户先在 BililiveTool 新建或明确选择。

## 验证结果

- 本地 `py_compile backend/app.py backend/publishing.py` 通过。
- `node --check web/automation.js` 通过。
- `python -m unittest test_publishing test_automation`：32 项通过。
- NAS 临时 API 镜像只读挂载源码后运行同一套测试：32 项通过。
- 此前完整后端套件 228 项中 227 项通过；唯一失败为已知无关的 `test_folia_native.FoliaNativeTests.test_tempera_preview_reduces_gpu_cost`（预期 0.5、当前实现 1.0），旧镜像也可复现。
- Compose 配置、API/Web 构建、API/Web 健康检查通过。
- API 重启时正在运行的小红泡整场 ASR 复用了原 transcriber job；转录器、模型与渲染器均未重启。

## 关键文件

- `backend/app.py`：数据库迁移、规则 API、publish job handoff、prepare worker。
- `backend/publishing.py`：BililiveTool client、preset/简介处理、payload 构建。
- `backend/test_publishing.py`：投稿及规则绑定回归测试。
- `web/index.html`、`web/automation.js`：规则表单和 preset 选择。
- `docs/modules/automation-pipeline.md`、`docs/DECISIONS.md`、`docs/STATUS.md`：行为边界和上线记录。

## 建议接手顺序

1. 检查 `ensure_publish_job()` 中“未选 preset 返回 `None`”的最后修正已经进入当前分支。
2. 查询 `/api/automation/queue`，在不会干扰关键阶段的窗口重建 `studio-api`。
3. 验证 `/api/automation/profiles`：芒芒显示 `s9iw1rmff2`，其余旧规则显示未选择。
4. 验证 `/api/publish-presets` 能读取四个真实模板；不要调用 `/api/bili/upload`。
5. 让用户在页面确认其他主播的模板选择。
6. 保持 `AUTO_PUBLISH_ENABLED=0`，Phase 2 未经确认不得开始。

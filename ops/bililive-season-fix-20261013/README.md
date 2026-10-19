# BililiveTool 合集可靠性适配（2026-10-13）

仅针对已检查的生产3.18.0镜像。不要对不同版本直接套用bundle补丁。

- `folia-season-jobs.cjs` 在BililiveTool进程内运行，用它已有的SDK/client/登录态。没有自己的登录、Cookie、上传或投稿实现。
- `patch_bundle.py original patched` 精确替换两个已核对bundle锚点；没有匹配时拒绝。生成文件不进入Git，保留原镜像/备份。
- 只有新Folia请求的 `options.foliaCollectionTracking=true` 启用；已有稿件/未标记请求不排队。用户已经手动补齐旧合集，不做历史补加验收。
- 新队列先按AID查所属合集，再用已有上传CID加入，await后回查。若在其他合集终止不移动；模板小节必须属于目标合集。恢复记录在原Bililive数据卷 `folia-season-jobs/<uid>-<aid>.json`，仅白名单业务值，无凭据。
- 6次累计流程尝试；412暂停60分钟，400/401/403停下人工检查，其他错误2分钟起退避。丢响应先核对；仅合集重试，绝不重传视频或重新生图。损坏记录停下，不覆盖为新请求。
- 这是同一自动投稿流程中的后续步骤，不是已经验证的“同一次B站HTTP请求”原子加入；不等审核通过。未尝试猜测season_id/section_id投稿字段。

只读受原passkey鉴权接口：

```text
GET /api/bili/folia-season/capabilities
GET /api/bili/folia-season/<aid>?uid=<uid>
```

准备及提交前都检查能力。Folia保存独立 `collection_status/error/attempts/next_collection_at`；旧默认NULL。合集查询不受审核计时阻塞，页面单独显示失败/重试而不把上传完成等同整个流程完成。

测试：`node --test test-season-jobs.cjs`，`node test-overlay.cjs patched/index-CWUSa9VA.cjs`，`node test-page.cjs ../../web/publish.js`；Python包含test_publish_v2/test_collection_client及旧投稿回归。所有测试为mock/断网，无额外真实投稿或收费生图请求。下一条自然新投稿仍需验证真实入合集结果。

后续用户明确授权《游园惊梦》旧参数稿件的单步实测，test-existing-yuyuan.py及run-existing-yuyuan-test.py仅对白名单ID/AID/MID/原标题/唯一CID严格核对、备份并加入同一恢复队列。已确认真实joined，原payload/MP4/AID/任务ID/上传次数不变。Folia显式非NULL collection_status可跟踪这条单稿维护，其他旧NULL不受影响。没有新视频上传或收费生图，不是全库补加入口；完整的新上传opt-in回调仍需自然新稿验收。

部署前确认录播机、上传、重任务空闲并做一致性数据库/配置/源码备份。使用固定本地镜像，Bililive根目录 `docker-compose.override.yml` 为镜像固定文件，原compose不变。deploy.sh是本次一次性部署脚本，不是可以跳过检查反复执行的更新器。新增Python运行模块为零，backend/Dockerfile现有显式COPY涵盖修改模块。

回滚用 `rollback.override.yaml` 对应原镜像，恢复API/Web对应镜像/源码，保留数据库与队列恢复文件；不能用旧数据库覆盖新任务ID/AID。ASR、原生渲染器、原录播、MP4和手工合集不动。上游更新须先验证新版本实际协议和锚点，不能直接pull覆盖适配。

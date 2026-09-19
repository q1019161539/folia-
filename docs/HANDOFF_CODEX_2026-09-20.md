# Folia 歌词视频工坊交接（交给 Codex）

日期：2026-09-20　交出方：Claude Code

## 开始前

按顺序完整读：`AGENTS.md`、`docs/STATUS.md`、`docs/README.md`，再读当前相关的
`docs/modules/automation-pipeline.md`、`docs/modules/asr-alignment.md`、`docs/deployment.md`。

- 本地工作副本（git 仓库在这里）：`C:\Users\34862\Documents\飞牛\folia-video-studio`
- 飞牛上的另一份 git 克隆（提交和推送在这里做）：`/vol1/1000/docker/folia-git`
- 飞牛上的部署目录（compose 实际读取的就是它，**不是** git 仓库）：`/vol1/1000/docker/folia-video-studio`
- ASR 数据：`/vol1/1000/docker/folia-asr-mvp`
- 网页：`http://100.111.1.11:18081/`
- API：容器内 `http://127.0.0.1:8000`，宿主机映射 `127.0.0.1:18082`

注意这是三份副本。改完代码要分别落到部署目录（再 `docker compose build` + `up -d`）和
git 克隆（再 commit/push），两边的 `md5sum backend/app.py` 应当一致。

凭据（`.env`、`DEEPSEEK_API_KEY`、`ACRCLOUD_ACCESS_*`、`WECOM_WEBHOOK_URL`、Basic Auth 口令、
SSH 私钥）一律不得写进仓库、文档、日志或提交信息；需要时向用户索取。

## 已完成并部署

五个提交，都已推到 `q1019161539/folia-` 的 main，并且已经在飞牛上跑着。

### `ce42bf3` 自动流程：新录播永远进不了队列

`INSERT INTO automation_runs VALUES(?×16)` 是按位置写的，而表被迁移加到了 17 列，
每次入队都抛异常，又被 `except Exception: pass` 吞掉，所以自动流程从外面看只是"安静地不动"。
改成具名列 `AUTOMATION_RUN_INSERT`（只列业务列，以后再加列也不会崩），`jobs` 同样处理成
`JOB_INSERT`；两个后台循环改用 `automation_loop_error()` 把完整 traceback 打到 stderr。

**这是全场最重要的一条经验：后台循环里不许有裸 `except: pass`。**

### `be47683` 歌曲身份：歌词候选不再有资格改名；行尾改看末字唱完的时刻

- 新增 `backend/song_identity.py`，身份语义只此一处。合法来源只有
  `shazam / acrcloud / deepseek / automation_history_backfill / legacy_fallback`，
  写别的来源直接 `ValueError`。**没有 `manual`，也不会有。**
- 歌词候选的标题不再回写进 job。之前 46 首里有 21 首被歌词候选改过名，
  改完的名字又拿去搜歌词，形成自我强化的污染回路。
- 标题相似度先过 OpenCC `t2s` 归一，繁简不再算作不同的歌。
- 行尾不再无条件截断，改成取该行最后一个唱完的字的 `end_ms`。

### `0ba8871` 逐字证据太稀时，用人声分离重读一遍

`word_timeline.separation_retry_needed()`：只对逐字歌词、字锚点覆盖率
低于 `SEPARATION_RETRY_COVERAGE`（现设 0.10）时触发一次人声分离重跑。

顺带修了一个更要命的问题：`transcriber/web.py` 的 `build_command` 只会追加
`--skip-separation`，而 `main.py` 默认就是跳过——**人声分离从来没真正执行过**。
我之前基于"分离结果更差"下的结论因此全部作废。

### `cbab0e3` 重任务共用一个槽位；标准歌词的时间轴只许平移一次

- 那次整机失联、只能硬断电的根因：`render_lock` 和 `ai_slot` 是两把互不相关的锁，
  渲染和 ASR/分离可以同时吃内存。现在渲染也走 `heavy_ai_slot`，重活共用单槽。
- 标准歌词只做一次整首中位数平移，force-align 遇到 `has_standard_timeline()` 的行
  直接 `preserved += 1; continue`，行内的字也不再改。
- `db()` 重写成真正的 contextmanager（commit/rollback/close，timeout 30s，schema 只建一次）。
  之前泄漏了 66 个 fd，表现为偶发 `database is locked`。
- `HF_HUB_OFFLINE=1`（local-worker 与 transcriber），停掉 transformers 对不存在的
  `custom_generate/generate.py` 的反复重试。
- 一场没检出歌时也发企业微信通知，不再静默。

### `8455590` 听歌识曲改用 ACRCloud

shazamio 走非官方接口，最近成片成片地返回空。ACRCloud 是正式授权接口，
同一首《读心术》1.1 秒命中。现在 `FINGERPRINT_PROVIDER` 默认 `acrcloud`，
设成 `shazam` 可随时切回，两条路径归一到同一身份结构，来源如实记录。

## 验证状态

- backend 单测 148/148，transcriber 单测 19/19。
- 部署目录与容器内 `backend/app.py` md5 均为 `1736446d2e2523721c7a8319f4af7710`，
  与 git 克隆一致；容器 healthy；`FINGERPRINT_PROVIDER = acrcloud` 已生效。
- 队列空闲，`ai_slot` 与 `render_slot` 均空。
- 端到端复核：9 首原本只拿到整句歌词的歌，现在 9/9 都选中了逐字候选
  （7 首靠繁简归一，最后 2 首靠身份修复）。
- 当前库里 118 个 job，`identity_source` 分布：
  空 95、deepseek 10、automation_history_backfill 8、shazam 4、acrcloud 1。

## 接手后优先事项

1. **《恋爱画板》**（job `9b52fc3c`）重新匹配已完成，停在 `alignment_review`。
   这是设计上的人工确认关口，等用户看过再渲染，不要自动推过去。
2. **21 首历史身份污染**。用户明确要求：只能另做一次**自动重新识别/身份恢复任务**，
   不许人去改名字，历史行保持 `legacy_fallback`。现在 ACRCloud 是主指纹，
   重识别的命中率应该比当初高。`IDENTITY_BACKFILL` 默认关着，别盲目打开。
3. **零字锚点的逐字候选仍可能胜出**。选候选时偏好逐字，但没校验它真的贡献了字锚点。
4. **标题装饰压低相似度**：`(片段)`、`(DJ默涵版)`、`《X》插曲` 这类后缀会让相似度失真。
5. **`ROLE_LINE` 漏掉** `Written by：` 和 `音乐项目总监：`，这两种署名行会被当成歌词。
6. **指纹全失败时的兜底想法**（尚未实现）：拿**人声分离后**的 ASR 文本去问 DeepSeek 是哪首歌。
   已验证《不期而遇》两家指纹服务都命中不了，而《读心术》两家都能中——是曲库覆盖问题，不是接口问题。
7. **遗留测试数据待清理**（等用户点头再动）：库里 8 个测试 job，以及
   `Folia成片/_新规则试渲染/逐字优先验证_20260919/`（其中 `读心术/` 下有重复的繁体文件名成品）。

## 操作规矩（这些都是踩出来的）

- **"查"和"动"必须分两步。** 我把"看队列"和"重启 transcriber"写进同一条命令，
  结果打断了正在跑的生产 ASR。重启前先单独确认 `/api/automation/queue` 的
  `active` 和 `queued` 都是空的。
- **backend 新增模块必须加进 `backend/Dockerfile` 的 COPY 列表**（它是逐个文件名列的）。
  漏了 `song_identity.py` 那次，studio-api 重启循环了两分钟。
- **`docker cp 目录 容器:目录` 是嵌套不是覆盖**，先在容器里 `rm -rf` 再拷，
  否则会跑到上一版的陈旧测试。
- 改完代码，部署目录和 git 克隆两边都要更新，`md5sum` 对得上才算完。

## 禁止事项

- 不修改、移动、删除原始录播。
- 切片只许写进 `歌曲切片/`。
- 不删除旧目录或历史成片。
- 不把口令、Webhook、API Key、Basic Auth 写进仓库、文档或日志。
- 不引入 `identity_source=manual`；歌词层永远不能改身份，人工也不参与。
- 不为了让验证好看而手工改歌名。

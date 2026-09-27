# Docker 部署与运维

Web 代理使用 Docker 内置 DNS（`127.0.0.11`）动态解析 `studio-api` 与 `transcriber`。后端服务单独重启并更换容器 IP 时，Nginx 会自动刷新地址，不应要求重启整个项目或清理持久化卷。

## 飞牛路径

```text
/vol1/1000/docker/folia-video-studio
```

## 服务

| 服务 | 作用 | 对外端口 |
| --- | --- | --- |
| `studio-web` | Nginx、Basic Auth、工作台 | `18081` |
| `studio-api` | FastAPI、SQLite、FFmpeg | 仅本机 `18082` |
| `local-worker` | Whisper 与 Qwen CPU 推理 | 无 |
| `transcriber` | 录播 ASR、ForcedAligner、逐句时间戳文件 | 通过 `/transcriber/` |
| `lyrics-service` | LDDC 多源逐字歌词搜索与解析 | 无 |
| `chromium-cdp-proxy` | 动效预览浏览器桥接 | 仅主机 `19222` |

飞牛容器列表使用固定的易读名称：`folia-video-web`、`folia-video-api`、`folia-video-ai`、`folia-video-transcriber`、`folia-video-preview`。这些服务都是单实例，固定名称意味着不能用 `docker compose --scale` 横向扩容。

## 配置

`.env` 至少应提供：

```dotenv
STUDIO_PASSWORD=请使用实际密码
DASHSCOPE_API_KEY=
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
```

不使用阿里云时 `DASHSCOPE_API_KEY` 可留空。本地识别与 Qwen 对齐不依赖它。
自动歌曲分析需要 `DEEPSEEK_API_KEY`；Key 不得写入代码、文档、数据库或日志。

## 常用命令

```bash
cd /vol1/1000/docker/folia-video-studio
docker compose ps
docker compose up -d
docker compose logs --tail=200 studio-api
docker compose logs --tail=200 local-worker
docker compose logs --tail=200 studio-web
docker compose logs --tail=200 transcriber
docker compose logs --tail=200 lyrics-service
```

健康检查：

```bash
curl -fsS http://127.0.0.1:18082/healthz
docker compose exec local-worker curl -fsS http://127.0.0.1:8001/healthz
docker compose exec transcriber python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/api/config').status)"
docker compose exec lyrics-service curl -fsS http://127.0.0.1:8090/healthz
```

## 更新步骤

1. 在本机副本修改并完成语法检查。
2. 只同步本次改动的文件到飞牛项目目录。
3. 只重建受影响服务。
4. 等待健康状态，不要在容器尚未 healthy 时判断页面失败。
5. 做一个小样本真实验证。
6. 把结果写回 `docs/STATUS.md`。

## 数据保护

- 重建容器不会删除 `data/`、`models/`、`work/` 或媒体挂载。
- 转录服务复用 `/vol1/1000/docker/folia-asr-mvp` 下既有的 `.env`、`models/`、`work/`、`output/`；不要删除旧目录或执行带 `-v` 的清理命令。
- 不执行 `docker compose down -v`，除非用户明确要求删除持久化数据。
- 清理 `work/` 前先确认没有 `recognizing`、`force_aligning`、`rendering` 或切片任务。
- 备份时至少保存 `.env`、`data/studio.db` 和本项目代码；模型缓存可重新下载，但体积大，保留可节省时间。


## 2026-09-26：视频保存到第二块硬盘

应用、数据库、字体、图片库、模型、ASR 工作目录仍保留在 `/vol1`。只调整媒体文件：

- 今后的录播、下载与歌曲切片：`/vol2/1000/video/Folia录播`。
- 今后的成片与样片：`/vol2/1000/video/Folia成片`。
- 旧录播：`/vol1/1000/docker/bililive-tool/video`，不搬迁。
- 旧成片：`/vol1/1000/video/Folia成片`，不搬迁。

`folia-media-view.service` 使用官方 mergerfs v2.42.0 静态程序 `/usr/local/bin/folia-mergerfs`，将新录播目录（RW）与旧目录（RO）合并到应用目录的 `media-view`。同一相对路径优先读取新盘，创建文件只进入新盘；不提供旧文件的写时复制。服务在 Docker 启动前建立挂载，依赖 `/vol1`、`/vol2` 的挂载。录播工具仍使用 `/app/video`，因此房间身份历史、目录别名及工坊原项目 source ID 不变。

工坊 `/media-output` 直接绑定新录播目录；历史切片下载缺失时回读统一媒体视图，生成切片时也检查历史同名文件以防遮盖旧项目。API 与原生渲染器 `/output` 绑定新成片目录；旧成片只读挂在 `/output-legacy`，历史输出接口优先新路径、缺失时回读旧成片。录播工具的历史成片入口为 `/app/历史Folia成片`。

投稿准备另外将 `./cover_templates` 只读挂载到 `/cover-templates`，封面写入 `/output/publish/covers`。BililiveTool 已将新成片挂载为 `/app/Folia成片:ro`、旧成片挂载为 `/app/历史Folia成片:ro`，不复制 MP4。`BILILIVETOOL_PASSKEY` 只能放在部署 `.env`；Phase 1 保持 `PUBLISH_ENABLED=1` 与 `AUTO_PUBLISH_ENABLED=0`。`cover_templates/generic/placeholder-*` 只用于联调，自动真实投稿前必须替换为正式授权素材。

配置、代码与 SQLite 一致性备份：`/vol1/1000/docker/folia-video-studio-backups/20260926-vol2-video-paths/`。回退时恢复两份 Compose 和 `app.py` 并重建对应服务，勿删除第二块硬盘已经生成的视频。切换录播工具前必须正常停止录制并等待转封装任务完成，再恢复原正在录制的房间。

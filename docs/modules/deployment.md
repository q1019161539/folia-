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
| `folia-renderer` | 固定上游 Folia、透明/快速原生成片 | 仅本机 `18091`（候选）/ 容器 `8091` |
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

Folia 上游升级额外遵守：只跟踪稳定 Release；将 Release、提交、Stack、amd64 digest、13 个模式和补丁版本写入 `folia-version.json`；从固定提交源码构建；先在独立端口和独立输出目录运行候选容器；队列为空后才切换正式服务。`data/fonts` 与数据库一起备份，渲染器对字体目录保持只读挂载。

## 数据保护

- 重建容器不会删除 `data/`、`models/`、`work/` 或媒体挂载。
- 转录服务复用 `/vol1/1000/docker/folia-asr-mvp` 下既有的 `.env`、`models/`、`work/`、`output/`；不要删除旧目录或执行带 `-v` 的清理命令。
- 不执行 `docker compose down -v`，除非用户明确要求删除持久化数据。
- 清理 `work/` 前先确认没有 `recognizing`、`force_aligning`、`rendering` 或切片任务。
- 备份时至少保存 `.env`、`data/studio.db` 和本项目代码；模型缓存可重新下载，但体积大，保留可节省时间。

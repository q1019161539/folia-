# 架构说明

## 服务

```text
浏览器 :18081
    │
    ▼
studio-web (Nginx + Basic Auth)
    ├── /api、/effects → studio-api (FastAPI :8000)
    └── /transcriber/ → transcriber (Flask :8080)
                          └── 选择录播 → ASR → ForcedAligner → 逐句时间戳

studio-api
    ├── SQLite /data/studio.db
    ├── FFmpeg：提取、切片、渲染
    ├── local-worker :8001
    │      ├── Faster-Whisper CPU/int8
    │      └── Qwen3-ForcedAligner-0.6B CPU/float32
    ├── lyrics-service :8090
    │      └── LDDC：QQ/酷狗/网易云/LRCLIB 逐字歌词
    └── folia 外部网络：音乐平台网关
    └── 自动流水线：主播目录监听 → transcriber → DeepSeek → 切片 → 逐首 Qwen/渲染
```

## 目录职责

| 路径 | 用途 | 是否持久化 |
| --- | --- | --- |
| `backend/app.py` | 主 API、项目状态、切片、渲染 | 代码 |
| `backend/worker.py` | 本地 ASR 与 Qwen 对齐 | 代码 |
| `web/` | 工作台页面和控制逻辑 | 代码 |
| `effects/src/` | 歌词效果运行时 | 代码 |
| `nginx/` | Web 镜像、认证和反向代理 | 代码 |
| `transcriber/` | 录播转录、ASR、ForcedAligner 与逐句时间戳页面 | 代码 |
| `data/` | SQLite 项目与任务状态 | 是 |
| `models/` | Whisper/Hugging Face 模型缓存 | 是 |
| `work/` | 临时音频与处理中间文件 | 可清理，但任务运行时不要动 |
| `experiments/` | 上游参考项目，不参与线上运行 | 参考 |

## 挂载与写入边界

- `/media/bililive`：bililive-tools 录播，只读。
- `/media-output`：同一录播根目录，可写；后端只允许写入源视频相对目录的 `歌曲切片/`。
- `/output`：Folia 成片目录。
- `/models`：模型缓存，容器重建后继续复用。
- 转录服务继续挂载原 `/vol1/1000/docker/folia-asr-mvp/{models,work,output}`，合并只迁代码和入口，不迁移数据。
- 转录任务使用 `/work/jobs/<job_id>` 与 `/output/jobs/<job_id>` 隔离；录播挂载始终只读。

## 主数据流

```text
录播 → FFmpeg 音频 → ASR 片段 → Qwen 现场逐字文件
     → LDDC 多源标准逐字歌词 → 单调匹配与整体平移
     → Qwen 匹配字 + LDDC 漏字融合
     → 透明预览 → FFmpeg/ASS 成片
```

切片工作流与 ASR 独立：

```text
时间轴文本 + 原录播 → 解析/编辑 → FFmpeg -c copy → 歌曲切片/
```

自动流水线复用两条既有数据流：整场录播只在 transcriber 中执行一次 ASR；后端把歌曲范围内的逐句结果换算到切片相对时间，再送入标准歌词整体平移与逐字渲染。多个主播可以同时监听，但所有重任务严格串行。

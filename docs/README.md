# 文档索引

新对话固定先读：

1. 根目录 `AGENTS.md`：协作边界和安全规则。
2. `docs/STATUS.md`：线上现状、最近验证和待办。
3. 只读本次任务对应的模块文档。

| 任务类型 | 应读取文档 | 主要代码 |
| --- | --- | --- |
| ASR、漏字、Qwen、时间戳、进度 | `modules/asr-alignment.md` | `backend/worker.py`、`backend/app.py`、`web/app.js` |
| LDDC、多平台搜索、标准逐字歌词 | `modules/lyrics-sources.md` | `lyrics-service/`、`backend/word_timeline.py` |
| 歌词特效、透明叠加、预览、成片 | `modules/lyrics-preview-render.md` | `effects/src/`、`web/`、`backend/app.py` |
| 时间轴文档、批量切歌、中止 | `modules/batch-clips.md` | `web/clips.js`、`backend/app.py` |
| 主播监听、自动判歌、整套自动出片 | `modules/automation-pipeline.md` | `web/automation.js`、`backend/automation.py`、`backend/app.py` |
| 投稿管理：主播模板、封面底图、封面字体、字体库 | `modules/automation-pipeline.md`（投稿管理页） | `web/publish.js`、`backend/publishing.py`、`backend/app.py` |
| Docker、端口、挂载、升级、故障 | `modules/deployment.md` | `compose.yaml`、`backend/*file`、`nginx/` |
| 服务关系、数据流、目录用途 | `ARCHITECTURE.md` | 全局 |
| 为什么这样设计 | `DECISIONS.md` | 全局 |

`experiments/` 保存 AMLL、lyrics-studio 等上游参考代码。只有在比较或移植上游效果时才读取，日常故障排查不要扫描它。

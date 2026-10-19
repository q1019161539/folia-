# Folia 歌词视频工坊

部署在飞牛 fnOS 上的 CPU-only 录播处理工具，提供手动制作、批量切歌、转录工作台、自动流水线和独立投稿阶段：

- 录播音频识别、标准歌词校对与逐字对齐。
- 原视频透明歌词预览及带歌词成片渲染。
- 根据歌单时间轴批量无损切歌。
- 按主播自动监听录播，整场转录、判歌、切片、标准歌词匹配和出片。
- 高置信成片按主播/歌曲去重，本地选帧或使用有授权的人物参考图，通过 API 生成完整封面及可选 AI 标题。
- 继承主播 BililiveTool preset，校验、创建上传任务并跟踪 AID/BVID、审核及合集状态；上传失败不改变原成片。
- SQLite WAL、持久化尝试次数和结果检查点，支持恢复与有限重试。历史已接受任务不自动重投。

## 分享与部署边界

这是 2026-10-19 NAS 已用源码的同步版，不是通用安装包。**Windows 双击免安装版尚未实现**，当前仍需 Linux/NAS Docker 环境；不要把此仓库当作已经完成的 Windows 移植。

- 先复制 `.env.example` 为 `.env`，自行填写密码、服务地址和密钥。分享版自动投稿默认关闭，且没有默认投稿账号或模板。
- `compose.yaml` 仍包含原部署的 `/vol1`、`/vol2` 媒体路径、`/dev/dri`、外部网络及 `../folia-asr-mvp/.env`，换机器必须按 [部署文档](docs/modules/deployment.md) 调整，不能原样运行。
- 不包含数据库、录播、成片、模型权重、人物参考图、字体库、登录状态或运行时密钥；须自行准备有使用权的素材及模型缓存。无 GPU 时需移除/调整 `/dev/dri` 相关配置，本地模型支持 CPU。
- AI 标题、判歌和封面可能收费，请自行核对服务商、模型兼容协议、额度与网络。自动化开关不能替代费用上限控制。
- 只有主播模板、共享文件映射、置信度、响度筛查等均符合条件的成片才能投稿；BililiveTool 及合集补丁的要求见 [自动投稿文档](docs/modules/automatic-publishing.md)。
- `ops/` 含一次性修复/发布工具，部分有固定历史 ID，不是通用启动入口，不要在自己的账号上直接执行。
- 安全扫描范围、结果和密钥处理方式见 [安全说明](SECURITY.md)。仓库目前无项目级 LICENSE；分享代码不代表已补齐各上游及素材的再分发授权。

## 当前入口

- 页面：`http://<飞牛地址>:18081/`
- 飞牛项目：`/vol1/1000/docker/folia-video-studio`
- 本机源码目录：克隆仓库时选择的目录（不包含运行数据）。
- 新录播/切片目录：`/vol2/1000/video/Folia录播`；旧录播通过 `media-view` 合并只读访问。
- 新成片目录：`/vol2/1000/video/Folia成片`；旧成片仍在第一块盘并兼容读取。

页面使用 Basic Auth，密码由 `.env` 中的 `STUDIO_PASSWORD` 提供。不要把真实密码写进文档。

## 快速操作

在飞牛项目目录执行：

```bash
docker compose ps
docker compose up -d
docker compose logs -f --tail=100 studio-api local-worker studio-web
```

修改代码后按影响范围重建：

```bash
# 只改网页
docker compose build studio-web && docker compose up -d studio-web

# 只改主 API
docker compose build studio-api && docker compose up -d studio-api

# 改了识别模型、依赖或 worker.py
docker compose build local-worker && docker compose up -d local-worker
```

## 文档导航

先看 [当前状态](docs/STATUS.md)，再从 [文档索引](docs/README.md) 进入对应模块。服务与数据流见 [架构说明](docs/ARCHITECTURE.md)，接手维护见 [代码地图](docs/CODE_MAP.md)。线上源码与 NAS Git 副本需显式同步，不能把本机旧副本直接覆盖到线上。

## 给新对话的开场话术

复制下面这段即可，不需要粘贴旧聊天：

```text
请继续维护 Folia 歌词视频工坊。项目目录是 C:\Users\34862\Documents\飞牛\folia-video-studio，飞牛部署目录是 /vol1/1000/docker/folia-video-studio。先完整阅读 AGENTS.md 和 docs/STATUS.md，再根据 docs/README.md 只读取与本次任务有关的模块文档。先检查当前状态，不要重做已完成工作，也不要修改原录播。我的本次需求是：<在这里写需求>。
```

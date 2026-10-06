# Folia 歌词视频工坊

部署在飞牛 fnOS 上的 CPU-only 录播处理工具，提供手动制作、批量切歌、转录工作台、自动流水线和投稿准备：

- 录播音频识别、标准歌词校对与逐字对齐。
- 原视频透明歌词预览及带歌词成片渲染。
- 根据歌单时间轴批量无损切歌。
- 按主播自动监听录播，整场转录、判歌、切片、标准歌词匹配和出片。
- 按主播配置 BililiveTool preset、封面底图和字体，准备并校验投稿参数；当前不自动上传。

## 当前入口

- 页面：`http://<飞牛地址>:18081/`
- 飞牛项目：`/vol1/1000/docker/folia-video-studio`
- 本机项目副本：`C:\Users\34862\Documents\飞牛\folia-video-studio`
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

# Folia 项目协作约定

1. 使用简体中文交流，所有文本文件使用 UTF-8（无 BOM）。
2. 开始工作时先读 `docs/STATUS.md`，再根据任务查 `docs/README.md` 中对应模块；不要默认遍历 `experiments/`、`models/`、`data/`、`work/` 或 `node_modules/`。
3. 主项目是本目录，飞牛部署目录是 `/vol1/1000/docker/folia-video-studio`，页面端口是 `18081`。
4. 保留 CPU-only 支持，不引入 CUDA 或付费服务作为必需依赖。
5. 不修改、移动或删除 bililive-tools 原录播；切片只能写入原视频相对目录下的 `歌曲切片/`。
6. 修改前确认现有状态，保留用户已有改动。修改后至少执行与模块对应的语法检查和健康检查，结果写回 `docs/STATUS.md`。
7. 密码、API Key 和令牌只放 `.env` 或飞牛环境变量，不写入代码、文档、日志或提交记录。
8. `experiments/` 是上游项目参考副本，不是线上入口；除非任务明确涉及上游比对，否则不要修改。
9. 新增功能时同步更新相应模块文档；重要取舍记录到 `docs/DECISIONS.md`，不要依赖聊天记录保存项目知识。


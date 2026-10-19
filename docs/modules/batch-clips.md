# 歌单批量切片

## 入口

- 页面：`web/clips.js`、`web/clips.css`
- API 和任务执行：`backend/app.py` 中 `parse_song_timeline`、`clip_batch_task`
- SQLite：`clip_batches` 表

## 功能

- 从 bililive-tools 目录选择录播。
- 粘贴时间轴文本并解析正式歌曲与疑似片段。
- 执行前编辑歌名、起止时间、余量和是否包含。
- 默认前后各保留 5 秒。
- 逐个用 FFmpeg 流复制，避免同时读取大文件。
- 输出到原视频同级 `歌曲切片/`。
- 文件名过滤非法字符，重名追加编号，不覆盖旧文件。
- 支持中止；已完成文件保留，当前临时文件清理。

## API

- `POST /api/clips/parse`
- `POST /api/clip-batches`
- `GET /api/clip-batches/{id}`
- `POST /api/clip-batches/{id}/cancel`
- `GET /api/clip-batches/{id}/files/{index}`

## 修改后的最低验证

先切一个约 20 秒片段：

1. 确认原视频未变。
2. 确认输出只在正确的 `歌曲切片/`。
3. 用 `ffprobe` 检查 H.264/AAC、时长和可播放性。
4. 检查重名不会覆盖。
5. 检查中止后临时文件已清理。

流复制受关键帧影响，轻微起点偏差属于当前模式限制。

## 最近验证

- 2026-10-19：用户授权制作小红泡“温柔教练”反差精剪，独立脚本见ops/contrast-20261019/README.md。14镜头/115.084秒/1080p30，ASS字幕、阶段提示、字数递减、轻微震动和回放，最终全片解码通过；三个原录播size+mtime_ns不变。所有媒体制品仅写入原录播同级歌曲切片下的专属子目录，不注册自动成片或投稿任务。字幕来自既有ASR，不声称完成逐句人工听校或自动说话人识别。

- 2026-09-10：从 90 分钟录播的逐句转录中筛选 13 段明确演唱，时间轴见 `docs/artifacts/08-21-03-song-timeline.txt`。
- 批次 `c162a79b7660429e8232d0682e4ba178` 完成 13/13、失败 0；余量为前后各 2 秒。
- 13 个输出均经 `ffprobe` 确认为 H.264 + AAC；原录播切片前后 SHA-256 一致。

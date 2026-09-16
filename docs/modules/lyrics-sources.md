# LDDC 多源逐字歌词

## 服务边界

- `lyrics-service/` 是独立的 GPL-3.0-only 服务，固定使用 LDDC 提交 `84631e8cd011fcc3f71ca0ae017e2c9758958ffc`。
- 服务只在 Compose 的 `studio` 内网暴露 `8090`，主 API 通过 `LYRICS_SERVICE_URL` 调用。
- 支持 QQ 音乐、酷狗、网易云和 LRCLIB；每次查询每个来源最多保留 3 个候选。
- LDDC 缓存位于 `data/lddc/`。镜像内 `/licenses/LDDC-GPL-3.0.txt` 保存上游许可证。
- LDDC 服务整体不可用时，主 API 才回退旧网易云接口；单个来源失败不会阻塞其他来源。

## 逐字数据

候选统一返回逐行正文、行起止和字词起止。`timing_type` 为 `verbatim`、`line`、`plain` 或 `unknown`，`word_coverage` 表示有效逐字时间对正文的覆盖率。

标准时间轴选择仍以 ASR 文字与顺序为主。逐字版本会进一步比较 Qwen 现场字时间与平台字时间：至少 15 个精确字锚点、3 行、10 秒跨度且 P90 残差不超过 800ms，才与既有句级高置信共同构成逐字高置信。候选最终选择以高置信优先，避免总分略高的 Live/DJ/改编版覆盖残差更小的原版；制作名单、版权提示、平台广告和标题横幅会在评分前移除。

最终每字时间优先级为 Qwen 精确匹配、相邻锚点内的一对一纠错、LDDC 标准时间、行内插值。所有时间必须位于整体平移后的固定标准行边界；不对两套时间做平均。

## 接口

- 歌词服务：`POST /v1/search`、`POST /v1/lyrics`、`GET /healthz`。
- 主 API：原 `POST /api/jobs/{id}/search-songs` 返回多源候选；`POST /api/lyrics/resolve` 根据不透明 `candidate_ref` 读取歌词。
- 旧 `GET /api/lyrics/netease/{song_id}` 保留兼容。

修改后至少运行歌词服务健康检查、四来源搜索小样本、后端匹配单测和一个现有 ASR 任务副本验证。

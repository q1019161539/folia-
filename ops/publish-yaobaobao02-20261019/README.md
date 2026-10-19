# 指定上传小红泡2026-10-19《要抱抱》第二遍

用户取消合唱制作，明确要求上传当天`要抱抱_02`。这是单首显式授权，不更改自动去重、投稿水位或其他歌曲范围。

- 工坊项目：3d18a332b1ed4dd6b0b42e7687242a72，高置信完整成片，202871135字节。
- 新投稿：78cdc33b66245535a54bf8738175521b；Bililive任务c189e348-c08d-4334-868e-9f3a1a2276b6；AID117467137443746；BV12HnJ6HEN3。
- 实际上传完成，合集9133790已joined，初查审核中。稿件详情接口HTTP500；经创作中心列表核对MID/AID/完整标题取得BVID，查询异常不重新提交。
- 17日同名旧稿BV1hhJv6qE8q在本地记录为已删除，创作中心172条没有同名稿。今天两遍原被song_key去重；只将第二遍显式放行，第一遍仍重复隔离。
- 复用同歌成功封面及已有AI标题，新简介按本主播preset/formatDesc展开为2026.10.19，保留合集和其他策略字段。新行身份来自第二遍权威identified_*，歌手为空，不沿用旧稿“璟年”或候选“艾辰”补写。没有AI请求，封面次数保持1。

`once.py`通过线上既有Bililive客户端创建上传任务，不实现B站上传协议。prepare时先保存payload到DB，再校验；单首新任务先pipeline_version=1隔离普通worker，提交前持久化次数，仅一次POST。返回taskId先落专用accepted.json，再原子保存DB/交接歌曲主关联及pipeline_version=2，之后仅正常跟踪。旧任务的AID/BVID/taskId、原视频／身份／标题／简介／payload不清空；只解除唯一主关联，旧记录留作历史。

实际首次已被Bililive接受后，通用checkpoint因新任务尚未关联song_project_id抛错；专用accepted.json已保存任务ID。核对该任务已completed取得AID后，修正交接顺序、从receipt恢复DB，未第二次POST。后续已知ID或receipt一律只恢复/查询，submitting无receipt禁止自动重发；不把此脚本当通用重复投稿功能。

备份：`/data/publish-template-backups/yaobaobao02-20261019/`，含一致性SQLite（integrity_check=ok）、原行、共享路径核验、payload、accepted和结果验证；不入Git。视频/封面与Bililive容器实际共享路径size/mtime_ns相同，原文件未变化。4项断网定向测试和Python语法检查；生产healthz正常，无服务重启／ASR中断或自动开关变更。不提交推送GitHub。

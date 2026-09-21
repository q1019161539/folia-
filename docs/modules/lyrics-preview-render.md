# 歌词预览与成片

## 入口

- 页面结构与基础样式：`web/index.html`、`web/style.css`、`web/effects.css`
- 页面控制：`web/app.js`
- Folia 固定源码与补丁：`folia-renderer/Dockerfile`、`folia-renderer/patch_upstream_source.py`
- 服务转发：`nginx/default.conf`
- ASS/FFmpeg 渲染：`backend/app.py` 中 `ass_karaoke`、`render_task`
- Folia 原生配置转换：`backend/folia_native.py`
- Folia 原生浏览器渲染：`folia-renderer/app.py`，固定使用 `v0.7.7` / revision `80c073490482303d4283d1d5205be7707c96179d` / Stack `1.0.26`
- 字体资产：`backend/font_assets.py`、`data/fonts/`

## 两种概念

- 覆盖模式：原视频作为背景，Folia 只绘制透明歌词层。
- PV/特效：效果运行时可改变歌词布局与动画，但不应擅自用白底或固定背景遮住原视频。

网页透明不等于视频文件带 Alpha。旧效果仍把歌词烧录进原视频；选择“Folia 原生”后还需选择输出方式：默认快速方式直接生成叠回原视频并保留原音频的 H.264 MP4；透明方式才会同时生成带 Alpha 的无声 ProRes 4444 MOV 与 H.264 MP4。

## Folia 原生引擎

- 效果页只保留“直播清晰 classic”和“Folia 原生”。原生引擎直接从固定上游提交构建并保留全部 13 个 visualizer：Sonnet、Tempera、Luminous、Mindscape、Partita、Fume、Tilt、Claddagh、Monet、Pendolo、Cappella、Diorama、Still。
- 旧 Folia、AMLL 和 Kinetic 效果不再构建或提供入口。历史项目的旧效果值保持不变，但加载和重渲染时自动回退 classic，并显示一次兼容提示。
- 原生引擎仅强制 `background.transparent=true`。不得删除全局 CSS `background`、Canvas、PixiJS 或 Three.js 层，因为文字渐变、描边、阴影、发光、粒子和动画可能位于这些层中。
- 预览由同源 iframe `/folia-native/obs` 承载。工坊把当前歌词时间、播放器时钟和 WebAudio 频谱送入原版 OBS SSE 协议。
- 预览时钟只能允许一个 HTTP 请求在途；浏览器卡顿或网络变慢时丢弃待发的旧样本、只保留最新播放器位置。`sentAtMs` 必须使用浏览器采样时刻并传到同一浏览器里的 Folia，让原版时钟插值补偿 HTTP/SSE 延迟，不能在 NAS 收包时覆盖。
- iframe 视频桥正常播放时优先复用主播放器 `captureStream()`；媒体到达结尾后若用户 seek 或重播，必须切换为同源静音视频镜像并校准播放器时间，不能继续使用已经停止产出帧的结束流。原生水平/垂直位置默认均为 50%，界面提供一键重置到该中心值。
- 两种导出都以 44.1 kHz、FFT 2048、平滑系数 0.6 分析原音频，频段和指数增益与固定 Folia revision 一致。快速方式在 Xvfb 1920×1080 画布中同步播放原视频并实时驱动同一 visualizer，由 FFmpeg `x11grab` 直接录制 H.264/AAC；不产生 Alpha 中间片，耗时目标接近片长，另加 Chromium 冷启动和 MP4 封装时间。透明方式继续逐帧驱动 OBS，先编码无声 ProRes 4444 Alpha，再叠加到原视频。
- 两种方式均固定 1920×1080、30 fps。透明方式的 MOV 永久保留且不含音轨；快速方式只输出 MP4。完整成片仍按有效歌词首尾各 5 秒裁切，15 秒样片从播放器当前位置开始。
- 工坊提供 Folia 原生水平/垂直位置控制，预览和离线渲染使用同一参数。Tempera 是特殊情况：它原本在 Canvas 内部自行画满屏色块并对文字动态反色；透明覆盖模式会隐藏这些不透明色块、元数据片头卡以及会短暂铺满画布的 paper transition，并关闭依赖底图的反色，保留文字、阴影、装饰、逐字动画和镜头运动，让“文字主色”直接决定 glyph 颜色。
- 为降低工作台预览卡顿，Tempera 预览固定使用 0.5 纹理分辨率且关闭全屏后处理。快速成片同样使用该实时性能配置，否则 NAS 软件渲染只能约 5 个不同帧/秒；透明 MOV + MP4 的精确逐帧方式仍使用保存的其余原生质量参数。
- 原生统一描边配置为 `text_outline.enabled/width_px/color/scope`，默认开启、黑色、3px、`scope=primary`。DOM 使用 `-webkit-text-stroke`，Canvas 在 fill 前 `strokeText`，Pixi/Sonnet/Tempera 使用 TextStyle stroke，Diorama 在 Three.js 文字纹理光栅化时描边并扩充留白。只命中主歌词和逐字高亮，不改歌名、歌手、翻译、和声、装饰字与背景排版。
- Tempera 原先的固定黑边已并入统一开关；关闭时恢复上游原生阴影，开启时只使用统一描边，不能叠两套黑边。描边和字体参数必须进入布局与纹理缓存键，调整后立即重建文字资源。
- 原生字体支持内置黑体、宋体、等宽、原版 fontWeight 及 TTF/OTF/WOFF2 上传。上传上限 20MB，校验字体结构和字体族名，按 SHA-256 去重保存在 `data/fonts`。预览和两种成片均等待 `document.fonts.ready`；加载失败明确提示并回退内置黑体。
- 原生渲染严格串行，接口在入队前取得全局锁；重复点击或已有任务时返回 409。临时文件使用 `.partial`，中止或失败不会替换已完成文件。仅透明方式按 3 GB/分钟预估中间片并检查可用空间。
- 每次 Chromium 渲染必须使用独立临时 user-data-dir 和动态空闲 DevTools 端口，不能复用容器默认 profile；容器以 `tini` 回收浏览器与 Xvfb 子进程。退出路径在强制 kill 后仍需 wait，并删除临时 profile，避免 `SingletonLock`、端口占用和僵尸进程阻断下一次任务。
- 快速输出：`<原名>_folia_<mode>_fast.mp4` 与 `<原名>_folia_<mode>.fast.render.json`。透明输出：`<原名>_folia_<mode>_alpha.mov`、`<原名>_folia_<mode>.mp4`、`<原名>_folia_<mode>.render.json`。

## 数据

时间轴行保存在 `alignment.lines`。存在 `words` 且 `timing_precision=forced-character` 时可以真正逐字驱动；其来源可能是逐句 Qwen，也可能是整场 Qwen 与 LDDC 标准逐字融合，后者由 `word_timing_source=qwen-lddc-hybrid` 标识。`corrected-character` 可用于 ASR 纠错预览，但页面仍显示“未逐字”；标准时间轴的 `standard-line` / `estimated-line` 使用固定行边界，逐字失败时在行内均匀分配效果。

## 逐字表现

- Folia 原生字幕使用 `words[].start_ms/end_ms` 驱动上游各 visualizer 的逐字动画；classic 继续生成 ASS `\\kf` karaoke。
- 旧项目或未逐字行保留整句均匀近似进度，不伪装成强制逐字成功。
- 成片中所有效果都生成 ASS `\\kf` karaoke；强制逐字行使用真实单字时间，其他行才按整句时长均分。
- 每首歌的样片、完整成片、LRC、ASS 对齐数据和渲染清单都写入 `Folia成片/<主播>/<日期>/<高置信或低置信>/<歌名>/` 独立目录；文件名使用录播/歌曲名，不再追加 `_低置信`。歌名经过文件名安全化，避免不同歌曲在同一天互相覆盖或混放。
- 标准歌词替换或补回的字符在时间轴编辑界面固定显示黄色，并可查看 ASR 原字。该颜色是编辑标记，不属于歌词样式；原生与 ASS 成片均不会出现纠错黄。
- 已验收的标准时间轴行即使没有 ASR `segment_ids` 也允许进入预览、LRC、ASS 与成片；这只适用于带 `alignment.timeline_match` 的新模式，旧项目继续执行原有证据门槛。
- 低置信标准时间轴会把 `_低置信` 统一加入 MP4、LRC、对齐 JSON 和渲染清单文件名；渲染清单同时保存完整 `timeline_match`，避免人工验收时丢失版本和偏移依据。

## 时间轴边界规则

- 完整成片先按原流程完成字幕烧录，再对成品 MP4 使用 FFmpeg `-c copy` 直接裁切：从第一条有效歌词前 5 秒开始，到最后一条有效歌词后 5 秒结束。某一侧空白不足 5 秒时该侧不切，不补黑帧或静音；LRC 时间减去裁切起点，第一句仍在成片内的正确时间出现。直接复制 H.264 时保留解码所需关键帧为 MP4 隐藏预卷，不能用 `-avoid_negative_ts make_zero` 把预卷变成可见画面。15 秒样片继续使用用户选择的样片起点。
- LRC 中的作词、乐器、录音师等署名不会作为有效歌词参与首尾裁切，也不会写入成片字幕和配套 LRC。
- `fit_forced_words` 对漏词、多词和标点只在相邻可靠字符之间插值，不把整句未匹配字符按搜索窗口做全局线性铺开，避免后续字幕提前出现。
- `forced-character` 行的可见起止时间以首字 `start_ms` 和末字 `end_ms` 为准；ASS 事件不得回退到旧的 ASR 粗粒度行边界。
- 标准时间轴行例外：LRC 行起止是不可移动的固定边界，Qwen 字时间只能在边界内细化；Qwen 成功或失败都不得改变整行边界。
- 生成 ASS 前应保持单字时间单调、持续时间至少 1 ms，并由相邻字符的起点截断前一字符，防止字符重叠。

## 修改后的最低验证

1. `node --check web/app.js`。
2. 在干净的固定上游提交上执行源码补丁，并完成 Folia TypeScript/Vite 构建。
3. 重建 `studio-web`。
4. 在覆盖模式确认原视频可见、页面没有白底，并分别检查逐字行与未逐字行的动画。
5. 至少检查 classic 和一个 Folia 原生模式的短样片，用 `ffprobe` 检查视频流、音频流和时长。
6. 修改 Folia 原生链路时额外检查：13 个模式均可建立预览；快速样片为 1920×1080、30 fps、H.264 + AAC，画面含原视频与动态 visualizer；透明方式的 MOV 只有 ProRes Alpha 视频流且没有音频流，叠黑/叠白都没有实色画布背景；其 MP4 为 H.264 并含源音频。

新增预设前优先提升已有效果的可调参数、逐字反馈和可读性，不要仅增加相似预设数量。

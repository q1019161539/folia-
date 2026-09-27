# 歌词预览与成片

## 入口

- 页面结构与基础样式：`web/index.html`、`web/style.css`、`web/effects.css`
- 页面控制：`web/app.js`
- Folia 固定源码与补丁：`folia-renderer/Dockerfile`、`folia-renderer/patch_upstream_source.py`
- 服务转发：`nginx/default.conf`
- ASS/FFmpeg 渲染：`backend/app.py` 中 `ass_karaoke`、`render_task`
- Folia 原生配置转换：`backend/folia_native.py`
- Folia 原生浏览器渲染：`folia-renderer/app.py`，固定使用 `v0.7.8` / revision `9cf822015328e47ee5e22061213010a70b4ec5c9` / Stack `1.0.27`
- 字体资产：`backend/font_assets.py`、`data/fonts/`
- Tempera 图片资产：`backend/image_assets.py`、`data/images/`、`web/folia-images.js`

## 歌词制作界面

- 制作页将视频预览、歌曲与自动匹配、歌词时间轴分成独立卡片。歌词列表随页面滚动，不再嵌套固定高度滚动区。窄屏时预览取消吸顶。
- 制作页只提供自动匹配标准时间轴；候选手选、标准歌词大文本框、旧方式采用、ASR 精修和单独的 Qwen 逐字任务不再显示。自动匹配内部的 ASR 与逐字分析仍保留，自动流水线不受影响。
- ASR 草稿行不作为最终歌词编辑区。自动匹配完成后，用户可修改有效时间轴行的歌词正文、起止时间和启用状态；改字或改时间时清除旧逐字数据，保留逐句时间。保存时校验时间，并从有效行同步项目 `lyrics` 正文；预览、样片、完整成片读取同一 `alignment.lines`。
- 歌名和歌手可由用户手动修正，`manual_title`、`manual_artist` 优先供后续标准歌词搜索使用；自动识别结果继续留在 `identified_*` 字段。显式人工修正后的歌名不会被后续指纹识别覆盖。制作页重新自动匹配已有时间轴前要求确认。

## 两种概念

- 覆盖模式：原视频作为背景，Folia 只绘制透明歌词层。
- PV/特效：效果运行时可改变歌词布局与动画，但不应擅自用白底或固定背景遮住原视频。

网页透明不等于视频文件带 Alpha。旧效果仍把歌词烧录进原视频；选择“Folia 原生”后还需选择输出方式：默认快速方式实时录制画布并输出 H.264 MP4；流畅方式逐帧等待浏览器绘制后直接把透明画面叠到原视频，输出 H.264 MP4；透明方式才会同时生成带 Alpha 的无声 ProRes 4444 MOV 与 H.264 MP4。三种方式均保留原视频画面和原音频。

## Folia 原生引擎

- 效果页只保留“直播清晰 classic”和“Folia 原生”。原生引擎直接从固定上游提交构建并保留全部 13 个 visualizer：Sonnet、Tempera、Luminous、Mindscape、Partita、Fume、Tilt、Claddagh、Monet、Pendolo、Cappella、Diorama、Still。
- 旧 Folia、AMLL 和 Kinetic 效果不再构建或提供入口。历史项目的旧效果值保持不变，但加载和重渲染时自动回退 classic，并显示一次兼容提示。
- 原生引擎仅强制 `background.transparent=true`。不得删除全局 CSS `background`、Canvas、PixiJS 或 Three.js 层，因为文字渐变、描边、阴影、发光、粒子和动画可能位于这些层中。
- 预览由同源 iframe `/folia-native/obs` 承载。工坊把当前歌词时间、播放器时钟和 WebAudio 频谱送入原版 OBS SSE 协议。
- 预览时钟只能允许一个 HTTP 请求在途；浏览器卡顿或网络变慢时丢弃待发的旧样本、只保留最新播放器位置。`sentAtMs` 必须使用浏览器采样时刻并传到同一浏览器里的 Folia，让原版时钟插值补偿 HTTP/SSE 延迟，不能在 NAS 收包时覆盖。
- 预览的样式配置更新也只允许一个请求在途；滑动参数或连续切换特效时合并到最新配置，避免较早的请求在较晚的请求之后到达并覆盖当前效果。SSE 读取会话时只复制版本计数，配置、时钟和音频对象在写入后保持只读，避免每 10 ms 深度序列化整首歌词。
- iframe 视频桥正常播放时优先复用主播放器 `captureStream()`；媒体到达结尾后若用户 seek 或重播，必须切换为同源静音视频镜像并校准播放器时间，不能继续使用已经停止产出帧的结束流。原生水平/垂直位置默认均为 50%，界面提供一键重置到该中心值。
- 三种导出都以 44.1 kHz、FFT 2048、平滑系数 0.6 分析原音频，频段和指数增益与固定 Folia revision 一致。快速方式在 Xvfb 1920×1080 画布中同步播放原视频并实时驱动同一 visualizer，由 FFmpeg `x11grab` 直接录制 H.264/AAC；不产生 Alpha 中间片，耗时目标接近片长，另加 Chromium 冷启动和 MP4 封装时间。流畅方式逐帧驱动 OBS，等待两次浏览器动画帧后截图，并通过 FFmpeg `image2pipe` 同步叠回原视频，直接编码 MP4；浏览器绘制或编码变慢时增加耗时，避免 `x11grab` 按墙钟时间重复采样旧画面。透明方式先编码无声 ProRes 4444 Alpha，再叠加到原视频。
- 三种方式均固定 1920×1080、30 fps。透明方式的 MOV 永久保留且不含音轨；快速和流畅方式只输出 MP4。完整成片仍按有效歌词首尾各 5 秒裁切，15 秒样片从播放器当前位置开始。
- 快速方式的 x264 编码限制为 4 线程，让浏览器视觉效果与录屏编码有各自的 CPU 时间；转录容器在 CPU 争用时使用较低权重，原生渲染容器使用较高权重。实时画布仍受重特效渲染速度影响，因此复杂效果在高负载下可能出现重复画面；透明逐帧方式可用于对画面连续性要求更高的成片。
- 工坊提供 Folia 原生水平/垂直位置控制，预览和离线渲染使用同一参数。Tempera 是特殊情况：它原本在 Canvas 内部自行画满屏色块并对文字动态反色；透明覆盖模式会隐藏这些不透明色块、元数据片头卡以及会短暂铺满画布的 paper transition，并关闭依赖底图的反色，保留文字、阴影、装饰、逐字动画和镜头运动，让“文字主色”直接决定 glyph 颜色。
- Tempera 工作台预览使用 1.0 纹理分辨率并关闭全屏后处理，保证浏览器缩放预览时的字形清晰度。快速成片仍使用 0.5 的实时性能配置，否则 NAS 软件渲染只能约 5 个不同帧/秒；流畅及透明逐帧输出继续使用保存的其余原生质量参数。预览清晰度和快速模式的画面质量因此可能不同。
- 原生统一描边配置为 `text_outline.enabled/width_px/color/scope`，默认开启、黑色、3px、`scope=primary`。DOM 使用 `-webkit-text-stroke`，Canvas 在 fill 前 `strokeText`，Pixi/Sonnet/Tempera 使用 TextStyle stroke，Diorama 在 Three.js 文字纹理光栅化时描边并扩充留白。只命中主歌词和逐字高亮，不改歌名、歌手、翻译、和声、装饰字与背景排版。
- Tempera 原先的固定黑边已并入统一开关；关闭时恢复上游原生阴影，开启时只使用统一描边，不能叠两套黑边。描边和字体参数必须进入布局与纹理缓存键，调整后立即重建文字资源。
- Tempera 图片池沿用 Folia v0.7.8 官方 `layerImages`、`layerImageDepth`、`layerImageFrequency` 参数，最多 16 张。图片库按项目隔离：上传 PNG/JPEG/WebP 到 `data/images/<项目 ID>/`，校验解码和 4000 万像素上限，超过 2048 边长等比缩放，在项目内按处理后内容 SHA-256 去重。上传后自动加入当前项目；素材卡可永久删除并清除该项目已保存的图片引用，选中列表里的「从本片移出」只取消使用、不删除素材。项目样式只存图片 ID 与布局参数，预览和三种输出共用 `/images/<项目 ID>/<图片 ID>`，配置同时提供 `temperaLayerImageAssets`。缺失图片会在预览或渲染开始时明确报错。图片仅作为 Tempera 动态层叠加在录播上，背景继续透明。
- 原生字体支持内置黑体、宋体、等宽、原版 fontWeight 及 TTF/OTF/WOFF2 上传。上传上限 20MB，校验字体结构和字体族名，按 SHA-256 去重保存在 `data/fonts`。预览和三种成片均等待 `document.fonts.ready`；加载失败明确提示并回退内置黑体。
- 工坊界面在桌面将预览与已对齐歌词时间轴放在宽主区，文件、效果、导出放在侧栏；侧栏随页面滚动。手机用可独立展开的选择视频、歌词与预览、画面效果、导出视频四步操作；效果步骤可见时同一播放器缩为顶部紧凑预览。折叠只改变显示状态，不清空编辑内容；当前会话记住展开状态。
- 预览必须从保存后的 `alignment.lines` 副本读取有效逐句时间轴；未保存的编辑继续留在编辑区，点击“保存并应用到预览”后才替换预览数据。无当前歌词时视频保持无遮挡，预览标题显示已载入句数和下一句时间；不得用“请选择视频”之类占位文案覆盖播放中的视频。桌面预览、歌曲信息与时间轴在主列依次排列，预览不吸顶遮挡编辑区。
- 桌面使用共用左侧工作区导航，歌词制作按文件、视频与歌词、识别/效果/导出三列排列；手机预览在效果步骤展开时移入卡片内容，不使用固定悬浮层。视频下方缩略图时间条只叠加已保存的逐句歌词，点击可定位；抽帧由 `/api/media/{id}/thumbnail` 后台串行完成，缓存位于 `/data/thumbnails`，不写原录播。
- 文件、预览、歌曲、歌词时间轴、识别、效果和导出卡片均可独立折叠；桌面折叠状态在当前浏览器会话保留。文件列表、效果参数及歌词时间轴行各有独立纵向滚动和高度上限，歌词保存按钮留在行列表外。手机原四步操作仍保留，长列表可在步骤内单独滚动。
- 已导入的可选中文字体有霞鹜文楷轻便版 Medium、站酷小薇体 Regular、得意黑 Oblique，以及马善政毛笔体、龙藏体、站酷快乐体、站酷庆科黄油体、钟齐志莽行书、刘建毛草。后六款来自 Google Fonts 官方字库。古风字库另有演示春风楷、演示佛系体、演示秋鸿楷、演示夏行楷、演示悠然小楷（`maoken-fonts/slidefont`，原作者授权转发并按 OFL 开源）、香萃刻宋（`Miiiller/Xiangcui-Kesong`）和香萃潮汐宋粗版（`Miiiller/Xiangcui-Chaoxisong`）。原始 TTF 保持不变，各字体的 SIL OFL 1.1 许可文本保存在 `data/fonts/OFL-*.txt`。字体列表从 API 读取，刷新工坊页面即可看到，无需重建镜像。
- 原生渲染严格串行，接口在入队前取得全局锁；重复点击或已有任务时返回 409。临时文件使用 `.partial`，中止或失败不会替换已完成文件。仅透明方式按 3 GB/分钟预估中间片并检查可用空间。
- 每次 Chromium 渲染必须使用独立临时 user-data-dir 和动态空闲 DevTools 端口，不能复用容器默认 profile；容器以 `tini` 回收浏览器与 Xvfb 子进程。退出路径在强制 kill 后仍需 wait，并删除临时 profile，避免 `SingletonLock`、端口占用和僵尸进程阻断下一次任务。
- 快速输出：`<原名>_folia_<mode>_fast.mp4` 与 `<原名>_folia_<mode>.fast.render.json`。流畅输出：`<原名>_folia_<mode>_smooth.mp4` 与 `<原名>_folia_<mode>.smooth.render.json`。透明输出：`<原名>_folia_<mode>_alpha.mov`、`<原名>_folia_<mode>.mp4`、`<原名>_folia_<mode>.render.json`。

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

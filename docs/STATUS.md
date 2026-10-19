# 当前状态

最后整理：2026-10-19

## 2026-10-19 GitHub 最新源码同步与凭据检查

- 用户要求同步 NAS 当前源码以便分享，并检查 AI Key 泄露。从 NAS Git 源码副本建立独立审核树，核对业务源文件与生产目录一致；不覆盖生产 .env/数据库/媒体，不重启或中断任务。合入此前仅在 NAS 保存的自动投稿 V2、AI 封面/标题、6.1-sol 判歌、响度筛查、重制、SQLite WAL、合集适配及相关测试/模块文档；一次性运维源码保留，运行制品不提交。
- 同步前全可达历史37次提交/335个blob和235个候选路径检查，当前运行配置8项敏感值在NAS内精确比对也无命中。Gitleaks的15项均为两个公开字面量误报，仅精确豁免；没有发现需要通过历史重写清除的真实凭据，不强推或改变仓库私有状态。
- 新增SECURITY.md、离线密钥守卫及GitHub Actions全历史扫描；加强忽略规则/构建上下文，补全无密钥.env.example。分享版AUTO_PUBLISH_ENABLED默认0、账号/模板默认空；生产compose/.env原样保留，不自动部署。README修正已落后的“仅ready”说明，明确尚无Windows免安装版本及NAS路径/外部服务/素材授权边界。
- 隔离断网/只读源码容器使用当前API镜像执行后端全量418项，全部通过；首次416项中的4项仅因test_publish_control夹具漏引入primary_cover_configured，修复夹具并新增Gemini主用的允许/拒绝及不泄密用例，不改运行行为。离线安全守卫5项通过；122个Python文件AST解析、Compose/工作流结构、Dockerfile显式COPY路径、Git暂存差异检查通过，当前文件及全历史复扫均无真实凭据。健康检查仍正常。最终同步提交以GitHub提交记录为准；不把扫描通过等同于完整依赖或渗透审计，不在仓库保存未脱敏凭据。

## 2026-10-19 用户指定《要抱抱_02》投稿（已完成）

- 用户取消两遍合唱制作（此前仅只读调查，未启动合唱渲染），明确要求上传今天第二遍。核对项目3d18a332b1ed4dd6b0b42e7687242a72完整high、非样片，实际202871135字节；17日同名旧稿记录已删除，创作中心172条无同名稿，今天两遍均因旧song_key记录而duplicate。只显式放行第二遍，第一遍及其他歌曲去重/水位/开关不变。
- 新投稿78cdc33b66245535a54bf8738175521b，taskId=c189e348-c08d-4334-868e-9f3a1a2276b6，AID117467137443746，BV12HnJ6HEN3，上传100%/completed/success，合集9133790已joined，初查审核中。稿件详情HTTP500但创作中心MID/AID/标题精确匹配取得BVID，不能因查询异常重投。
- 复用成功封面和AI标题“💗鼓起勇气，来抱抱｜《要抱抱》｜【小红泡-管珩心】翻唱”，0次新AI请求／封面累计仍1。继承本主播preset ign19v4u95a及formatDesc，日期为2026.10.19，保留合集及策略；第二遍identified_artist为空，不拿候选艾辰或旧稿璟年补身份。视频/封面Bililive共享路径实测size+mtime_ns一致，源删除选项false，参数校验HTTP200 success。
- 独立ops/publish-yaobaobao02-20261019/once.py，经现有客户端仅一次真实POST；先持久化次数／专用accepted receipt，再交接DB。实际第一次返回任务ID后通用checkpoint因尚无song关联报错，专用receipt已存；核对该task已completed后从receipt恢复，无再次POST，submit_attempts=1。通用checkpoint已移至歌曲主关联交接之后。旧任务ID/AID/BVID/身份/原视频/标题/简介/payload完整保留，仅唯一主关联转到新记录；歌曲两次演唱及旧发布历史不删除。
- 一致性DB备份integrity_check=ok、原行／payload／共享路径／receipt／result／verification保留于/data/publish-template-backups/yaobaobao02-20261019，备份及凭据不入Git。Python语法、4项断网防重复提交定向测试通过；实际原视频和封面stat/hash、旧投稿核心字段保持不变，healthz正常。无新增后端运行模块／镜像变更，无服务重启、ASR中断或合唱输出；仅同步本任务运维源码/文档到NAS Git副本，不自动提交推送。

## 2026-10-19 小红泡温柔教练反差精剪（单次视频制作，已完成）

- 用户授权将当天“我脾气很好／最温柔的教练”与实际游戏后的反应做成完整反差切片，可使用特效。只读提取三段现有整场ASR及录播：12-35-23、13-31-56、15-02-01。14个剪辑镜头串起立人设、温柔教学、夸夸教育、调整心态、十五字缩到五字、生气、降火下播，开头预告和结尾宣言回放明确标记，未伪称时间连续。
- 独立运维脚本ops/contrast-20261019，既有API镜像中的FFmpeg/libass/Noto CJK字体；无新后端模块或Dockerfile变更。隔离容器network=none、1CPU/2GiB、低CPU权重，录播挂载只读，仅新的歌曲切片专属目录可写。数据库由宿主只读提取所需ASR快照，渲染容器不挂生产数据库；不重启或取消生产任务、不改投稿开关、不生成publish_job、不调用任何AI或投稿接口。
- 样式包括重点字幕弹出、阶段提示、15字→5字、轻微画面震动及结尾低饱和回放；保留原声、不加BGM。字幕基于现有ASR与少量明显文字修正，妹妹回应使用独立颜色／标记；不声称已逐句人工听校或完成说话人识别，原转录快照完整保留。最终两处切口收紧，避免带入下一句话，基础版与缓存保留。
- Python语法、4项定向测试通过（镜头时间／顺序、ASS转义／时间、妹妹字幕分离、已开始时间线不可静默变更）；真实ASS/字体试渲染通过，基础版及最终版全片解码均通过。最终115.084秒、1920×1080/30fps/H264+AAC48k双声道、73180972字节，音视频起点均0，时长差11ms；三个源文件size+mtime_ns与制作前一致。最终字幕画面另抽14张供目检，原声和ASR个别字仍待用户试听复核。
- NAS最终文件：/vol2/1000/video/Folia录播/小红泡-管珩心/2026-10-19/歌曲切片/温柔教练_反差精剪_v1/小红泡_最温柔的教练_反差精剪.mp4；剪辑清单、ASS、原ASR、基础版和result-final.json同目录。另复制本机output/contrast-20261019供直接查看。原录播及之前两条无损素材不动，不自动投稿，不推送GitHub。

## 2026-10-18 小红泡去重长篇单集（后台生成中，未完成）

- 用户明确选择全部已完成成片、按同歌去重、歌曲首尾顺畅衔接。只读盘点173个已完成工坊项目，兼容/output与/output-legacy，不局限于投稿关联85首；去重23个版本后保留148条。仅排除1个实际缺失文件与1个明确标为“我好想你-前奏”的非完整演唱片段。旧版缺identified_title不从jobs.title/歌词候选补写身份，只用原输出目录作“旧版待核对”显示标签，保留8条未核对标题；所有原数据库身份、视频、已投稿结果均不改。
- 合集专属manifest冻结源项目/身份/路径/size/mtime、歌词边界、质量与去重依据；同歌优先高置信、已投稿、逐帧版本。同名归一与大段完全一致歌词辅助发现别名；旧读心术目录名与已确认标题一致且歌词相似0.9128，保留新版；另人工对照完整首尾歌词确认旧误标Can't Stand It实际与高置信《讨厌》同歌（相似0.9349），仅从合集清单移除旧重复条目，不改旧项目identified_*。无同名明确歌手/歌词冲突。歌单按录播日期/源路径编排，不伪称情绪/BPM/调性自动排序。
- 独立CPU-only工具ops/compilation-20261018/compilation.py，不改后端API/前端/镜像/自动投稿开关。整体响度分析后施加恒定增益（目标-18 LUFS、峰值余量-1.5 dB，增益限定-24至+12dB，峰值限制时不保证每首精确达到目标）；不变速/变调。只有显式成片trim元数据能投影歌词边界、两侧有安全余量时才做≤0.8秒画面叠化/音频线性交叉淡化；证据不足的旧片不叠人声，改用短画面淡出淡入及10ms音频防爆音。原成片含歌词直接保留，不重新ASR/对轴/生图或改歌词。
- 实现按歌曲主体/短转场逐段H264+无损PCM缓存，统一1080p30、片段禁B帧，最后视频流复制＋连续AAC封装为单个MP4，生成内嵌章节和歌单时间轴；部分失败/重启可复用完整缓存，.partial不替代成功输出。新增文件是只读挂载的独立运维任务，不是后台新运行模块，因此无需改逐文件COPY的backend/Dockerfile，实际容器导入/执行已验证。
- Python语法及4项测试通过（含真实FFmpeg三段合成、两次交叉淡化、章节、7.4秒时长、音画起点、无边界淡入淡出、源stat变化拒绝、生产重任务SIGSTOP/SIGCONT只作用于本任务进程组）。最初xfade真实测试暴露帧率1/0，已在滤镜尾部重新fps=30统一；最终4项OK（2.207秒）。真实《回到过去→退后》《退后→爱琴海》两个540p/23.2秒试片均完整解码通过，H264/AAC起点和时长完全一致；叠化中间帧已目检。仅这些短片完成验收，不能误称8小时长版已完成或全片已验收。
- 独立容器folia-xhp-compilation-render-20261018已启动，1核CPU/2GiB/低CPU权重，源/output与/output-legacy只读，仅合集目录可写。读取生产health的heavy_task_slot，忙或不可观测时等待/暂停本任务FFmpeg，空闲恢复，不取消或重启ASR/渲染/投稿。实际已处理首条并进入第二条，清单预计28905.133秒（约8:01:45），尚未完成；进度progress.json与completed-tracks.json、结果result.json在合集目录，不能只因容器running就说已生成。
- NAS目录：/vol2/1000/video/Folia成片/小红泡-管珩心/歌曲长篇合集/2026-10-18。预期成片名小红泡_歌曲长篇合集_去重.mp4，完成才写result.json和歌单时间轴.txt。两个试片另已复制到本机output/compilation-20261018/transition-01.mp4及transition-02.mp4。运维脚本/文档同步NAS Git源码副本，不自动提交推送；不注册publish_job，不产生真实上传或额外AI请求。

## 2026-10-15 完整参考图/无话筒图库（已部署）

- 用户要求取消本地截半身，提供完整参考图，让AI优先半身但适合歌曲时允许全身。人工复核正比10张/Q版6张：带话筒正比22-50-32、22-50-44、22-57-04、22-57-12，Q版22-53-55共5张排除出新库，原文件不删；此前固定22-50-32确实带麦。其余6张正比原PNG作默认池，5张Q版无麦原图单独保留不启用。诊断缩略图仅本机审阅，绝不用于生产输入；新库复制原PNG并逐字节/指纹核对，无裁切/缩放/重编码。
- cover_fallback.provided_reference新增主播references池，显式人工无麦标记、指纹校验及SHA256(主播键+NUL+歌曲键)稳定映射；publish_v2传权威归一歌曲键。新参考type=provided-transparent-full，crop=null，保存source/frame一致SHA及ID；未知主播不串图，配置坏/含未确认或带麦项终止。构图提示改为优先半身、可按歌曲内容和氛围全身，不再禁止腿部。保留旧crop兼容，不重做已有封面/原图缓存或已投稿任务，不重置次数。
- Python语法、19项相关断网回归通过（8.841秒），覆盖整图字节/尺寸/透明度、稳定选择/顺序无关/歌曲间变化、带麦/未复核/损坏拒绝、身份保护、主用/备用、缓存/重启和10次预算。运行模块未新增，既有Dockerfile COPY已覆盖。源码/11张无麦原图/人工复核清单在ops/reference-full-20261015/stage；线上/data/cover-references/references.json已迁移到full-v1的6张正比全图池，Q版5张仅保留。旧固定带麦素材与历史裁剪副本保留不删，但新库不再选择。
- 首次更新预检发现新整场ASR“17-07-16_【歌杂】这小牛烧心.mp4”正在运行，安全停止；先完成只读SQLite一致性备份（integrity_check=ok）及配置/源码/回滚镜像备份。随后用户明确授权“允许中断，现在部署”：保存14e3da799687468594b42f72d11a80fd原行，通过既有cancel入口确认cancelled后才重建API。新镜像56175dc27d57fc636848773411efbbe03a56d08c5a96670be0b92c1dfcb10a1f，镜像内app/构图指令导入通过，/healthz ok；只更新API，未重启转录、渲染、录播、Bililive或Web。再调用原流水线retry入口恢复为queued/retrying，保留原source/profile和transcriber工作关联；不声称从未中断或保证每个ASR计算步骤都不重做。中断/恢复快照及备份位于ops/reference-full-20261015/backup，代码/文档同步NAS Git副本，不自动提交推送，密钥/图片/DB不进入Git。
- 查询确认前次恢复的小红泡10首均已completed取得AID和BVID，全部Gemini生成；本次不动这些封面/投稿结果。左手指月BV1g8Jy6FEip、海屿你BV1h8Jy6FETa、嘉宾BV14qJy6sEni、看着我的眼睛说BV1TqJy6sELQ、天涯BV1g8Jy6FEDQ、My WorldBV12qJy6sEDR、人间不值得BV1xBJy69Ehr、想她BV14BJy69ETR、第二杯半价BV1xBJy69E8t、勾指起誓BV1MeJy64EjA。

## 2026-10-15 Gemini改为封面主用，小红泡10首恢复（已部署）

- 用户要求将已验证的Gemini改为主用。新增COVER_PRIMARY_PROVIDER配置，NAS.env设gemini；第一笔实际新生图直接使用原生gemini-3-pro-image-preview/imageSize=2K/16:9，不再等待GPT累计>5。继续使用既有环境中的Gemini密钥，不复制/输出密钥，GPT配置保留但不自动回切已403的通道。配置默认gpt兼容旧部署，非法值或Gemini未启用/缺密钥明确停止。控制接口、启用门槛及投稿页按主通道显示，不再硬性依赖GPT密钥；标题仍gpt-6.1-sol不变。
- 小红泡2026-10-15新建10首均因GPT403、累计1–5次终态而未触发原备用。经用户单独授权，只将明确10个无taskId/AID/BVID/提交次数、无封面/payload、绑定bilibili:2516117的原任务恢复pending；不新建投稿行、不清累计次数、不改身份/原MP4/已生成AI标题/模板/水位或其他旧失败。歌曲为勾指起誓、第二杯半价、想她、人间不值得、My World、天涯、看着我的眼睛说、嘉宾、海屿你、左手指月。记录ops/gemini-primary-20261015/released.json；恢复入队不等于上传完成，实际结果查投稿状态。
- 保留每歌曲累计10次、并发1、600秒无隐藏重试、原图/成功封面缓存和重启恢复、用户半身透明参考与书名号可选。Gemini鉴权/明确参数错误继续终态，不改成无限重试；Bililive故障不重新生图，已接受/已完成不重投。新Python模块未增加，既有Dockerfile已显式COPY三个运行模块。
- Python/JS语法、4组页面主用/配置状态用例通过，隔离断网147项完整回归通过（341.086秒）。新镜像内app/主用选择/配置门槛导入通过。备份SQLite一致性快照integrity_check=ok，原配置/源码/回滚镜像保留于ops/gemini-primary-20261015/backup；两次部署检查重任务/render和准备/提交/上传均空闲，只更新API/Web，ASR、renderer、录播和Bililive容器未重启。API镜像f6c5c7dab10096dc550491285df556e94b459c82dc3a2d15083dec2528627582，Web449a183051f1a96b6ca7a80ed970b42261ddefda55afd04904400ec9f5e07bb5，/healthz ok，运行控制确认cover_primary_provider=gemini、cover_max_attempts=10、title_model=gpt-6.1-sol。相关代码/测试/文档同步NAS Git副本，不自动提交或推送，备份/密钥/运行制品不入Git。

## 2026-10-15 封面书名号可选（已部署）

- 用户认可无书名号封面并授权部署；publish_v2.PROMPT改为左侧完整写出准确歌名，书名号可加可不加，由AI根据排版决定。人物身份、自然表情动作、右侧人物、独立歌曲背景及半身近景要求保留，GPT/Gemini共用。投稿AI标题/固定标题里的《歌名》不改，权威身份不改。只作用于后续实际新生图，不清已有封面/原图缓存/冻结payload，不重置次数或重新投稿，没有额外付费验证请求。
- Python语法检查通过；隔离断网完整144项回归通过（230.966秒），覆盖提示词、投稿标题保留书名号、身份保护、成功封面缓存及累计预算。首轮测试夹具缺少7个测试模块，核心62项通过但整组报缺模块；补齐后完整重跑144项OK，不把夹具错误当成业务故障。
- 部署前两次确认重任务/render及准备/提交/上传均空闲，SQLite一致性备份integrity_check=ok，保存原配置/源码和回滚镜像folia-api-before-cover-brackets:20261015；仅更新studio-api，未中断ASR或重启其他服务。新镜像da1fad223467772cc88cf4b23c83e8b3ae1f67164b3659cb5927661ce5ee5a0e，镜像内app/提示词/半身指令导入通过，/healthz ok、容器healthy，投稿开关保持原值。运维记录及备份位于ops/cover-brackets-20261015，凭据不入Git；同步NAS Git副本，不自动提交或推送。

## 2026-10-15 原生Gemini 2K验证通过，备用已部署并恢复4首

- 用户要求先验证真2K再部署。以同一小红泡半身透明参考和《游园惊梦》提示词，单次原生POST /v1beta/models/gemini-3-pro-image-preview:generateContent，generationConfig.imageConfig={aspectRatio:16:9,imageSize:2K}、responseModalities=[TEXT,IMAGE]、candidateCount=1；HTTP200、88.52秒，接口原图JPEG2752×1536/2741342字节，SHA256 f166798c2a12f051ebe575d3ea37a21d3b0b5d2f527e3c424c4e9f5b07e47886。无本地放大/叠字/去水印。返回无modelVersion且usage含estimated标记，不据请求名/估算用量证明后端或计费。此图漏《》，已明确告知，仍无OCR/付费视觉。
- 因原生尺寸参数已验证，备用改为此协议，不再用兼容chat路径；只接受一张非thought的inlineData原图，验证最低2048×1152和横版比例，低分辨率/坏图在原累计预算内按退避处理，不静默降级或放大。逐笔attempt-N.json同时记录实际请求配置。144项断网全量回归通过（104.622秒），8项原生协议定向回归通过，新镜像782d977de3d5966f6fa0454b0e95977f0895dbdda7124f0a3b6fb4b8fa200f81，模块/app导入、运行时配置/5次边界/人物绑定检查通过。
- 用户明确允许中断当前ASR，但现场核对时整场转录已completed，流水线正在后续analyzing。先保存bf503ac430234d48adaa4fc657bae8fb原行/转录和transcriber ID，再调用既有cancel；只更新studio-api，无录播/转录/renderer容器重启或原文件操作。该流水线随后实际completed/error为空/0首歌，原ASR任务ID和完整转录与中断前快照完全相同；保护性retry检查拒绝对completed重排，未重跑ASR或已完成分析。记录在data/publish-template-backups/gemini-fallback-20261015/interrupted-run.json及resumed-run.json。
- 原GPT、标题密钥与模型不替换；Gemini独立环境密钥、ENABLE=1；小红泡bilibili:2516117绑定用户正比PNG半身副本，芒芒等继续自己的选帧。生产运行版本已核对原生imageConfig2K/16:9，身份不串用。健康HTTP200/ok=true，自动投稿原开关保持启用。原镜像folia-api-before-gemini:20261015及一致性DB/配置/源码备份保留。
- release_deferred.py核对新镜像/备用配置/原行身份与标题/无提交ID和次数余量后，只把原4首next_retry_at恢复到可执行，不清计数、不改status/权威身份/MP4。金风玉蝶由9到第10次，已真实通过Gemini生成2752×1536原图并按既有整数比例裁剪2720×1530上传JPEG，开始BililiveTool上传，taskId=141073ba-9616-43e2-88cc-ddc4db0e173a已落库、submit_attempts=1。玻璃第9次已用Gemini/generating；我们俩8次、没关系7次恢复等待，未改5次HTTP400的你的酒馆对我打了烊及旧失败。仍需观察其余封面和最终上传结果；尚无AID不能误称已发布。未推送GitHub。
- 后续正式验收：原4首均已完成Gemini原生2K封面（全部original2752×1536/upload2720×1530）、上传取得AID并确认joined合集；最终累计次数金风玉蝶10、玻璃9、我们俩9、没关系8。金风玉蝶AID117444035282702/BV1nDJy61EMB，玻璃AID117444035348320/BV16DJy61EqT；我们俩AID117444035216596、没关系AID117444051995416已completed/joined，稿件详情查询暂HTTP500，BV号按既有退避查询，绝不重投。这与最初GPT封面失败是不同阶段。
- 逐项对比备份：既有111条completed稿件的身份/源项目/标题/简介/tags/封面/冻结payload/taskId/AID/BVID/submit_attempts全未改变；本次4首权威身份/原视频size+mtime/原AI标题和生成记录均保持不变。rollout/上线水位/授权批次/开关未改。相关运行源码、显式Docker COPY、测试、文档及运维脚本已同步NAS Git副本；同步前验证旧副本与备份一致并保存旧文件，仅修改本任务相关文件，不含.env/密钥/原图，不自动提交或推送。验证快照ops/gemini-fallback-20261015/verification.json。

## 2026-10-15 Gemini封面备用与用户透明人物图（先前实施过程，部署结果以上文为准）

- 用户认可小红泡透明正比图的半身Gemini封面，要求GPT累计失败超过5次的原任务使用备用。新增cover_fallback.py：现场已验证的兼容chat/completions，单参考PNG、单张、600秒无隐藏重试；严格>5后下一次切Gemini，所有provider合计仍最多10次，不清零、不重复生成成功封面。cover_model/次数先写DB，并保存attempt-N.json的provider/参考指纹/提示词/状态，无密钥。原GPT、标题、身份、去重/置信/响度/模板/投稿状态均不改；新模块已加入backend/Dockerfile。
- 小红泡bilibili:2516117精确绑定用户正比RGBA原图（SHA256 bb19b18aa05d45a0a0b8a24e25161208d87a69f6d6bf8a22087e8f0e56fa1efa），裁剪(1500,350,2680,1250)副本作参考，原素材不动；其他主播仍用自己的视频选帧，禁止把小红泡套给芒芒。配置文件/data/cover-references/references.json，素材已复制到NAS。配置损坏终止，不静默串主播。
- 半身实测Gemini返回1376×768而非2K，提示词确实补充“输出2K横版图片”，但兼容chat请求未传专用分辨率参数；网站公开说明未证实该通道如何强制2K。不能将文字要求当尺寸保证，也不本地放大冒充2K。GPT同条件线上客户端单次测试11.69秒HTTP502。实测图/记录在本机output/imagegen/xiaohongpao-transparent-20261015。
- 新env变量COVER_FALLBACK_ENABLED/BASE_URL/MODEL/API_KEY/PROXY及COVER_REFERENCE_CONFIG，备用密钥只写NAS.env运行配置（已备份、权限600），未进入代码/Git/日志。原部署compose尚未替换，因此当前API仍旧f7115f803bebd424e0a0ac2eca998b3431ea8c454303a810d9669989c848f472，尚未启用备用。增量镜像已构建7c0283d2cb42588097fbcd14b2466b5d0446e3eca3c50520fd2db937de6e205a，模块和app导入通过；源代码暂存在ops/gemini-fallback-20261015/stage，未覆盖运行后端。
- 143项断网回归完整重跑全部通过（175.850秒）。首轮141项通过、2项因测试夹具未复制Dockerfile报错；补齐夹具后两项定向通过并完整重跑143项OK。覆盖真实请求结构、阈值、预算、模型请求前落库、缓存/重启、身份保护、素材匹配、原图不动、请求错误分类、制品不带鉴权、原MP4/已提交保护。日志NAS ops/gemini-fallback-20261015/regression.log。
- 备份SQLite integrity_check=ok、原.env/compose/源码/文档在ops/gemini-fallback-20261015/backup，另原4行快照和整库一致性备份在data/publish-template-backups/gemini-fallback-20261015。仅4首原pending、cover阶段、无task/AID/BVID/submit_attempts且次数>5的芒芒任务临时延后next_retry_at（最多24小时，等待部署，未清次数或改status/身份/源视频/标题）：金风玉蝶9次、玻璃8次、我们俩8次、没关系7次。你的酒馆对我打了烊5次HTTP400未动，海绵宝宝/跳楼机等旧失败未恢复。
- 部署预检先遇到《第二杯半价》渲染、随后该曲准备请求，再遇新整场ASR“12-30-59_【午间陪伴系】我去 小红帽.mp4”；均在复制后端/重启前安全停止。没有擅自打断任务。已向用户询问等待ASR结束还是允许中断后部署；待确认后运行ops/gemini-fallback-20261015/deploy.py，只更新studio-api，再运行release_deferred.py（验证新镜像/备用开关/身份/无已提交/预算后仅恢复这4首的next_retry_at）。仍需部署后健康检查、真实备用生成/上传观察、最终文档和NAS Git副本同步；未推送GitHub。

## 2026-10-13 《游园惊梦》合集单步实测通过（明确授权的单稿维护）

- 用户指出“刚才投稿的没加入合集，正好测试”，选择最新小红泡《游园惊梦》fdcec4448cff4006992da76861c301b9/AID117432995808958/BV1FPpB6eEMV。原稿17:58已上传，新Bililive适配18:17才部署；原快照无foliaCollectionTracking、collection_status=NULL，不能把这条旧路径当成新回调失败。
- 通过现有Bililive创作中心列表精确核对MID181647901/AID/完整标题、唯一cid_list=42708107686，并核对合集9133790的正片小节10204569；此前所属合集查询为“啥都木有”。只针对这一稿授权补加，不排其他历史稿件，不改投稿快照或重投。维护源脚本为ops/bililive-season-fix-20261013/test-existing-yuyuan.py及run-existing-yuyuan-test.py。
- 原单行和SQLite一致性备份在/data/publish-template-backups/collection-test-20261013-fdcec4448cff4006992da76861c301b9/。调用同一队列工具仅原子保存核对后的UID/AID/CID/目标/原标题/原任务ID；录播/上传/重任务idle时重启Bililive恢复这条记录。所有账号/B站调用仍由Bililive已有SDK执行，无自己的登录/Cookie/投稿器。
- Folia只对这条记录显式置collection_status=pending。poll_collection改以非NULL合集状态作为已授权跟踪门槛，仍核对原payload目标/UID/AID/taskId；允许显式单稿维护跟踪无新marker的旧快照，旧默认NULL依旧不读、不补加。原frozen payload原样保留，SHA256=55b248e10dce1f13b7fa2727a2f53cfe258cf033b527bf5243fd7a926d71c77f。
- Bililive队列首次处理后joined/attempts=1；随后真实GET /bili/season/{aid}返回200、9133790/《管珩心的歌声收藏夹》，Folia同步joined、合集错误清空。这是真实SDK合集步骤验证，不是仅mock；仍未新增一次真实视频上传来验证opt-in新回调完整链路。是否已经加入在处理前也会核对，不能把流程尝试次数误称为上传次数。
- 原MP4stat、封面/标题/简介/tags、权威身份、请求快照、AID、上传taskId和submit_attempts=1均未变；没有重新生图或上传，也没修改其他旧合集。3项定向回归（显式旧稿维护/旧NULL隔离/合集与上传分离）与语法通过，API镜像f7115f803bebd424e0a0ac2eca998b3431ea8c454303a810d9669989c848f472，healthz正常；修改源码/测试/文档同步NAS Git副本，不自动推送。

## 2026-10-13 投稿合集跟踪与可靠加入（已部署，仅后续新任务）

- 用户已手动补齐旧稿件并授权修复后续流程，明确不再改历史稿件。现场模板 ign19v4u95a 和最近快照均有 seasonId=9133790；《风月》父任务 completed/AID 已取得，17:39:09 日志“加入合集失败”伴随上游 HTTP 412。最近 12 条中 11 条可查到目标合集，不能误报全部漏加。
- 线上实际 BililiveTool 3.18.0 在创建稿件的 onEnd 另调 addMedia2Season，并先 getArchive 获取 CID；合集错误只记录日志，父上传任务仍完成，且旧调用未 await。未找到已验证的同一次投稿请求加入合集参数，不猜 season_id/section_id。修复仍在同一自动流程内先创建稿件/AID、再自动加入合集（不等审核），不是原子同一次 B站请求。
- 为固定生产镜像增加小型受鉴权适配，仍完全使用 BililiveTool 的现有 SDK/createClient/登录态。仅 options.foliaCollectionTracking=true 的新 Folia 请求使用新分支：从父任务已完成分P的 completedPart.cid 取 CID，跳过容易 412 的 getArchive；将 UID/AID/CID/模板合集/小节/标题/任务 ID 原子保存到 /app/data/folia-season-jobs/<uid>-<aid>.json。无新上传器、登录/Cookie 代码或凭据持久化，非 Folia 请求仍走原分支。
- 独立串行队列先核对所属合集，已经加入只确认，不重复加入；目标不符停止而不移动。小节必须属于模板目标合集，缺少小节时只接受唯一正片小节。await 加入后再次核对；响应丢失/重启也先查询，不重新上传视频。累计最多6次流程尝试；一般错误 2分钟起退避，412 暂停60分钟，400/401/403 停止人工检查，不更换IP或绕过风控。损坏恢复记录保留并终态告警，不杀录播服务或创建新请求。
- 新只读受鉴权接口 GET /api/bili/folia-season/capabilities（version=1,durable=true）、GET /api/bili/folia-season/{aid}?uid=...。没有历史补加入队/上传入口。Folia 在新准备读取适配能力后冻结标记；publish_jobs 新增 collection_status/error/attempts/next_collection_at，仅新标记请求启用，旧列默认 NULL。上传 completed/AID、审核和合集状态分开；合集查询独立于审核重试时间，不因合集失败清除AID、标题/封面或重投。
- 页面显示合集等待/确认/退避重试/已加入/需人工核对及次数/原因；上传 completed 但合集未确认时显示“上传完成 · 合集待完成/失败”，不笼统显示整体投稿完成。已完成旧稿件不追踪回填。publish.js 查询版本更新为 20261013-collection-tracking。
- 125项 Python 隔离断网回归、10项 Node队列测试、实际生产 bundle 回调 mock 测试、页面状态测试、Python/JS/CJS语法及镜像导入通过。初次完整测试缺少 render_revisions.py 夹具，补齐后重跑125项全部通过；未额外付费生图或真实投稿验收。下一个自然新投稿才能验证实际入合集结果，不能把 mock 成功宣传为已成功真实加入。
- 部署前录播机/上传/重任务均 idle，SQLite 一致性备份并 integrity_check=ok；备份位于 /vol1/1000/docker/folia-video-studio/ops/bililive-season-fix-20261013/backup，保留旧源码/配置/镜像。仅更新 BililiveTool fullstack、Folia API/Web，不动 ASR/renderer/原录播/MP4。Bililive compose 原文件不改，新增 docker-compose.override.yml 固定 folia-bililive-season:20261013，以免常规重启丢失适配。
- 新镜像：Bililive 339dec01c026ab1ec28611a3a7888d5ec734536976e8a1696a01ba2712192dbd；API最终 663fe6235585ce981416b6abda3ce0d96801d5cd90c1b706c431d0785bbaf8da；Web 6ec454848429f18c966b32d257ad440889b6b4f5979bddc402d81abf359a4319。/healthz ok、API healthy、新页面/脚本/API200；合集能力接口200、未鉴权401、非法ID400、旧《风月》记录404。历史149条身份/成片stat/封面/标题/简介/tags/payload/任务ID/AID与备份完全一致；旧任务 collection_status 均NULL、Bililive新合集队列0条，未写历史合集。
- 补充提交前能力检查，已有ready快照也不能向回滚/不支持适配的上传器发POST。新增这项及正常跟踪/缓存3项定向测试通过；准备阶段和提交阶段均受保护，临时未就绪保持ready/退避而不增加submit_attempts。只补更API，录播/Bililive/Web不再重启；中间API镜像保留folia-api-before-season-guard:20261013。
- 适配源码/精确 bundle 锚点补丁/测试与运维说明在 ops/bililive-season-fix-20261013，生成 original/patched/backup 和日志排除 Git。新 Python 模块未增加，现有 Dockerfile 已显式COPY两个修改模块。源文件/文档/测试同步NAS Git副本，不自动提交/推送；上游镜像升级前须重新验证锚点/协议，不能直接覆盖本镜像。

## 2026-10-12 封面独立场景提示词（已部署）

- 用户同意为减少同场直播背景趋同追加：“参考图仅用于保持人物身份，不沿用直播背景。根据歌曲独立设计场景、主色调和光线，避免统一套用同一种背景风格。”只改 publish_v2.PROMPT，锁脸、自然表情/动作、人物右侧/完整《歌名》左侧仍保留。
- 不清空已有封面/原图缓存/payload，不重置次数，不重新生图/上传，不新增跨图视觉检测；新请求应用新提示词，但不保证所有封面视觉上完全不同。本次没有额外付费验证请求。
- Python 语法、5 项容器断网回归（提示词、缓存/重启、授权重制复用、展示歌名/身份、封面写库故障）通过，新镜像实际提示词导入通过。部署前确认无准备/提交请求、无重任务，备份 SQLite 一致性快照、配置和相关源文件到 ops/cover-prompt-20261012/backup；只更新 API，其他服务/数据库业务状态不改。
- 新镜像 SHA256 b6f3dc885b05cdeaaf8ec2c1883dd65b632558793809f559d0aca1406d753ece，/healthz ok、容器 healthy；保留上一版 sqlite-fix-20261012 可回滚。相关源文件/测试/文档同步到 NAS 与 Git 副本，不自动提交/推送。

## 2026-10-12 SQLite 锁冲突与投稿恢复（已部署）

- 只读调查发现线上 studio.db 使用 DELETE 日志模式，多个提交事务报 database is locked；投稿错误处理把这类临时数据库错误当成终态。库位于 NAS 本地 btrfs，不是远程共享；未确定历史锁持有线程，不能据此宣称单一长事务来源。
- app.db 启动时串行完成一次 WAL/建表/提交，成功后才置 schema_ready。新增 sqlite_runtime.py：只重试同一事务 COMMIT，或完整回滚后重做短纯数据库更新；不重跑含网络/付费操作的整个工作流，不吞掉磁盘/损坏等其他错误。Dockerfile 显式 COPY 新模块。
- 投稿 V2 的锁错误按退避保留待恢复状态；标题结果、已接受 task ID、已完成 AID 在 /output/publish/songs/<song_id>/checkpoints/ 原子保存输入指纹及白名单字段，DB 写失败后重启复用，不存密钥。标题随明确授权重制复用；上传凭据与 payload 指纹严格绑定，冲突停止人工核对。封面继续复用已落盘 original-N.bin，不增加生图次数。
- 启动仅恢复 V2、精确锁错误、submit_attempts=0 且无 task ID/AID/BVID 的准备失败；提交前失败且已有 payload 回 ready。保留标题、封面、payload、所有次数，不改投稿开关/上线水位/高置信/响度/去重；旧 V1、已接受或不明提交不得重置。此次恢复目标共 7 条，原队列原资格仍生效，不扩大历史补投。
- 小红泡《我的果汁分你一半》《春夜坠落》虽本地记上传失败，真实 archive_detail 已确认同 UID、完整标题、分P歌名和提交后 7–9 秒创建时间匹配。只回填既有 AID/BVID，保留旧 task ID/次数，无新上传：《我的果汁分你一半》BV11hpi6TEuk（开放浏览）；《春夜坠落》BV1kvpi6eEb6（稿件仅自己可见，state=-50）。上传完成与可见性继续分开，不因仅自己可见重投。
- 已完成数据库一致性备份及 integrity_check=ok，备份路径 /vol1/1000/docker/folia-video-studio/ops/sqlite-fix-20261012/backup，含原源码/compose/.env；凭据不进源码或 Git。只更新 API，回滚镜像 folia-sqlite-rollback:20261012，新镜像 SHA256 61a3d24dd2000fda81173eebaadba51b4f1a28f5c06055f3193970927d109610。原录播/MP4/其他服务未修改。
- Python 语法通过；容器断网隔离 119 项相关测试通过（SQLite 实际读锁/提交重试、WAL 并发初始化、标题/封面/ID/AID 写库故障恢复、重启不重复 POST、旧任务隔离、原 MP4 保护及原投稿/标题/重制回归）；新镜像导入通过。测试不访问真实 AI/上传接口。完整记录见 ops/sqlite-fix-20261012/tests.log（NAS）、reconciliation.json。
- 部署后实测 journal_mode=wal、/healthz ok、容器 healthy；运行镜像三个修改模块 SHA256 与本机一致，自动投稿 rollout/水位/授权批次未变。首轮 7 条已恢复为 pending/ready，随后《我不配》《我是真的爱上你》取得新 task ID 并落库，《咖喱咖喱》ready；两条历史稿件完成回填。初始观察日志锁错误/traceback 均为 0；这是短时验收，不保证今后完全无锁或所有队列均已上传完成。原成片与其他服务保留，相关源码/测试/文档同步到 NAS Git 副本，不自动提交或推送 GitHub。
- 后续观察：《我不配》BV1Zwpo6mEiE、《我承认》BV17wpo6mE8p、《咖喱咖喱》BV1qwpo6mExW 已完成；《我是真的爱上你》已保存 AID=117427643876212，稿件详情临时访问失败按退避查询，保持 completed 不重新提交。《爱要坦荡荡》上传中，《下个路口见》准备中，《热气球》待处理。automation/health 扫描 ok，scan_count=7/error_count=0、无重任务占用；本条为观察快照，后续由既有 worker 继续，不添加新监控任务。

## 当前维护入口

先读 CODE_MAP.md 与 ARCHITECTURE.md，再读对应模块。下方日期条目是历史记录，不能将旧版算法当成当前规则。当前自动整场用Whisper；单曲Qwen只提供定位证据；标准平台字时间只统一平移；DeepSeek全曲重排关闭。切片后先执行免费低响度筛查，明确很轻的疑似背景音乐跳过歌词及后续流程。投稿采用歌曲项目＋免费选帧＋GPT完整封面＋BililiveTool真实上传；测试白名单为空，接新水位之后的合格成片，另按用户最新授权恢复芒芒既有逐帧批次中合格未投歌曲，按原录播日期新到旧优先。其他历史库/旧V1仍隔离。高置信、严格响度、身份、去重和本主播模板保护保留。

`/api/automation/health`区分扫描是否真正成功和进程健康，诊断仅当前进程有效。投稿V2不依赖底图或字体，提示词要求人物在右、左侧完整《歌名》、不加主播名或装饰横线；技术校验后自动继续，不做收费视觉/OCR。历史身份、失败任务和投稿不自动批量回填。

## 2026-10-08 小红泡《当你》补逐字LRC（单首维护）

- 用户发现成品目录LRC只有句时间并授权补一份。确认项目fe8513c2bb034e8f92cb6c29e8ed9c24、10月7日高置信《当你》：55行/345字均有QQ标准字时间，ASS含345个kf标签；backend/app.py原导出只写句首，并非本次判歌模型切换或逐字对齐失败。
- 只新增 /vol2/1000/video/Folia成片/小红泡-管珩心/2026-10-07/高置信/当你/当你.逐字.lrc（增强LRC），由现有alignment/render快照扣除trim_start_ms=18230，首句5000ms、末字结束175573ms。现有LDDC解析器回读55行/345字，逐字文字/开始/结束与对应成片时间完全一致；UTF-8无BOM，文件6095字节。
- 原MP4、逐句LRC、alignment JSON及render manifest的SHA256/大小/mtime均未变，不改数据库/身份、无重新渲染/上传/AI调用或服务重启；healthz正常。维护校验脚本语法通过。此为单首补导出，未修复全局后续成品LRC自动导出逻辑，未来该入口仍只生成逐句LRC。

## 2026-10-08 整场判歌主模型6.1-sol，DeepSeek备用（已部署）

- 用户要求仅切换整场ASR后的完整演唱范围分析。新增song_analysis.py，主接口复用标题TITLE_API_BASE_URL/KEY/PROXY，独立SONG_ANALYSIS_MODEL=gpt-6.1-sol；DeepSeek V4 Flash备用。主接口超时、连接、HTTP或格式失败才转备用，各一次；有效无歌/低置信/无效ID不再强行问备用。HTTP各阶段上限600秒。Whisper、Qwen、指纹身份、标准歌词字轴及默认关闭的DeepSeek歌词重排不变。
- 请求前保存timings.song_analysis的模型/provider/状态，错误仅类型/HTTP码，最终记录与songs原子保存，空结果重启复用；分析JSON/时间轴写实际请求模型，旧未记录模型的分析明确标注legacy，不冒称6.1。启用/手动整场入口接受主或备用任一已配置；规则页显示主/备用，任务页显示本次模型及备用使用，不返回凭据。
- 用现有10月8日缓存整场ASR（1442句、90分钟）只读实测：主接口167.766秒成功，返回1条候选并通过现有segment ID/时间/阈值校验，未调用DeepSeek、未写入原分析、未重新切片/渲染/投稿。该样本只验证可调用，不证明第三方真实后端或识别准确率优于DeepSeek，歌曲权威身份仍由后续指纹识别维护。
- 本地50项相关测试通过；Linux断网177项回归通过，补充后的20项新模块/编排测试也全过（含空结果重启不再分析、错误记录保留）。Python/JS语法、新镜像导入、前端模型/任务状态渲染测试通过；backend/Dockerfile已显式COPY新模块，Compose增加独立模型/超时，不复制密钥。
- 仅更新API/Web，镜像b60f1d343e271404abc993ce9aed6ce97e48ead10d2acc71b921a36d205e96b5 / 268a2966ede4245c906116b10c243d32478dafdd1a18cc1489715540628af64e。备份数据库、配置、源码及原镜像于/vol1/1000/docker/folia-video-studio-backups/20261008-song-analysis-sol；未改全局journal_mode、身份/投稿快照或历史补投范围。
- 更新前临时冻结1条尚未开始的重制，记录原status/error并在ASR接回后逐字段恢复（维护标记已清除）；转录器、模型、原生渲染器、BililiveTool容器身份/启动时间均未变。正在转录的cd739591be0e42a599cb0a0cf1477a33仍使用同一transcriber task ID，未取消或重新POST。9月遗留“下一个天亮”rendering行已只读确认22天未更新且renderer404，不将其误认活任务，不改其行/原视频。
- 上线healthz/config/规则/扫描/投稿control正常，主/备用均configured，自动投稿恢复原active及原水位/范围。网页携带鉴权返回200并提供新版本automation.js，未鉴权仍401；数据库quick_check=ok。源码/测试/文档同步NAS Git副本，不含环境密钥、数据库或媒体；本次未推送GitHub。

## 2026-10-08 《遇见》歌词轴纠正及显式单次重投（重制中止，未上传）

- 后续检查：修正版曾启动renderer13632a3e79e44eba86205ec0a45a42dc，但单首驱动在snapshot调用失败时停止；主jobs后来为failed/error="database is locked"，没有创建0815fcdd605b57aa8a1bf40f9eb89a59投稿行或取得新task/AID/BVID。本次模型切换未追加第三次重制/上传，也未将“驱动已启动”当作重投成功。下方是此前对轴及排队记录，原稿、原封面和原身份继续保留；数据库锁及结果交接需另行核对修复。

- 用户反馈 BV1bzHS6LEwe 歌词不对应，明确自行删除旧稿并授权“对完上传”；本次不调用撤稿/删除接口，不扩展历史补投或重置其他任务。
- 定位原项目468a5fa3c75d4cd69434e40addfbaae7及逐帧克隆ed4ca17f79b54ebcbabd80cf3ff88929：沿用9月23日错误演唱会版kugou:272728602，首句62.713秒而原ASR约5秒、按错轴裁掉57.713秒；timing_confidence=low、cross_model_conflict=true、句字偏移差5115ms，但旧confidence_tier=high仍放行。长演唱会备注使正常版标题相似度0.2353低于逐字候选门槛0.5；不是快速/逐帧渲染的速度问题。
- 单首维护脚本repair-yujian-lyrics-and-repost.py使用现有LDDC、渲染和BililiveTool客户端，不改变运行模块/开关。只查询“遇见 孙燕姿”并选qq:8145，完整25行、两个副歌；复用已有Qwen证据，统一平台字轴shift=-20129ms，54字锚点跨155648ms、P90=266ms、句字差13ms、timing=high且无冲突。识别身份、原项目/MP4及旧稿任务ID/AID/BVID/payload保留。
- 独立修正项目b37c38a07a61575f978955555942d471，逐帧不保存MOV，裁切0–179244ms；不覆盖旧119.3秒成片，不由历史补建自动创建第二笔费用。复用原成功封面/标题/简介/合集，维护投稿id0815fcdd605b57aa8a1bf40f9eb89a59。创建新任务而非清空已完成任务，提交前持久化次数和快照，已知task ID只查询；响应丢失不自动再次POST，需检查。
- 准备校验后事务转移歌曲主任务关联（旧发布结果和payload不改，旧关联保留在备份/演唱/维护历史），唯一约束仍只允许一个主任务；维护行pipeline_version=1与自动V2worker隔离，由显式脚本查询结果。歌曲页可通过主任务指针展示修正版，不新增第二个歌曲项目。旧稿已查询state=-100/已删除，删除由用户完成。
- SQLite一致性及逐行备份/data/lyric-repairs/20261008-yujian；10项本地/维护安全测试及Python语法通过（坏轴拒绝、主关联唯一、旧结果不清空、只提交一次、已接收只查询、响应不明不再POST、终态渲染失败停机、完成结果只恢复）。旧项目逐字段一致、旧投稿身份/快照/task/AID/BVID/次数及封面SHA一致。独立运维进程只读确认已存在的表后标记schema ready，不在生产重任务旁重跑迁移DDL；不改变API模块或数据库journal_mode。
- 首次修正版renderer895b73332a894526844deabe3ebba658实际failed/Chromium DevTools启动失败，主jobs仍rendering/1%（状态交接受数据库锁影响），没有产生成片或上传。确认终态后app_meta保存原错误/ID及render_retries=1，仅清理该修正版的输出状态重排；再失败即停，不重启/取消其他渲染，不能声称浏览器根因已修复。
- 固定目标NAS驱动run-yujian-repair-once.py已启动，日志/锁/PID在/vol1/1000/docker/folia-yujian-repair-20261008/；最多等待12小时，只使用现有API正常渲染队列。已完成renderer但主状态遗留时只恢复该ID；MP4/对轴技术检查通过后生成维护快照、校验，实际在BililiveTool容器检查视频stat和封面SHA，再核对旧稿已删除后只提交一次，查询AID/BVID/审核并保存result.json。不新增AI调用，不新增开机/定时常驻服务；终态渲染/准备/上传异常或响应丢失会停止并留日志，需要核对后再处理。
- 本条目前完成对轴并交给单首执行任务等待重制，尚未发起新上传；今天整场ASR已有4/30块证据，未获用户优先授权前不主动中断。结果以维护日志/result.json、新投稿记录为准，不因启动驱动就宣称已上传成功。
- 这是单首显式修正，不代表已部署全局歌词候选/旧high时间质量门槛修复；其他历史错轴仍需另行核对和授权。

## 2026-10-08 标题模型改为6.1-sol、歌词短句及持久化重试

- 用户确认切换TITLE_API_MODEL=gpt-6.1-sol，允许选已匹配标准歌词中副歌/重复段短句作标题文案，不强制意境描述。提示词限定短句摘录不超过10个汉字，不整段引用/编造歌词，身份字段和完整标题后缀保护不变。
- TITLE_TIMEOUT_SECONDS=120（HTTP各阶段等待上限），累计TITLE_MAX_ATTEMPTS=3；超时、连接错误、429、5xx可退避，400/鉴权/明确参数/非法标题直接固定标题兜底。每次prepare仅发一笔请求，title_generation_json在请求前保存attempts/in_flight、请求后保存history/retry_pending；重启保留次数，第三次失败继续封面/投稿，后续Bili或封面重试不额外生成成功标题。
- 已实测旧入口单次请求gpt-6.1-sol生成《遇见》标题10.683秒/HTTP200/格式通过，响应请求名不证明真实后端。本地66项相关测试、Linux断网新镜像141项回归、Python/JS语法及镜像模块导入通过。仅更新API/Web；运行中的《想自由》renderer ID e08839bb93b4432d80f4e4c1831eb720保留，原生渲染、模型、转录和BililiveTool容器未重启。线上control确认6.1-sol/标题3次/120秒/封面10次，自动投稿恢复active、原cutover/空名单/授权批次不变。数据库和配置、源码备份在/vol1/1000/docker/folia-video-studio-backups/20261008-cover-retry-ten，密钥不进入Git或日志。
- 显式恢复5条未提交封面网络失败，各封面2次记录不清零。奇妙能力歌/桃花旗袍/陷阱/遇见这4条未冻结payload的旧标题网络失败，原请求保留为第1次，只在原3次总上限内用新模型重试；三拜红尘凉原AI标题成功继续复用。不改其他历史失败标题/已冻结payload/已投稿或成功封面，不扩历史范围。具体新生图/上传完成结果另查队列，不因重新排队宣称已经投稿成功。

## 2026-10-08 GPT封面累计请求上限提高到10次

- 用户明确把每首歌曲项目的封面请求上限从2次提高到累计10次。统一COVER_MAX_ATTEMPTS=10，准备自动退避与实际请求边界一致；control返回上限，投稿页动态显示。准备重试接口拒绝无成功封面且已达10次的任务，已有成功封面继续复用；鉴权/额度/明确参数错误仍终态，不扩大真实上传重试上限。
- 实际诊断5首（奇妙能力歌、桃花旗袍、三拜红尘凉、陷阱、遇见）最后均SSL握手UNEXPECTED_EOF_WHILE_READING，参考帧已存在、无生成原图；曾有上游502。诊断时未发付费请求，GET /models已恢复401响应，不证明生图稳定或必需代理。既有2次失败保留，最多再请求8次；不重置已成功封面或已接受投稿。
- 原独立版本本地62项、Linux137项回归通过；第一次部署预检因正在普通渲染《血腥爱情故事》在任何变更前退出。该歌完成后与本次标题修复合并上线，最终API镜像1ab05cd1f9d31b60ef37f918d477239127cab2d106efa7c54ae9d4a7c8115b69、Web镜像6aa740804757462cd99d64f507b38f892c111acdb80ef719dea3967b27b7e5f4，141项Linux回归通过。真实恢复5首网络失败队列、每首旧2次保留；成功资源与已接受任务不改，上线watermark不扩大。

## 2026-10-08 芒芒重制失败一次性恢复/重试

- 诊断6条失败：奇妙能力歌、桃花旗袍为主API数据库锁/状态交接失败，原生renderer实际上completed且MP4存在；遇见、多余的解释甜妹版、单身情歌为Chromium DevTools启动失败；表白Remix旧renderer ID 404（任务保存在渲染器内存）。日志中的DBus警告不等于已确定浏览器故障根因；本次不修改SQLite journal_mode或重启服务。
- 用户明确授权重试一次。当前仍有重制和录播任务在处理，故不部署/重启API或渲染器，不新增自动无限重试。保存显式6首运维流程 retry-mang-failed-revisions-once.py：先只读预检源文件/当前响度/已投稿去重/renderer状态，完成结果FFprobe确认音视频与时长后复用原resume_render_revision接回；failed/cancelled/确切404才允许清除克隆旧ID、原队列重新render一次；网络异常/未知状态不清除ID。保留旧失败/ID/行快照，不修改权威身份、原项目/视频、投稿payload或成功封面。
- 实际接回奇妙能力歌renderer33ddfe8558c14d858256e43f72095254、桃花旗袍rendererb9223546760a4b1e99911d76121c279a，两个render_revisions completed且原交接函数enqueued。遇见、表白Remix、单身情歌重排为pending，仍按原录播日期优先、现行任务不抢占。多余的解释平均−36.4/峰值−4.7被当前OR规则排除，不重跑、不重开投稿。
- 每首app_meta.render_revision_retry_once:<job_id>保存count=1、动作、请求时间和旧失败/ID；BEGIN IMMEDIATE保护一次性认领，重复执行只读返回already_requested。原队列单次失败仍停止，需要另行授权/修复，不宣称已实现可视化重制重试或所有未来失败自动重试。动作前行级备份及结果位于/data/render-retry-backups/20261008-once；脚本是外置一次性运维工具，不是新增Docker运行模块，宿主部署目录保留可重新拷贝执行。
- Python语法及5项运维策略单测通过（完成复用、终态/404重建、活动只恢复、低响度排除、仅显式6首且无直接上传/渲染POST）。保持原自动投稿active，未改水位/名单、未取消当前逐帧或ASR任务；本次没有修复数据库锁和浏览器启动根因。源码运维工具与文档同步NAS Git副本，未推送GitHub。

## 2026-10-08 投稿歌名去除括号备注

- 上线核对：SQLite完整性ok，所有已有投稿任务/歌曲项目/封面与备份一致、所有原始身份未变；运行中的外部 renderer ID 保留。网页鉴权健康、自动扫描健康接口、投稿控制接口均200，已恢复自动投稿 enabled=true，芒芒合格重制队列继续，仍保留新OR响度阈值与原范围。

- 用户要求歌名圆括号及其中内容不需要。新增 title_generation.song_display_title（现有模块内，无新运行文件），确定性删除中英文圆括号内容，支持连续/嵌套/混用闭合。牛仔很忙 (cover: 周杰伦)→牛仔很忙，公主殿下 (cover: 崔洋)(完整版)→公主殿下。空结果或括号未闭合在付费请求前停止准备。
- AI标题输入和严格校验/固定兜底、GPT封面提示词、tags、模板简介title变量、BililiveTool分P标题统一用派生展示歌名。原identified_title、identified_artist、identity_source和song_key不改，不修改已接受/已投稿记录、已冻结payload或成功封面，不重置次数额外生图；无历史歌曲合并、重渲染或撤稿。
- 106 项断网 Linux 回归及 Python语法/增量镜像导入通过，含中英文/混用/嵌套备注、空结果、AI/兜底一致、真实适配payload/简介/封面prompt、权威身份和去重键不变、缓存复用。仅更新API，原生渲染/模型未重启；标准Dockerfile已COPY两个既有模块。备份 /vol1/1000/docker/folia-video-studio-backups/20261008-display-song-name，旧镜像 folia-api-before-display-name:20261008 保留。源码、测试、文档同步 NAS Git副本，不含密钥/数据库/媒体，未推送GitHub。

## 2026-10-08 响度宁错杀档：任一低电平排除

- 最终健康/自动扫描/控制接口经网页鉴权均200，SQLite完整性ok；原项目、旧V1、已接受投稿记录、封面和生成次数与备份一致。已恢复 active，空白名单、原cutover和授权批次保留，合格逐帧版继续按原录播日期新到旧。原生渲染《第57次取消发送》ID acd4cb91be8f4922830ff3c9af323dc5 仍相同；核对时重制完成11、失败3、等待25、运行1、跳过2。

- 用户明确要求“有一个满足就排除、宁错杀不放过、继续提高标准”。当前默认平均 RMS ≤−30 dB **或**峰值 ≤−15 dB 即 skip；版本 quiet-clip-v2-any，settings.logic=any。原 −32/−18 且同时满足规则仅作历史记录。继续使用免费 FFmpeg volumedetect，不是 LUFS 或主播身份分类器；正常响度背景原唱仍可能漏过，真实演唱也可能误拦。
- 修改前通过原控制 API 暂停新生图/提交，未取消已接受任务。遗失的心跳当时已经 completed，AID117402142508196 / BV133HU61Euf；新规则真实解码 −37.0/−9.1 dB 为 skip，但不撤稿、不重投、不篡改已投稿快照。
- 对已授权芒芒批次 33 首重新判定，只有 source path/size/mtime_ns 完全一致才复用先前真实 FFmpeg 测量。未提交新增排除《忽然之间》−38.3/−1.8（未开始的重制克隆 skipped）和《多余的解释（甜妹版)》−36.4/−4.7（既有失败保留、不清错）。另 25 首未提交通过（其中仍有重制失败）；已经接受的歌曲/投稿/封面不改。原项目、原 MP4 均不改，不扫其他历史库。
- publish_v2.eligible 在准备/提交边界使用当前规则重算已有电平，旧 AND pass 不再放行，测量缺失/非法则拒绝；授权批次还要求当前版本、配置和输入 stat。拒绝不产生生图或上传，已成功封面/次数保留。新切片仍在建立项目前筛查，不进入识别/歌词/Qwen/渲染/投稿。
- 96 项断网 Linux 回归、Python语法和增量API镜像构建/导入通过；含任一低值/等号边界、旧缓存失效、旧 pass 拦准备/上传、成功封面和原 MP4 不变。真实解码遗失的心跳、目及皆是你为 skip；一笑倾城、鱼仔、慢歌1通过，媒体 stat 不变。仅更新 API，不重启原生渲染/模型，当前 renderer ID 保留。备份 /vol1/1000/docker/folia-video-studio-backups/20261008-any-performance-gate 与 /data/publish-policy-backups/20261008-any-performance-gate；源码/测试/文档同步 NAS Git 副本，未推送 GitHub。

## 2026-10-08 恢复芒芒逐帧批次投稿、新日期优先

- 用户最新明确恢复芒芒投稿，优先原演唱日期新的、仅投稿重制成功的版本。复查已绑定的 Bili 房间 25984441、preset s9iw1rmff2，以及模板合集 9136587 / 小节 10207730；再读 B 站现有稿件排重。批次 `26e223f70d714588b6e40cdca70e9fca` 42 首中 33 首未投高置信且严格响度通过，5 首已投不重投、3 首本地对齐不投稿、《望穿秋水》低响度禁投且未开始的克隆标 skipped，原项目/切片/成品不改。33 首中 3 首现重制失败继续保留错误，不回退快速版、不擅自重建丢失的 renderer ID；其余 30 首随成功重制继续。
- rollout 新增明确 `{batch_id,profile_id}` 的 `authorized_render_batches`，保持 active、allowlist=[]、全局 cutover 与暂停区间不变，不降低水位、不扫其他主播历史。该批次只在 smooth 完整高置信、标记允许、归属正确规则、当前严格响度 pass 且源文件 stat 未变时绕过历史水位。页面暂停仍阻止本批付费请求/提交；有任务ID/AID/BVID仍只查询。
- `publish_jobs` / `render_revisions` 各新增 `priority_at` 默认0，实际原录播开始时间作为优先级，不篡改 created_at/finalized_at 或识别身份。已接收/提交中的投稿优先恢复查询，未提交新版按日期降序；其他无优先级任务保持原先顺序。渲染中任务不抢占，剩余高置信重制先新日期；已完成新版之间优先新日期，不阻塞等待尚未完成的歌。
- 已通过原交接函数将4首已完成合格新版入队，首首《泪桥》原录播 2026-10-07 09:05:22，AI标题“🌉把没说完的话，留在桥的那头｜《泪桥》｜【芒芒_Mou】翻唱”，开始准备且生图1次；检查时牛仔很忙已重制成功入队，下一首正在重制《好像掉进爱情海里》。投稿开始不等于上传完成，结果后续补记；所有请求仍沿用原两次上限和成功封面缓存。
- 最终《泪桥》completed：task a1379456-8657-4460-ba9e-c9f55f465e25，AID 117402125732195，BVID BV1gVHU65E5P，BililiveTool主任务100%，生图/提交均1次。冻结payload继承合集9136587/小节10207730、简介2026.10.07，源删除false；共享逐帧MP4与封面在BililiveTool容器可读。牛仔很忙上传task 9cab9ec4-5d1e-4110-ad9c-970707e6374b已持久化，生图/提交各1；遗失的心跳开始准备，其余继续队列。SQLite完整性、所有原项目不变、旧V1逐项不变及已接受任务ID/AID/BVID/次数/快照不变通过，Nginx鉴权健康/新范围JS 200、未鉴权401，自动扫描ok/错误0。3首失败重制未清错；原《目及皆是你》不撤稿不重投。检查时重制完成10、等待27、运行1、失败3、跳过1。
- 93 项断网 Linux 回归、Python/JS语法、增量API/Web镜像与导入通过；新批次授权包含错误主播、非smooth、低置信、响度skip、源改变等拒绝测试，重制/投稿排序测试保留原创建时间。只更新 API/Web，不重启模型/原生渲染；原《牛仔很忙》render ID `6e90ec93a81a47a8baf564cba73ebbb2`保留。首次部署探针抢在启动迁移完成前报告字段缺失，启动健康后确认两个priority字段存在，旧投稿逐项不变，无迁移丢失；探针已改为等待HTTP健康。备份 `/vol1/1000/docker/folia-video-studio-backups/20261008-mang-resume` 与 `/data/publish-policy-backups/20261008-resume-mang-revised`，旧镜像 api/web-before-mang-resume 保留。源码、测试、页面及文档同步 NAS Git 副本，不含凭据/数据库/媒体，未推送 GitHub。

## 2026-10-08 响度库存核对与严格档上线

- 只读核对 4 位主播自动成片（逐帧克隆不重复计数）：未投完整演唱 300 次；按权威身份去重 243 首，重复额外演唱 23 次，缺权威歌名 34 次。测完 462 个有项目切片及 7 个未建项目切片，错误 0，视频 size/mtime 未变；旧规则筛出《望穿秋水》《改变自己》及原已短片跳过的《当你》。报告保存在 `/data/audits/unpublished-20261007-222539/`（目录名 UTC，报告时间上海 2026-10-08 06:25:40），未恢复历史投稿/生图或改变项目状态。
- 用户明确没有需要保留的轻唱、允许更严格。默认阈值由平均 RMS ≤−38、峰值 ≤−25 dB 收紧为平均 ≤−32 **且**峰值 ≤−18 dB；不是改成 OR 或声纹检测。现有 469 个测量回算不合格 9 个（新增 6），其中 7 个有成片。额外为清歌喵《白色风车》《今生你作伴》《聊表心意》《第二杯半价》《从头再来》及短片《打工人》。这些仍只记录核对结果，历史已完成项目不自动改判/重跑；新切片在创建项目前执行严格档。
- 严格镜像真实解码《目及皆是你》−45.0/−30.9 dB 为 skip；《一笑倾城》《鱼仔》《阴天》《慢歌1》实际抽取演唱样本均 pass，媒体 stat 不变。现有默认缓存因 settings 不同重新核对；90 项断网 Linux 回归通过，新增严格边界/真实样本电平和旧缓存失效测试。较响原唱仍可能漏过，整体偏轻的真实演唱也可能误拦，结果仍只称疑似背景音乐。
- 仅更新 API 内 `performance_gate.py` 默认值，无新依赖，Dockerfile 已 COPY；运行环境没有阈值覆盖。备份 `/vol1/1000/docker/folia-video-studio-backups/20261008-strict-performance-gate`，旧镜像 `folia-api-before-strict-gate:20261008` 保留。原生渲染服务未重启，《泪桥》同 ID `0eb179ea5e8b49e49531fd603c673434` 继续运行；投稿 rollout/全部任务/封面次数/SHA 均未变，历史批次继续禁投。模块/测试/文档显式同步 NAS Git 副本，不含凭据或媒体，未推送 GitHub。

## 2026-10-08 停止历史投稿、切片低响度筛查上线

- 用户核对原演唱日期后撤销这批历史投稿。先通过控制 API 暂停新生成/提交，备份 `/data/publish-policy-backups/20261008-stop-historical/`，再将批次 `26e223f70d714588b6e40cdca70e9fca` 的 42 个克隆 `render_revision_publish=0`、交接 `publish_status=not_requested`；未接受投稿的主任务记 policy 失败，禁止准备重试重新放行，成品/切片/成功封面保留。只是取消投稿，剩余渲染队列未擅自取消。
- 停止前本批已有 5 首 completed：《慢歌1》BV1JDH16HExA、《目及皆是你》BV1JDH16HEpD、《我想要你的爱》BV17RH16UEzV、《爱情专属权》BV1fiHU6tEYC、《七月末》BV1FiHU6bENA；未删除、撤稿或重复上传。检查时无准备/提交请求在途。政策调整后旧投稿 task/AID/BVID、身份/metadata/payload、封面次数/SHA 均未变化。
- 新增 `performance_gate.py`，直接 FFmpeg 解码现有切片并用 volumedetect 测平均 RMS/峰值电平，不转码、不写视频、无模型/收费 API。默认平均 ≤−38 dB 且峰值 ≤−25 dB 才自动跳过；缺音轨、解码失败、超时或非法测量停止该首并可重试，不悄悄继续付费流程。缓存以版本/文件路径/size/mtime_ns/阈值匹配；保存 `song.performance_gate` 与 skip 原因、前端显示“切片演唱筛查”。在 `create_imported_song_job` 之前执行，skip 不创建歌词项目、不运行指纹/歌词/Qwen/渲染/生图/投稿，不改识别身份。已经完成/跳过的歌曲不自动回溯重判。
- 实测原《目及皆是你》平均 −45.0 dB、峰值 −30.9 dB，新生产函数在隔离调用中用真实切片判 skip、后续调用 0、文件 size/mtime 不变；《一笑倾城》《鱼仔》《阴天》平均 −18.6/−18.2/−18.7 dB，峰值 −0.4/−0.2/−0.4 dB，均 pass。《慢歌1》−25.9/−4.2 dB 也不会误拦。注意这是保守低响度筛查，不是声纹、主播身份或完整歌唱检测；正常响度原唱播放仍可能通过，极轻演唱也可能被误判，保留切片供人工核对。
- 默认启用，运行环境可调 `PERFORMANCE_GATE_ENABLED`、`PERFORMANCE_GATE_MEAN_DB`、`PERFORMANCE_GATE_PEAK_DB`。没有新增依赖；Dockerfile 显式 COPY 新模块。88 项 Linux 断网隔离回归通过，含真实低/正常电平解码、边界无下游调用、缓存/失败/身份保护与 policy 重试拒绝；Python/JS 语法及增量镜像构建/导入通过。
- 只更新 API/Web，转录/模型/原生渲染服务不重启。上线时唯一活动外部逐帧任务《我想我不够好》ID `216dfb29b8bf4b23b37a4a98269d6ebe` 保留，API 重启后仅恢复查询同 ID、进度继续。部署备份 `/vol1/1000/docker/folia-video-studio-backups/20261008-performance-gate`，旧镜像 `folia-api-before-performance-gate:20261008`、`folia-web-before-performance-gate:20261008` 保留。SQLite 完整性、原项目不变、Nginx 鉴权 API/资源 200 与未鉴权 401 已核对，未以测试产生生图/投稿。
- 上线后恢复未来新成片自动投稿，mode=active、allowlist=[]、cutover=`1791411419.8232932`，历史批次继续禁投，暂停区间持久化；没有重新开放旧 V1 或全库历史。检查时重制完成 6、失败 3、等待 32、运行 1，这些不代表仍会投稿。源码/测试/文档同步 NAS Git 副本，不含凭据/数据库/媒体，未推送 GitHub。

## 2026-10-08 取消测试白名单、启用自动投稿

- NAS 恢复后按用户明确授权，通过现有 `/api/publish-v2/control` 启用自动投稿。持久化 rollout 为 `active`，`allowlist=[]`；接收水位为已授权批次 `26e223f70d714588b6e40cdca70e9fca` 的创建时间 `1791378780.944397`，而不是本次启用时刻，确保先完成的三首也放行。执行前再次核对水位之后的完整成片仅来自这批重制，未开放更早全库历史补投。后续合格新成片自动处理，不需逐首白名单；页面开关读取为 enabled=true，仍可暂停/恢复。
- 原 PUBLISH_ENABLED/AUTO_PUBLISH_ENABLED、严格高置信、身份保护、主播模板、同主播同歌去重、两次封面上限和已接受任务不重复提交均保留；旧 V1 的 50 条记录逐项与此次备份一致，不自动迁移或重新提交。备份 `/data/publish-control-backups/20261008-no-test-whitelist/` 包含启用前 SQLite 一致性快照及控制状态。仅修改持久化控制状态，不重建/重启生产服务。
- 实际检查《慢歌1》已完成封面并交给 BililiveTool 上传，task ID `58eb5191-8050-4ea0-a105-18a829b70ee7`，提交 1 次、封面 1 次；尚未取得 AID/BVID，不宣称投稿已完成。《目及皆是你》正在生图（1 次），《我想要你的爱》等待；其余重制成功后自动续入。43 项投稿控制/V2隔离测试通过，运维脚本语法通过，SQLite integrity_check=ok、API/自动扫描健康。
- NAS 全栈重启后另有三首重制失败保留待修：《表白 (Remix版)》旧渲染 ID 丢失，《遇见(央视星光璀璨中国巨星演唱会)》《多余的解释（甜妹版)》浏览器启动失败。诊断进程初始化 schema 后持有长事务导致《爱情专属权》数据库锁失败，已修正独立核对脚本的事务范围，并查询确认原 renderer ID `f41a0d5fb4734394b658271080180512` 仍运行后恢复为待续接，不创建新渲染。检查时重制完成 3、失败 3、待处理 35、运行 1；失败不影响原 MP4，不因放开投稿范围自动清空错误或重复生图。
- 最终回读《慢歌1》已 completed，AID `117401806964266`、BVID `BV1JDH16HExA`，仍仅提交/生图各 1 次；《目及皆是你》已取得 task ID `1d8c1e4a-1cd7-4ffe-b36b-6f45f674a1fe` 并 uploading（提交/生图各 1），《我想要你的爱》生图 1 次正在准备。active/空测试名单、API 健康、SQLite 完整性及旧 V1 50 条不变再次确认。控制与状态文档已同步 NAS Git 副本，未推送 GitHub。

## 2026-10-07 芒芒逐帧默认与历史重制队列

- 后续用户明确要求取消测试白名单，允许本批逐帧重制及未来合格成片自动投稿，仍保留高置信/身份/主播模板/去重保护、隔离旧 V1 队列。执行前 NAS `100.111.1.11` 连续 SSH 超时，Tailscale 显示节点离线且 ping 无回复；尚未变更线上开关或水位。已准备独立运维脚本，拟通过现有 control API 启用，再以本批起点为水位并清空测试名单，防止漏掉先完成的《慢歌1》且不扫更早历史库。必须恢复连接后先核对状态再执行；这条授权记录目前仅本地，未能同步 NAS。
- 用户授权芒芒默认逐帧生成、不保存 MOV，并补充要求成品进入投稿队列。已仅将芒芒规则 `bc87122ccfbb4403a15efafb3ae01cc6` 的 `render_output_mode` 改为 `smooth`；其他主播仍 `fast`。自动流水线页面新增单规则 MP4 模式设置及历史重制进度。
- 显式核对原完整成片、权威歌曲身份、缓存歌词时间轴和实际共享路径，并只读核对 BililiveTool 当前稿件，排除已投稿《一笑倾城》《日不落》《离人赋》《阴天》《鱼仔》及同主播重复演唱。批次 `26e223f70d714588b6e40cdca70e9fca` 共 42 首：39 首满足严格高置信投稿门槛，完成后进入 V2 投稿队列；《表白》《大圈圈》《身骑白马》3 首本地对齐版仅重制，不升级置信度、不投稿。
- 新增 `render_revisions.py` 和独立持久化队列，复用原源切片与歌词时间轴，不重新 ASR/识别/搜词。克隆项目具名插入，保留原身份和时间轴，独立输出目录，`keep_alpha_mov=false`。已有 renderer ID 只恢复查询，不重复创建渲染；投稿交接失败与成品失败分离，可独立重试。新模块已显式加入 backend/Dockerfile。
- 已启动后台串行重制。检查时《慢歌1》逐帧进度 76.4%，另外 41 首待处理，尚不能宣称全部完成；42 个原项目及 MP4 size/mtime 均不变，克隆权威身份/歌词时间轴逐项一致。批次与原输入快照保存在 `/data/mang-smooth-batch-20261007.json`，不进入 Git。
- 投稿入队不代表扩展发布授权：仍保留原 `acceptance` 两首白名单，未 activate，新的高置信重制任务入队后等待当前范围放行，不因此启动全量付费生图或真实上传。未提交的同歌曲主任务可以改指向新逐帧成片并复用已有封面；有任务 ID/AID/BVID 或已接受提交的主任务绝不替换。
- 相关 118 项 Linux 隔离测试及另外 4 项实际路由测试通过（共 122 项），Python/JS 语法和镜像模块导入通过。只更新 API/Web，部署前确认重任务空闲，不重启转录或原生渲染服务。备份 `/vol1/1000/docker/folia-video-studio-backups/20261007-smooth-revisions`；旧镜像 `folia-api-before-smooth:20261007`、`folia-web-before-smooth:20261007` 保留。SQLite 完整性与自动扫描健康，浏览器只读检查确认芒芒逐帧选项、42 首进度和入队说明。检查时原 53 条投稿任务及封面次数不变，未新生图/上传。
- 最终检查首首《慢歌1》已完成并交接入队：新项目 `d4aa0a80d884418dbe3f5c01e8c116f4`，投稿任务 `02ceec5358734adf98eb78144702fefa` 为 V2 `pending`、`publish_status=enqueued`，封面次数/提交次数均 0，无 BililiveTool 任务 ID。实际 MP4 为 H.264/AAC、1920×1080、30fps、92.933 秒、58,039,490 字节，新目录没有 MOV。队列转为完成 1、运行 1、等待 40，《目及皆是你》接续逐帧处理；原 53 条投稿记录/封面仍与备份一致，总任务数因新增入队成为 54。源码/测试/文档同步 NAS Git 副本，未推送 GitHub；临时只读检查页面/服务已关闭。

## 2026-10-07 投稿V2单首真实上传验收

- 用户授权补充可视化自动投稿开关，已上线API/Web：“歌曲项目与投稿记录”顶部提供启用新成片/暂停、测试模式暂停按钮、范围与上海时间显示，并确认AI费用和真实投稿。GET/POST /api/publish-v2/control，严格boolean，首次启用要求两首完成取得AID且环境总开关/封面密钥有效；旧activate共用检查。rollout持久化paused及暂停区间、首次水位；重复启用不移动水位，重启保留，恢复原队列但不补投暂停期间成片。暂停在标题/选帧/提交请求边界再次检查，已经发出的请求可完成，已提交上传/审核继续查询。相关76项测试及JS语法通过，API/Web增量镜像成功；标准Dockerfile原已COPY修改模块，无新运行模块。窄屏浏览器只读验收确认开关可用但未开启，截图output/publish-control-20261007/page.png；正式Nginx静态文件读取权限修正后首页/JS/CSS/control鉴权200、未鉴权401，API/自动扫描健康。数据库/源码/配置备份/vol1/1000/docker/folia-video-studio-backups/20261007-publish-control，旧API/Web镜像保留；原投稿任务状态/身份/metadata/payload/任务ID/AID/BVID/提交数及封面路径/SHA/生成次数与备份一致，无新生图或上传。仍acceptance白名单、未activate，启用留给用户页面操作。源码/文档同步NAS Git副本，未推送GitHub。

- 用户核对提示词并授权部署AI标题。新增title_generation.py，使用独立环境密钥及同站/chat/completions，请求gpt-5.6-terra；只润色外围文案，严格保留歌名/主播后缀、单行80字符。一次请求、45秒HTTP超时，鉴权/额度/网络/格式错误均固定标题兜底。title_generation_json及标题在封面前保存，重启/后续失败复用，已冻结payload不重新生成。相关63项测试通过，断网增量镜像构建成功，标准Dockerfile显式COPY新模块；仅更新API，数据库/配置备份在/vol1/1000/docker/folia-video-studio-backups/20261007-ai-title，旧镜像folia-api-before-ai-title:20261007保留。实机独立标题请求15.136秒成功：“☁️阴云落进心里，安静地听一场雨｜《阴天》｜【芒芒_Mou】翻唱”；仅测试输出，没有修改已投稿标题/数据库。SQLite完整性ok，原53条任务的身份、标题、简介、payload、任务ID/AID/BVID及状态均与上线前备份一致，V2原MP4 size/mtime不变。仍acceptance两首白名单，未activate、未生图、未上传或扩展历史补投；API健康。源码和文档同步NAS Git副本，未推送GitHub。

- 用户随后授权修正直播时间，已上线：既有recorder_identity.py新增只读recording_start_time，V2及旧准备入口均改用源录播开始时间，删除run.mtime/video_mtime/当前时间回退。按精确目录/stem匹配BililiveTool记录（兼容.flv转.mp4），以平台/房间过滤，record_start_time实际为毫秒；缺失时仅解析原YYYY-MM-DD/HH-mm-ss_命名，多个时间冲突或未知时间终止，V2在付费生图前检查。新增8项时间测试及2项V2回归，相关54项通过，增量CPU断网镜像构建成功，现有Dockerfile已COPY三个修改模块。只更新API；上线前确认唯一活动任务为兼容的外部Whisper整场ASR、无渲染/切片/投稿处理中，重启后原transcriber_job_id保留且任务继续运行。备份/vol1/1000/docker/folia-video-studio-backups/20261007-record-start-time/及旧镜像folia-api-before-record-time:20261007；API/自动扫描健康，模板合集设置保留，无新生图/上传、不修改已投稿快照。代码、测试、文档同步NAS Git副本，未推送GitHub。
- 用户要求修正芒芒模板合集。实查BililiveTool preset s9iw1rmff2的seasonId原为null、三首冻结payload也为空、稿件详情in_season=false。通过线上GET /bili/seasons确认“芒芒_Mou的歌曲合集”9136587及正片小节10207730；核对3.18.0路由后PUT /preset/video/s9iw1rmff2，仅改seasonId/sectionId，回读一致，其他模板及其他字段未变。旧模板备份/data/publish-template-backups/s9iw1rmff2-before-season-1791369995.json；后续新准备会继承合集，不自动修改已投稿稿件或已冻结payload、不重投。直播时间调查：当前formatDesc.time取run.mtime（文件修改时间）而不是开始时间；鱼仔/阴天源芒芒_Mou/2026-10-07/09-05-13_其实我超喜欢你.mp4，mtime为当日10:36:20；一笑倾城源10-35-23文件、mtime为11:01:47。现有简介只显示日期2026.10.07，与源录播目录日期一致；跨午夜或改mtime不可靠，未在此次日期询问中擅自修改时间算法。
- 本轮两首最终完成：阴天任务9012bb94-08ba-45d7-a2ad-335dc12f70f0，AID 117399172941325，BVID BV119Hk6QEFd，开放浏览；鱼仔任务c0dc7208-3288-4e46-8413-abb841555e10，AID 117399173006468，BVID BV1N9Hk6XE7f，检查时审核中。各仅提交一次；两张GPT原图/投稿JPEG均2048×1152，阴天本次生成1次，鱼仔累计2次含此前网络失败。人工查看歌名和书名号存在，风格随歌曲变化；不保证人物完全保真。两首原MP4 size/mtime不变，封面SHA一致、共享路径映射一致，BililiveTool容器均可读，删除源视频选项false，SQLite完整性ok。当前33旧ready/16旧failed/1旧completed保持隔离，3个V2completed；仍acceptance，只允许鱼仔与阴天，无pending/ready待自动提交任务，未activate。API/自动扫描健康，新的整场ASR正常运行，未为检查再次重启。源码/提示词回归及文档同步NAS Git副本，未推送GitHub。
- 用户选择GPT锁脸版，并授权再投稿两首。重新核对后选定《鱼仔》（b7d19c329e934b788dbfb1a7451ab93b）与《阴天》（bd2d92a28c174477a1ccd9cd2824df0f），均高置信完整MP4、无身份疑点、芒芒模板已绑定、未提交/未重复。显式将acceptance白名单替换为这两首，不activate、不放行其他历史成片；已完成一笑倾城记录不变。提示词改为锁脸型/五官比例/瞳色/发型/标志配饰，允许表情/视线/动作/姿态变化；新增提示词回归，相关44项通过，CPU断网增量镜像构建成功。备份/vol1/1000/docker/folia-video-studio-backups/20261007-face-prompt-two/含DB一致性快照/旧模块文档，旧镜像folia-api-before-face-prompt:20261007保留。只更新API，重任务及队列空闲，网络免费探测401；两首已入准备队列，最终结果待记录。
- 用户继续授权GPT/Grok各一张锁脸对比（独立预览，不替换封面、不投稿、不改生产提示词/次数）：同一8.8081秒视频参考帧，同一提示词要求脸型/五官比例/瞳色/发型/标志配饰不变，允许表情/视线/动作/姿态变化。请求gpt-image-2返回2048×1152、102.71秒；沿用此前验证的Grok JSON编辑结构，请求grok-imagine-image-2.0返回2816×1584、357.48秒，各仅一次且无重试。原图和完整无密钥记录在/output/publish/preview-tests/yixiaoqingcheng-face-20261007/{gpt,grok}/。人工查看两张歌名/书名号均存在，人物面部仍有一定重绘；Grok文字下方出现装饰拖笔，不能宣称完全满足人物保真或禁横线。请求模型名不证明上游实际模型。
- 上传后用户另行授权一张放宽人物约束的独立对比图：沿用视频参考帧与GPT接口，仅保持人物主体/辨识度，允许动作、姿态、表情自然发挥；明确不替换已投稿封面、不再投稿、不重置歌曲项目2/2计数。记录及原图位于/output/publish/preview-tests/yixiaoqingcheng-relaxed-20261007/，单次请求117.12秒，返回2048×1152。人工查看人物有持麦/伸手动作，歌名字形可读，但漏了要求的《》；此图仅供比较，生产提示词尚未更改。
- 用户恢复代理后授权只测试一首。NAS API容器免费GET /models返回401，确认HTTPS连接恢复；只通过准备重试接口放行《一笑倾城》，复用8.8081秒的1920×1080参考帧。累计生图次数2/2（第一次为此前网络失败），本次返回2048×1152原图及同尺寸JPEG，未本地叠字，未追加请求。
- 《一笑倾城》继承芒芒模板并完成真实校验/上传：标题“芒芒_Mou《一笑倾城》｜直播翻唱”；BililiveTool任务2815b94f-ba4b-4484-8986-4627e3bdc96d，提交次数1，AID 117398954838812，BVID BV1anHC6PEe7，上传100%，检查时审核中。投稿完成与审核状态分离，不因审核中重传。
- 实际审计原MP4大小/mtime未变；《鱼仔》保持failed、生图1/2、提交0，无额外测试或历史补投。上线仍为acceptance，两首白名单中的另一首尚未验收，未调用activate、未开放未来成片自动发布。以下实施记录中的网络阻塞是此前状态。

## 2026-10-07 投稿V2实施与待验收

- 新增publish_v2.py、song_projects/song_performances及投稿版本/上传恢复字段；身份快照不读歌词/手工标题。绑定平台房间去重、明确歌手冲突停住，重复演唱不再生图。已完成日不落进入已投稿去重记录，即使稿件删除不重投。
- worker只领取pipeline_version=2，旧任务隔离。原33 ready不动；两首白名单从原19 failed中显式迁入，剩17旧failed不动。只允许一笑倾城（3d6f5fd9bd8d4a918414ef0317c0dbc6）、鱼仔（b7d19c329e934b788dbfb1a7451ab93b）；已重新核对完整MP4、output/alignment均high、无身份疑点、芒芒preset s9iw1rmff2已绑定。两首取得AID前禁止activate；未来只放行output.finalized_at高于上线水位的成片，不能用修改updated_at误补历史。
- 免费选帧均完成1920×1080 PNG并缓存；每首GPT尝试计数1/2。当前NAS对codex789 HTTPS握手SSL EOF，未取得生图响应、未创建上传任务；两首已停为准备失败，保留参考帧/计数，不能重置计数扩大测试。NAS mihomo为TUN auto-route，默认自动选择显示套餐已过期；普通curl可能仍被TUN接管，尚不能据此断言服务必须使用代理。电脑既有代理不带鉴权GET models返回401，说明能到达服务。对NAS网络规则的变更待用户授权，未修改代理配置。
- 请求gpt-image-2、单张2048×1152/high、600秒、无隐藏重试，付费并发1、每首最多2次，发出前持久化次数；成功原图/JPEG/SHA复用，后续BililiveTool故障不会重新生图。API密钥只NAS .env/运行环境，payload/日志/Git不含凭据。
- 真实3.18.0接口已从线上包核对：task列表{list,runningTaskNum}、upload返回taskId、父任务completed.output为AID、archive详情另取BVID/审核。已知taskId丢失只报错，不重投；无ID中断先可靠匹配、最多再提交一次，保留响应丢失重复风险，不引入submit_unknown。真实上传、审核与生图尚未完成端到端验收，不能宣称已验证。
- 272项后端测试在断网CPU隔离容器通过，含新22项V2回归；JS语法检查通过。新模块加入标准Dockerfile；标准全量构建遇NAS PyPI SSL EOF、nginx仓库401，部署复用既有依赖镜像增量COPY业务代码，API新模块导入验证成功。只更新API/Web，其他转录/模型/歌词/渲染容器不重启；上线前重任务/自动队列空闲，API及自动扫描健康。
- 管理页已改为歌曲项目与投稿记录，显示模板/人物区域、参考帧、封面、演唱归档、生成次数、上传进度/BV/审核/准备与上传失败、旧任务隔离。浏览器只读检查已确认4个preset、芒芒绑定、其他主播未绑定、两首1/2失败记录和51条旧记录；临时测试不改变生产鉴权。NAS SSH禁止端口转发，不能依赖SSH隧道访问；只读页面检查通过SSH命令读取API绕过转发限制，不修改SSH设置。
- 备份：/vol1/1000/docker/folia-video-studio-backups/20261007-publish-v2（SQLite一致性快照、compose/.env、backend/web/docs，凭据备份权限600）；保留旧镜像folia-api-before-publish-v2:20261007与folia-web-before-publish-v2:20261007。当前AUTO_PUBLISH_ENABLED=1仅白名单门控；两首为failed且无自动重试，不会运行旧ready或扫全库。待网络恢复后用准备重试复用参考帧，剩各一次生图机会，再完成上传验收并开放未来水位。

模块协议、数据/接口与回滚详见modules/automatic-publishing.md。

最终更新已再次仅重启API/Web：重启前后均为33旧ready、17旧failed、1旧completed、2 V2网络准备失败，两首生图次数仍各1、提交次数0、BililiveTool bili任务数0；视频size/mtime均与持久化快照一致。源码与文档已同步NAS Git副本，保留原有免费选帧改动，不包含.env/数据库/媒体；本轮不推送GitHub。全量272项复测通过。

最终实机检查：BililiveTool容器两首共享MP4均可读，SQLite integrity_check=ok；新版首页/JS/CSS/歌曲项目API经生产Nginx鉴权均200，未带鉴权401。镜像内四个投稿/选帧模块编译通过；实际浏览器只读检查含窄屏歌曲项目主视图，截图保留在本地output/publish-v2-check-20261007/publish-page.png。临时页面服务器和测试连接在检查后关闭，不留额外公开端口。

## 已上线

- 2026-10-07：新增独立免费参考帧模块 `backend/cover_frames.py`，12 张候选、按主播区域亮度/清晰度评分、近似去重、原分辨率 PNG、持久化时间点及缓存复用；11 项单测和语法检查通过。NAS 断网限 1 CPU/512 MiB 隔离容器验证芒芒《一笑倾城》与小红泡《喂猪》，芒芒耗时 9.17 秒；小红泡全画面初测 11.47 秒，配置实际人物区域后复测 10.59 秒、选 17.842103 秒。均生成 1920×1080 PNG；第二次直接复用，原视频大小/mtime 不变。Dockerfile 显式 COPY 模块；源码独立交付，不启动自动选帧 worker，不接旧模板叠字 prepare_publish，不调用付费生图或投稿，不修改数据库/身份/ASR/歌词/渲染。当前 API `/healthz` 健康且 `auto_publish_enabled=false`。区域示例为芒芒、小红泡按实际画面配置；不能判断闭眼、遮脸或身份，其他主播区域与批量效果仍待核对。详见 `modules/cover-reference-frames.md`。

- 2026-10-06：完成第一轮代码整理。以 NAS 当前源码为基线更新 ARCHITECTURE、ASR 模块、预览渲染说明、README/索引，新增 CODE_MAP；历史状态记录保留并标明不得当作现行规则。新增 automation_runtime.py 与 `/api/automation/health`，只读记录扫描开始/成功/异常类型、规则/合格文件/入队计数及耗时，区分未开始、线程停止、过期、扫描中和失败；诊断状态不持久化、不改变入队决定，Dockerfile 已显式 COPY。修正 Tempera 预览测试中遗留的 0.5 断言为已上线的 1.0，快速导出仍测试 0.5，生产渲染代码未改。隔离无网络容器中 239 项后端测试全部通过（含 4 项扫描诊断测试）；Python 编译、Compose 配置与主 API 镜像构建通过。只更新 studio-api，转录/模型/渲染容器保持运行；线上检查线程存活、scan.status=ok、首次扫描 3 条规则/207 个合格文件/0 个新增入队、耗时 1.115 秒，自动 ASR 继续运行，AUTO_PUBLISH_ENABLED=false。未改数据库结构、歌曲身份、歌词算法、封面或投稿范围，未批量重跑历史任务。源码与 NAS Git 副本整理为同一基线，不在本次执行 GitHub 推送。备份：`/vol1/1000/docker/folia-video-studio-backups/20261006-code-organize/`（deployed-before.tar.gz、git-before.tar.gz）。

- 2026-10-06：Qwen 强制对齐改为离线加载。此前自动歌曲的逐字对齐在查询 Hugging Face `processor_config.json` 时遭遇 SSL EOF，导致 HTTP 500、零字锚点及后续跳过。worker 在依赖导入前固定 `HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1`；将仓库名仅从本地缓存解析为完整快照目录，检查关键模型/processor 文件后传入 Qwen，保留 CPU/float32 和现有模型卸载策略。Workerfile、Compose 同步设置离线环境；缓存缺失或关键文件为空时明确失败，不运行时下载。新增 `backend/test_worker_offline.py`，4 项缓存回归测试通过，镜像构建及 Compose 配置检查通过。在 `--network none` 的独立新镜像容器中读取既有《如果有来生》切片的 14.24 秒真实音频，模型加载与对齐共 72.66 秒，返回 11 个正时长字时间戳；结果保存于 `work/qwen-offline-check-20261006/result.json`（仅验证离线可用性，不代表歌词识别准确性验收）。用户已允许中断任务，切换时停止 API、转录器和 worker，保留原数据库/录播/成片并恢复这三项服务；没有批量重跑历史失败场次。代码与文档上线前备份：`/vol1/1000/docker/folia-video-studio-backups/20261006-qwen-offline/code-before.tar`。本次不改投稿、渲染、歌词评分或其他已知数据库锁问题。

- 2026-09-28：新增第五工作区“投稿管理”。按自动流水线锁定的主播逐一设置 BililiveTool 投稿模板、封面标题字体（默认思源黑体，可选思源宋体或字体库上传字体）和各自的封面底图（`data/cover-templates/<规则 ID>/`），可填试用歌名生成封面预览；统一管理字体库（上传、删除上传字体，内置或仍被歌词项目/规则/封面引用的字体拒绝删除）；显示最近 20 条投稿准备任务，失败可重新准备。流水线规则表单移除模板下拉，新建规则模板为空，卡片提示“去投稿管理”。封面不再使用 `cover_templates/generic` 占位图，也不设公共兜底：主播没有底图时准备任务失败并提示上传。内置封面字体改用 Noto CJK 简体中文字形（原先误用日文字形）。**当前四位主播都还没有封面底图**，在上传前新成片的投稿准备会失败（自动上传仍关闭，不影响成片）。核验：后端 `test_publishing`/`test_automation`/`test_font_assets` 37 项通过，全量 231 项仅已知无关的 Tempera 预览测试失败；Python 编译、`node --check`、Compose 配置通过。NAS 内部临时无认证容器（仅 127.0.0.1、测试后删除）配合无头 Chromium 实测：进入页面、给芒芒上传测试底图、界面保存宋体后接口确认、用底图生成 1920×1080 预览、改回默认、确认框删除底图、流水线卡片 3 个“去投稿管理”链接跳转，以及 390 px 手机宽度 4 列底部导航无横向溢出，均无页面报错；测试数据已复原（芒芒模板 `s9iw1rmff2`、默认字体、0 张底图）。部署时小红泡整场 ASR 正在转录，仅以 `--no-deps` 重建 `studio-api`、`studio-web`，API 重启后继续跟踪原转录任务。数据库新增 `automation_profiles.cover_font_id` 列。备份：`/vol1/1000/docker/folia-video-studio-backups/20260928-publish-page/`（含 SQLite 一致性快照）。

- 2026-09-27：上线投稿模板“未选择不回退”修正。此前线上仍有三处回退到全局默认 `s9iw1rmff2`：规则列表响应、`ensure_publish_job()` 创建准备任务、创建/更新规则接口；前端编辑旧规则时也会用 `default_id` 预选芒芒模板，直接保存即误绑。现规则列表如实返回空 preset，未选择 preset 的规则不创建投稿准备任务，新建规则必须显式选择，编辑只沿用本规则已保存的 preset，前端不再预选。线上核对：芒芒仍为 `s9iw1rmff2`，小红泡-管珩心、赛蒂娅Sentia、清歌喵（穿黑丝直播给兄弟们看）三条规则为空待选择；`/api/publish-presets` 读取到 4 个真实模板；`/healthz` 中 `auto_publish_enabled=false`。重建时自动化队列空闲。新 API 镜像挂载源码运行 `test_publishing`、`test_automation` 共 32 项通过，Python 编译与 `node --check` 通过；重建 `studio-api` 和 `studio-web`，均健康，转录/渲染/模型容器未重启。NAS 账号 `hermes` 已由用户加入 docker 组。修改前文件备份：`/vol1/1000/docker/folia-video-studio-backups/20260927-preset-fallback-fix/`。

- 2026-09-27：自动流水线规则增加“投稿主播 + BililiveTool 投稿模板”绑定。页面实时读取 `/api/preset/video` 并让每个主播选择模板，规则持久化 preset ID/名称；成片创建投稿任务时一并快照。旧规则未选择模板时等待选择，不会静默误用另一位主播的全局默认 preset，保存后由对账补建。准备阶段继承所选模板简介，并通过 BililiveTool `/api/bili/formatDesc` 展开 `{{now}}` 等变量，模板无简介时才回退 Folia 固定简介；已经冻结的历史 payload 不被静默改写。手动验收《日不落》已由 BililiveTool 完成上传，任务 `7e44efd0-3286-4c53-aeec-462d6738d27e`，AID `117342482861714`、BVID `BV1pBa86rEYc`，状态“开放浏览”。全局 `AUTO_PUBLISH_ENABLED` 继续保持 `0`，本次自动化代码仍不调用 `/api/bili/upload`。

- 2026-09-27：上线自动投稿 Phase 1，仅准备不上传。完整自动成片后幂等创建独立 `publish_jobs`，只快照 `identified_title` / `identified_artist` / `identity_source` 和主播；固定生成标题、简介、tags 及 1920×1080 模板封面，读取 BililiveTool 3.18.0 现有 preset `s9iw1rmff2`，仅覆盖 `title/desc/tag/cover`，存储不含 PassKey 的 payload 快照并通过 `/api/bili/validUploadParams`。视频和封面使用 BililiveTool 现有 `/app/Folia成片` / `/app/历史Folia成片` 共享挂载，不复制 MP4。`PUBLISH_ENABLED=1`、`AUTO_PUBLISH_ENABLED=0`，应用代码中没有 `/api/bili/upload` 调用。显式补建两个真实自动切片《日不落》、《三拜红尘凉》，均以 `identity_source=deepseek`、真实歌名进入 `ready`，BililiveTool 校验均返回 HTTP 200 `success`；其容器内已确认四个视频/封面路径全部可读。API 重启后任务仍为 2 个 `ready`、总尝试数仍为 2，BililiveTool `type=bili` 任务列表 SHA-256 前后同为 `a020b36146da3a7501d85fd8ce544b425d786ff2554481eca5e1edfdc5ef5eff`，确认未创建上传任务。新增投稿 16 项回归全部通过，Python 编译、Compose 配置、API 镜像构建和健康检查通过；全量 225 项中 224 通过，唯一 Tempera 预览测试失败已用上线前旧镜像复现，与本次无关。部署只重启 `studio-api`，当时进行中的整场 ASR 使用原 transcriber job ID 继续，转录/模型/渲染容器未重启。正式自动投稿前必须替换已明确标记的 Phase 1 占位封面。备份：`/vol1/1000/docker/folia-video-studio-backups/20260927-publish-phase1/`。

- 2026-09-26：仅将今后媒体写入切换到第二块硬盘：录播/下载/歌曲切片 `/vol2/1000/video/Folia录播`，成片/样片 `/vol2/1000/video/Folia成片`。应用、数据库、模型、字体、图片库和 ASR 工作数据仍在 `/vol1`；旧录播与旧成片未搬迁。系统服务 `folia-media-view.service` 在 Docker 启动前等待两盘挂载，使用官方 mergerfs v2.42.0 将新目录 RW、旧目录 RO 合并，保留原 source ID、录播机 `/app/video` 与房间身份历史。历史输出接口缺失新文件时回读 `/output-legacy`，旧切片下载兼容原路径，生成切片避开历史同名文件。录播工具保留原 Compose 项目名及 NAS 应用标签。切换前四个房间正常停止并完成 FLV→MP4 收尾，约 14:06–14:16 暂停；三间仍直播的房间已在新盘恢复，清歌喵当时已下播，监听规则保留。工坊原活动任务 `dd4b24513cc74b309f11ae3f0603f058` 在切换期间出现数据库锁，已保留八首歌及一首完成结果，通过重试接口重新排队，当前任务正常处理。Python 语法、Compose 配置、镜像构建、系统服务配置、Nginx、API/转录/渲染服务健康通过；旧项目视频与旧成片 HTTP Range 均为 206；新盘真实录播持续增长，API/渲染器成片写入标记均确认落在新盘并清除。未生成测试成片。备份：`/vol1/1000/docker/folia-video-studio-backups/20260926-vol2-video-paths/`。

- 2026-09-26：上线录播机身份联动，主 API 只读挂载 bililive-tools data，通过 streamer 与 record_history 的平台＋房间号绑定规则，持久化历史目录别名；改名后自动发现新目录，原监听开关、参数和历史任务保留。新旧目录统一用于自动扫描、历史选片与手动执行，主播名单按身份合并并显示房间号；新发现目录中早于规则启用时间的文件进入基线，避免重跑旧场次。四条既有规则均唯一绑定；清歌喵房间 1729694952 显示为清歌喵_清椰奶冠，API 历史列表包含新目录 30 个、旧目录 16 个原录播，名单仅一个入口。备份在 `/vol1/1000/docker/folia-video-studio-backups/20260926-recorder-identity/`。Python/JavaScript 语法、4 项身份回归测试、Compose 配置、API/Web 构建、Nginx 配置及服务健康通过，仅更新 API/Web；录播机与转录/模型服务未重启，未生成测试成片。

- 2026-09-26：自动流水线整场判歌改用 Faster-Whisper `large-v3-turbo` 逐句时间戳，180 秒分块、无 VAD、不生成整场逐字时间；DeepSeek 仍按真实句段 ID 定歌曲边界。歌曲切片导入项目后才运行 Qwen 逐字对齐及标准歌词匹配，手动转录的 Qwen 路径不变。断点按识别引擎和模型隔离，旧 Qwen 分块另行备份；API、转录器和本地 worker 镜像已更新，相关单测、Python 编译、Compose 配置和服务健康通过。正式重跑清歌喵 09:08 的 69 分钟录播：整场 ASR 完成 24/24 块、936 个逐句片段、0 秒整场逐字对齐，转录结果只发布逐句文件；DeepSeek 选出 1 首《普通Disco》，切片项目完成 Qwen 逐字及逐字版歌词匹配（20 个句锚点，32/32 句完成），生成高置信 H.264/AAC 成片 129.754 秒、120,369,201 字节。初次运行在 NAS 23:59 定时关机时中断，05:22 重启后续跑复用首块，未覆盖原录播或旧成片。上线前备份位于 `/vol1/1000/docker/folia-video-studio-backups/20260925-whisper-automation/`。本次只确认处理链路和文件元数据，实际画面仍由日常观看判断。

- 2026-09-25：自动流水线将规则性跳过与实际失败分开显示：仅有跳过的场次记为完成，页面标出跳过首数及逐首原因；确有失败歌曲时才显示部分失败。整场转录状态查询遇到短暂超时或断线会重试，使转录进程随后写出的 `SIGKILL` 原因进入任务记录；页面将此类失败标为“疑似内存不足”。历史上仅含跳过歌曲的场次及一条已有转录 `SIGKILL` 记录按现存证据回填。仅更新工坊 API 与网页，部署时使用 `--no-deps` 避免重建正在运行的转录服务；未重跑录播或生成视频。

- 2026-09-25：核查《金风玉蝶》逐字偏移发现分离后 ASR 的 359 个字中有 60 个零时长字，其中多个连续字被强制对齐器压到同一毫秒。过去这些零时长字仍被当作独立逐字锚点，制造虚假的约 -18 秒偏移组。现排除零时长 ASR 字参与逐字锚点评分，原 ASR 文本与时间记录保留供查看。隔离副本重算后有效逐字锚点从 58 降至 47，最大字锚点组从约 -18 秒改为约 -8.34 秒；但仍有不一致唱段，当前仍不自动应用单一全曲偏移。100 项时间轴单测通过，未生成成片。

- 2026-09-25：按用户要求把自动歌词匹配改为逐字优先：同歌名或合理短标题有可用逐字时间时，先限制到逐字候选，再用对齐证据分及最多 2 分的指纹歌手优势比较。逐字候选的偏移只允许由逐字锚点模型提供；锚点覆盖率低于 10% 或模型不稳定时尝试人声分离重识别，分离后仍无法形成可靠逐字偏移则保留原时间轴并明确报错，不再静默退回逐句偏移或报成高可信。修复再次匹配时丢失“已经分离过人声”记录而重复分离的问题。《金风玉蝶》复跑仍找到逐字歌词，但已分离的 ASR 字锚点未形成可靠对齐组，因此明确失败并保留原时间轴，不重复排队分离、不生成成片。已在 API 容器执行 99 项时间轴单测和 Python 编译，Compose 配置与 API 健康通过。上线前代码、文档及 SQLite 一致性备份位于 `/vol1/1000/docker/folia-video-studio-backups/20260925-word-first/`。

- 2026-09-25：修复《烟花易冷》暴露的翻唱标题误选歌词问题。音频指纹识别为白允y版本，但旧比较把 `(cover: 周杰伦)` 当作歌名的一部分，令网易云另一位歌手的逐句版标题相似度为 1.0、白允y逐字版仅 0.5，尽管后者有 30 个逐字锚点仍被淘汰。现仅在歌词候选比较时去除末尾翻唱/原唱说明；同标题、证据分接近时以指纹歌手打破平局，证据分相差较大时仍以对齐证据为先。真实旧候选摘要重新选择到 `qq:441280385`（白允y、逐字版）；新增针对该病例及错误歌手高分的回归测试，68 项时间轴单测通过。仅重建并重启 `studio-api`。芒芒项目自动匹配的初次逐字锚点覆盖率 6.9%，按 10% 阈值触发人声分离重识别。为让歌词任务先使用 AI 时段，按用户要求临时中止进度 3/31 块的整场转录；分离重识别完成后得到 64 个逐字锚点、14.75% 覆盖率、136 ms 逐字残差 P90，最终 `qq:401509123` 逐字候选、38 句时间轴、`alignment_review`。最终歌词候选标注歌手李苏航，与音频指纹白允y不同，需人工核对歌词版本。整场转录随后重试，复用已保存的音频与 ASR 分块，从对齐阶段继续，状态已回到 `running/transcribing`。未生成测试成片。修改前代码、文档及 SQLite 一致性备份在 `/vol1/1000/docker/folia-video-studio-backups/20260925-cover-title-alignment/`。Python 编译、Compose 配置、API 构建及服务健康通过。

- 2026-09-24：应用户要求追加七款古风与个性歌词字体：演示春风楷、演示佛系体、演示秋鸿楷、演示夏行楷、演示悠然小楷、香萃刻宋、香萃潮汐宋粗版。演示字体系列来自获得原作者转发及开源授权的 `maoken-fonts/slidefont`；香萃字体来自 `Miiiller/Xiangcui-Kesong` 与 `Miiiller/Xiangcui-Chaoxisong` 原作者仓库，均为 SIL OFL 1.1。原始 TTF 未修改，许可文本保存在 `data/fonts/OFL-*.txt`；字库文件均不超过上传接口 20 MiB 上限，常用歌词样例字均有字形。导入前备份字体和文档至 `/vol1/1000/docker/folia-video-studio-backups/20260924-lyric-fonts-ancient/`。上传 API 校验通过，七款字体的原生渲染器资源 URL 均返回 200，服务健康；无需重启，目前共 19 个可选字体（内置 3、额外 16）。未生成测试成片。

- 2026-09-24：为 Folia 原生歌词再导入六款中文字体：马善政毛笔体、龙藏体、站酷快乐体、站酷庆科黄油体、钟齐志莽行书、刘建毛草。原始 TTF 与 SIL OFL 1.1 许可均取自 Google Fonts 官方字库，文件未修改；抽查常用歌词汉字均有字形。导入前备份 `data/fonts` 和相关文档至 `/vol1/1000/docker/folia-video-studio-backups/20260924-lyric-fonts-more/`。通过现有上传 API 校验并按 SHA-256 去重，当前字体列表共 12 项（内置 3 项、额外 9 项）；六款新字体的 API 与原生渲染器资源 URL 均返回 200，两个服务健康。无需重建或重启容器，刷新工坊即可选择；按约定未生成测试成片。

- 2026-09-24：按用户截图收紧新版工作台。歌词制作的文件、预览、歌曲、时间轴、识别、效果、导出，以及切片/流水线各主要卡片现在可单独折叠；折叠状态在当前浏览器会话保留。文件列表、效果参数、歌词行及较长的任务/规则列表各自有高度上限和独立纵向滚动，操作按钮与卡片标题保持可见。修复文件列表仍沿用 22 px 网格列、却放入 40 px 图标造成文字压住图标的问题；时间轴列宽按主区收缩，效果网格限制子项最小宽度。备份在 `backups/collapsible-layout-20260924-213859/`，仅重建 `studio-web`。Node 语法、Web 构建、Nginx 与 API 健康通过；隔离浏览器接真实 API 在 360/390/768/1440/1611 宽度核对文件名无重叠、页面无横向溢出，现有 54 句时间轴的歌词列表及效果设置均出现独立滚动；卡片折叠/重新展开、两条滚动轴实际操作通过。未生成测试成片。

- 2026-09-24：按两张参考图重排歌词制作与自动流水线。桌面共用左侧工作区导航；歌词制作分文件、视频与歌词、识别/效果/导出三列，流水线显示真实统计、主播规则、队列与任务。手机继续使用底部三入口和四张步骤卡，效果预览移入效果卡内部，取消固定悬浮遮挡。新增 `/api/media/{id}/thumbnail`：验证媒体文件 ID 后在只读录播上串行抽取 240 px JPEG，缓存键包含相对路径、文件大小、修改时间和取帧时间；文件封面按需加载，每段视频时间条最多使用 12 个固定取帧点。时间条可点击定位，歌词区间来自已保存的逐句时间轴。新增 `/api/automation/summary`，按上海时区统计当前启用规则、当天任务、成功完成和当前排队。部署前备份在 `backups/ui-redesign-20260924-192323/`；仅重建 `studio-api`、`studio-web`。Node 语法、Python 编译、Compose 配置、镜像构建、Nginx 配置与 API/服务健康通过；真实项目缩略图从 202 生成中转为 200 JPEG，统计当前为 3/2/2/0。隔离浏览器核对 360/390/768/1440 两页无横向溢出；注入既有项目的 54 句保存时间轴，歌词前为空、提示下一句，进入区间显示对应歌词，时间条点击定位准确，手机效果卡内预览不悬浮。桌面浏览器操作服务连接失败，线上页面的实际选片和编辑保存交互未直接验收；按约定未生成测试成片。

- 2026-09-24：修复整站 UI 改版后预览被大字遮挡、歌词不显示及桌面预览覆盖后续内容。定位到此前歌词页改动遗漏了 `web/app.js` 的预览同步、样式、时钟和 Folia 原生会话函数；从改动前备份恢复，并让经典预览只读取已保存的对齐歌词。视频区域不再显示“选择视频后开始校对歌词”占位大字；标题旁明确提示已载入句数、下一句时间或尚未匹配。桌面预览与“歌曲与自动匹配”并排，时间轴在下方；预览取消吸顶，手机保留独立步骤。修改前备份至 `/vol1/1000/docker/folia-video-studio-backups/20260924-ui-fix/`，只重建 `studio-web`。Node 语法、Web 构建、Nginx 配置、API 健康及本地页面桌面/手机布局检查通过；未生成测试成片。NAS 页面需要刷新后加载新脚本。

- 2026-09-24：部署视频工坊整体 UI 与手机适配。新增 `web/ui-v2.css` 和 `web/ui-v2.js`，桌面将歌词预览/时间轴置于宽主区，文件、效果、导出置于侧栏；手机提供三个固定底部工作区入口、四个可独立展开的歌词制作步骤、紧凑效果预览、切片逐首卡片及单列流水线。转录工作台仍保留桌面入口和独立页面；工作区与步骤在当前浏览器会话中保留。仅重建 `studio-web`，保留 API、项目数据和导出链。前端 Node 语法、Compose 配置、Web 构建、容器健康及 360/390/768/1440 宽度页面布局检查通过；未生成测试成片。NAS 实际数据操作待日常使用观察。

- 2026-09-24：修复自动流水线页面每次切换进入都重新加载的问题。首次打开仍读取规则、任务、队列、主播目录和当前主播录播；再次返回直接保留页面内容，只在可见且距离上次更新超过 15 秒时后台刷新任务和队列。录播及主播目录不再因切换工作区重复扫描，仍可用页面刷新按钮主动更新。修改前备份页面与文档至 `/vol1/1000/docker/folia-video-studio-backups/20260924-automation-page-cache/`。`node --check`、Compose 配置、网页镜像构建、Nginx 配置及 API 健康通过；未运行测试成片。

- 2026-09-24：歌词制作页改为视频预览、歌曲与自动匹配、歌词时间轴三张独立卡片；时间轴取消框内滚动，窄屏预览取消吸顶。制作页移除候选手选、标准歌词大文本框、旧方式、ASR 精修和单独 Qwen 逐字入口，自动匹配内部能力和自动流水线仍保留。匹配前 ASR 草稿不作为最终歌词；匹配后逐句编辑正文、起止时间及启用状态，保存时校验时间，同步 `alignment.lines`、项目歌词正文和手动歌名歌手，预览与成片使用保存的数据。人工歌名歌手优先用于后续自动匹配，原识别记录保留，重新匹配已有时间轴前显示覆盖确认。修改前代码及 SQLite 数据库备份至 `/vol1/1000/docker/folia-video-studio-backups/20260924-lyric-ui/`。Python/Node 语法、Compose 配置、API 与网页镜像构建、Nginx 配置和 API 健康通过；未生成测试成片。Windows 浏览器操作工具无法确认当前 URL，按工具要求停止 UI 操作，因此页面实际交互与窄屏视觉尚未实测。

- 2026-09-24：修正 Tempera 预览字形发糊及图片库作用范围。此前工作台预览强制 0.5 倍 Pixi 纹理，现改为 1.0 并继续关闭全屏后处理；快速实时导出仍保留 0.5 性能档，流畅/透明逐帧导出不受此改动影响。图片库改为 `data/images/<项目 ID>/`，上传后自动加入当前项目，素材卡可永久删除且同步移除该项目保存的图片引用；「从本片移出」仅取消使用。原全局库里的一张用户图片按上传时 API 日志迁入《刚好遇见你》项目，原图和元数据均保留，其他项目不再显示。上线前备份代码、数据库和原图片目录至 `/vol1/1000/docker/folia-video-studio-backups/20260924-tempera-project-library/`。Python/Node 语法、Compose 配置、三镜像构建、Nginx 配置和容器健康通过；《刚好遇见你》图片库 1 张、《归期》0 张、渲染器项目图片 URL 可读取，预览配置报告 Tempera 纹理分辨率 1.0。按用户偏好未生成测试成片；实际视觉清晰度及快速模式画质待正常使用时观察。转录容器未重启。

- 2026-09-24：为 Folia 原生歌词效果导入三款中文字体：霞鹜文楷轻便版 Medium（抒情/手写感）、站酷小薇体 Regular（复古衬线）、得意黑 Oblique（活泼展示字）。字体分别来自原作者/Google Fonts 的官方仓库或正式发布包，按原始文件 SHA-256 去重，通过现有字体上传 API 存入 `data/fonts`；相应 SIL OFL 1.1 许可文本一并保存在同目录。导入前 `data/fonts` 备份在 `/vol1/1000/docker/folia-video-studio-backups/20260924-lyric-fonts/`。上传接口校验通过，`/api/fonts` 列出三款新字体，渲染器三个 `/fonts/<ID>` 路由均可读取，API 与渲染器健康；未重启容器或生成样片。刷新工坊页面即可在 Folia 原生「字体」下拉框选择。

- 2026-09-24：接入 Folia v0.7.8 官方 Tempera 图片池。工坊可上传 PNG/JPEG/WebP，解码校验、超 2048 边长缩放并按内容去重存入 `data/images`；每项目最多选择 16 张，可调水平/垂直倾向、大小、透明度、前后层级和镜头出现频率。项目样式只保存图片 ID 与官方 `layerImages` 参数，预览及快速/流畅/透明三种输出统一提供 `temperaLayerImageAssets` 和同源 `/images/<ID>`；缺图明确报错，背景保持透明、原录播画面保留。上线前备份到 `/vol1/1000/docker/folia-video-studio-backups/20260924-tempera-images/`。Python 与 Node 语法、Compose 配置、三镜像构建、Nginx 配置和服务健康均通过；临时图片上传、预览会话配置及渲染器图片 URL 读取通过，临时素材已删除并恢复原预览会话。独立无播放器的 Chromium 截图为空，未作为视觉验收；依用户偏好未生成测试成片，实际画面待首次使用自有图片时观察。转录容器未重启。

- 2026-09-24：新增 Folia「流畅 MP4（逐帧）」第三种导出方式。它复用透明路径的逐帧 Chromium 截图，但经 FFmpeg `image2pipe` 直接叠到原视频并编码 1080p30 H.264 MP4，保留原音频；逐帧等待浏览器动画绘制，避免实时 `x11grab` 因画布来不及刷新而按墙钟时间重复采样旧画面。输出使用 `_smooth.mp4` 与 `.smooth.render.json`，不覆盖快速或透明成片；原有快速 MP4 与透明 MOV + MP4 均保留。上线前备份代码与文档到 `/vol1/1000/docker/folia-video-studio-backups/20260924-smooth-export/`。Web、API、渲染器重建并健康，容器内 Python 编译、`node --check` 和 Compose 配置检查通过；正在运行的整场 ASR 在 API 重启后恢复跟踪，转录容器未重启。依用户偏好未运行新样片或完整测试流程，逐帧方式的实际速度与画面连续性需首个实际成片观察。

- 2026-09-24：针对实时预览切换和快速成片偶发卡帧做定向优化并上线。预览样式请求改为单请求在途、只追发最新配置，减少连续切换时的重复重建与旧请求覆盖；原生 SSE 会话快照不再每 10 ms 深度 JSON 序列化整首歌词，离线音频 256 频桶改为 NumPy 批量计算。快速 MP4 仍为 1920×1080、30 fps、x264 CRF 18，编码线程限为 4；CPU 争用时原生渲染器权重 2048、转录器 512，转录容器通过 `docker update` 原地调整，正在运行的转录任务未重启。同步修正网页中的 v0.7.8 revision 和文案。上线前备份到 `/vol1/1000/docker/folia-video-studio-backups/20260924-render-tuning/`。`node --check`、Python 编译和 Compose 配置检查通过；重建 Web 与渲染器后，渲染器及 API 健康接口正常。按用户偏好未运行新样片或完整测试流程；现有《阴天》Tilt 成片的 30、90、150 秒三个 5 秒片段各保留 149/150 个不同画面，源视频各为 150/150。重特效在实时画布上仍可能受机器负载限制，实际改善需下一次成片观察。

- 2026-09-24：Folia 原生渲染器从 v0.7.7 升到 v0.7.8（revision `9cf822015328e47ee5e22061213010a70b4ec5c9`，Docker Stack 1.0.27）。沿用 `studio-font-outline-v1` 描边与字体补丁，更新固定上游 revision、版本元数据及 Stack amd64 摘要。升级前备份配置和旧镜像 ID 至 `/vol1/1000/docker/folia-video-studio-backups/20260924-v078/`。按用户要求跳过测试流程与样片渲染；新镜像构建成功，渲染器与主 API 的健康接口正常，效果接口报告 v0.7.8。未修改原录播、切片或历史成片。

- 2026-09-21：完成 Folia `v0.7.7` / Docker Stack `1.0.26` 升级并正式上线。原生渲染器固定到提交 `80c073490482303d4283d1d5205be7707c96179d`，构建阶段从固定上游源码应用带版本校验的 `studio-font-outline-v1` 补丁，补丁不匹配即终止；效果页精简为“直播清晰 classic”和“Folia 原生”，原生区保留 v0.7.7 全部 13 个模式，历史 AMLL/Kinetic/旧 Folia 预设运行时回退 classic 而不改历史数据库。新增统一主歌词描边（默认开启、黑色、3 px、0–12 px、可选颜色）并覆盖 DOM/CSS、Canvas、Pixi 与 Three/Diorama 文字纹理；Tempera 原先的专用黑边并入统一开关，透明前景继续禁用会铺满画布的 paper transition。新增内置思源黑体/宋体/中文等宽字体、字重和 TTF/OTF/WOFF2 上传接口，字体按 SHA-256 去重保存在 `/data/fonts`，预览、快速 MP4 与透明 MOV 共用同一字体配置。新增每日稳定 Release + amd64 Stack 镜像检查、页面版本状态及同版本企业微信提醒去重，不自动升级。候选镜像验证 13 个模式会话均可创建，后端 188 项、转录服务 30 项测试和前端语法检查通过；正式容器健康检查确认 release、revision、Chromium、FFmpeg、字体和上游状态正常。上线前已备份 compose、数据库和字体目录到 `/vol1/1000/docker/folia-video-studio-backups/20260921-v077/`。切换期间先暂停调度；用户随后明确允许打断再续，转录服务已切换到新镜像，旧 job 的 `audio.wav`、`asr_chunks.json` 和已完成结果均被识别，原任务直接读取 826,596 字节现成 transcript 后完成，没有从零重跑，后续录播已继续执行。新版“Folia 稳定版可更新”企业微信事件已在正式转录容器中加载。正式镜像使用《离人赋》120–135 秒样片回归：快速 MP4 为 1920×1080、30 fps、H.264 + AAC，450 帧经 `mpdecimate` 保留 417 帧（折算 10 秒约 278/300）；2:04.5 画面保留原视频且统一 3 px 黑色主歌词描边可见，无全屏灰层；透明 MOV 为 ProRes 4444 `yuva444p12le`、30 fps、无音轨，对应帧 Alpha 均值约 0.8%（12 bit），确认不是实色画布。测试输出独立保存在 `/vol1/1000/video/Folia成片/芒芒_Mou/2026-09-21/高置信/离人赋_v077正式回归/`，没有覆盖历史成品、切片或录播。

- 2026-09-21：Tempera 透明前景字形新增黑色可读性边缘。固定 Fonia revision 的 Pixi 主字现在按字号使用 2–4 px 黑色圆角描边；原版已有的错版印刷式偏移副本由 `palette.ink` 改为固定黑色，透明度由 34% 提到 55%。改动只命中 Tempera 的主歌词字形，不处理背景、装饰字或其他 12 个 visualizer；构建脚本对三个固定压缩代码片段逐一校验，版本变化时直接失败。NAS 使用《离人赋》2:03–2:05 逐帧样片验证：浅色直播背景上的白字边界清晰，原动画正常，2:04 的不透明 paper transition 未恢复。渲染健康状态与新清单记录 `text_edge_profile=tempera-black-edge-v1`。

- 2026-09-20：修复 Tempera 快速成片严重卡顿及三处全屏灰层。《离人赋》快速版标称 30 fps，但 2:00–2:10 的 300 帧经 `mpdecimate` 只剩 54 个不同画面，根因是 NAS 的 Chromium 软件渲染无法以实时速度运行 Tempera 的 1.5 倍纹理与全屏后处理，X11 录屏只能重复旧帧；快速模式现在单独使用 0.5 纹理分辨率并关闭高成本后处理，10 秒实测提升到 271/300 个不同画面。透明 MOV 的 Alpha 检查同时定位到 28.600–29.267、112.067–112.367、124.500–124.800 三段整屏不透明，来自 Tempera 自带 paper transition 而非原视频或编码；透明前景配置现关闭该全屏转场，保留歌词、装饰、逐字、阴影与镜头运动。精确透明模式的其余质量参数不变。

- 2026-09-20：Folia 新生成的歌曲切片会同步生成同名 XML 元数据旁车文件，只保留原录播的 `<metadata>` 区块，不复制弹幕正文。bililive-tools 从“Folia切片”目录选择视频投稿时，可以继续解析主播、房间号和录制开始时间，因此简介中的 `{{now}}` 会按直播日期替换；固定投稿标题不受影响。原录播和原弹幕文件保持不变。

- 2026-09-20：修复低置信歌曲被错误指纹身份锁死。正常路径仍采用 ACRCloud 首个命中并立即比较歌词，高置信歌曲不增加任何指纹调用；只有初选低置信时才从下一个未检查窗口继续，两个独立窗口歌名一致即确认，并完整记录每个窗口的命中、无匹配或错误。复查同时把 12 个歌词候选名额均衡分给当前歌名和两个 ASR 歌词片段，避免错误歌名一次占满候选池。若异名候选为高置信、至少 5 个核心锚点、覆盖 10 秒且比分领先 40 以上，允许以 `evidence_consensus` 纠正歌曲身份和切片名；仍低置信才进入人声分离。

- 2026-09-20：修复自动任务“排队时取消”永久停在 `cancelling`。排队任务还没有转录 job，旧接口却和运行中任务一样只写 `cancelling`；工作线程只领取 `queued`，因此再也没有线程替它收尾，也会一直挡住空闲检测和部署。现在排队任务直接进入 `cancelled`，保留原运行记录，可通过重试重新排队；运行中的任务仍先请求中止底层转录，再由工作线程收尾。

- 2026-09-20：修复企业微信通知“系统内已发送、手机端却没有”的观测盲区。此前转录服务只要收到 HTTP 响应就当成功，完全不检查企业微信响应 JSON 里的 `errcode`；即使机器人拒收，自动流水线仍得到内部 HTTP 200，异常也被静默吞掉。现在投递必须以 `errcode == 0` 为成功，失败最多重试 3 次，最终失败由通知接口返回 502，并由自动流水线输出事件名、运行 ID 和完整异常。通知失败仍不改变 ASR、切片或渲染任务结果。

- 2026-09-20：补全“标准逐字歌词只做一次全曲平移”的实现。此前 09-19 的改动只阻止了后续 `force-align` 改写标准行，却遗漏了时间轴阶段的 `apply_hybrid_words`：它仍把 Qwen 现场字时间覆盖到平台逐字轴内部，《离人赋》因此记录为 `word_local_hybrid`。现在删除这条混合写回路径，改为 `apply_shifted_provider_words`；Qwen/人声分离证据只用于候选选择、唯一全局偏移和质量诊断，最终每个标准歌词字符严格使用平台原始时间加同一个 `shift_ms`。新增回归测试锁定 Qwen 字时间不得进入标准逐字成品轴。

- 2026-09-19（下午）：**整机死机一次并强制关机恢复**，根因是重任务互斥只堵了一半；连带修掉逐字对齐改写标准时间轴、人声分离从未真正执行、HF 离线、数据库连接泄漏。
  1. **事故**：15:00 前后整机失去响应，ping 不通、SSH 不通，只能强制断电重启。内核日志未持久化，`journalctl -b -1` 为空，OOM 记录无从取证，但现象（不是单进程被杀而是整机拖死）与 15 GiB 物理内存 + 3 GiB swap 下的换页死亡螺旋吻合。**根因是 `render_lock` 和 `ai_slot` 是两把互不知情的锁**：`ai_slot` 管整场 ASR / 逐字对齐 / 手动识别，渲染却走独立的 `render_lock`，于是渲染可以叠在 ASR 上跑。**修法**：`render_task` 拆成两层，外层取 `render_lock`（仍然保证"同时只有一个渲染"）后再进 `heavy_ai_slot`，渲染体 `render_task_locked` 不再自己碰锁。现在五类重活——整场 ASR、逐字对齐、手动识别、渲染、人声分离重识别——共用同一个槽位严格串行。新增测试锁定"渲染必须走 heavy_ai_slot""渲染体不得自己持锁""五类重活标签都在"。
  2. **逐字对齐不再改写标准歌词时间轴**（按用户明确要求："只要平移，不要再修改时间轴"）。`force_align_task_locked` 对 `has_standard_timeline(line)` 为真的行直接 `continue`，行框和行内字一律不动；只为标准行存在的 ±1200/±2500 ms 宽窗口、`standard_duration_ms` 校验一并删除。逐字对齐现在只服务 ASR 推导行和手工粘贴歌词。**证据**：《身骑白马》31 行里只有 2 行有 ASR 证据、316 字里只有 17 字有真实 Qwen 时间，对齐器却逐行改写行框——把标准歌词原本 6585 ms 的《放下西凉 没人管》压到 3520 ms（−47%），同时把 9152 ms 的《我一心只想 王宝钏》拉到 12160 ms（+33%）。逐行量起点差：−34515 出现 22 次、其余散落在 −31795~−34515，终点差极差 6178 ms——**起点和终点被独立挪动**，行时长因此被随机拉伸压缩，成品表现为"一句唱到一半字就扫完了、然后干等"。标准歌词自身行时长中位 6512 ms、行间空隙中位 696 ms，本来是整齐的。
  3. **人声分离从未真正执行过**。`transcriber/web.py` 放开了 `separate_vocals`，但 `build_command()` 只在需要跳过时 append `--skip-separation`，而 `main.py` 的默认值就是跳过——不加参数等于照样跳过。于是 09-19 那次"分离重识别"实际只是**拿同一份原始混音又跑了一遍 ASR**（`stats.json` 里 `separation_seconds: 0.0`、`separation_model: null`），锚点 27→17 的"倒退"其实是两次 ASR 的随机差异，此前"mdx_q 把歌仔戏唱腔剥坏了"的推断作废。补上 `--with-separation` 后手动实测《身骑白马》：**锚点 17 → 42，覆盖率 5.2% → 13.0%，两版平移量只差 174 ms**（互相印证）；耗时 462 秒（分离 218 + ASR 164 + 对齐 79），**峰值 6.8 GiB 且出现在 ASR 阶段而非分离阶段**——分离本身只占 4.6 GiB，进程退出后立即释放。此前按"分离峰值 9 GiB"估算风险是错的，那个数字是整个任务的峰值。触发阈值定为逐字覆盖率 < 10%（37 首 verbatim 项目的覆盖率中位 10.3%，饿着的那批远低于它），`SEPARATION_RETRY_COVERAGE` 可调，设 0 即关闭。
  4. **HF 离线**：transformers 每次加载模型都会试探一个上游本来就不存在的可选文件 `custom_generate/generate.py`，本地已有 `.no_exist` 负缓存但非离线模式下仍会去远端复核。网络好时一次 404 就过，网络卡时 10 秒超时反复重试（实测一次任务打了 10 条错误，两个模型各来一遍）。给 `local-worker` 和 `transcriber` 各加 `HF_HUB_OFFLINE: "1"`，实测超时归零、无 `LocalEntryNotFound`。代价是以后换模型或缓存被清会直接报错而非自动下载——对这台钉死版本的 CPU-only 机器，报错比静默卡住更容易发现。
  5. **`db()` 连接泄漏**：原本返回裸连接，`with db() as c` 只开事务、从不关闭，全靠垃圾回收。实测 studio-api 进程同时开着 **66 个** `studio.db` 描述符；未回收的连接若留着读到一半的游标会一直持有共享锁，这正是当天 `retry` 接口 500（`database is locked`）而所有读接口正常的原因。改成真正的上下文管理器（退出即 `commit`+`close`，异常 `rollback`），busy timeout 从默认 5 秒提到 30 秒，建表与迁移每进程只跑一次（原来 33 个调用点每次都跑 6 条 CREATE 和 2 次 PRAGMA 扫描，其中几处在循环里）。修复后描述符稳定为 0，隔离环境实测 50 次调用 fd 数不变、异常回滚、正常提交、退出后连接确实关闭。
  6. **零歌曲也发收尾通知**：`process_automation_run` 在没检出歌曲时提前 return，`outputs_completed` 永远不触发，读者只看到"开始转写、转写完成"就没有下文，和任务卡死无法区分。现在补发一条三项计数全 0 的汇总，正文出现 `🔇 本场未检出歌曲，没有需要查看的成片`。同时修正 `docs/modules/automation-pipeline.md` 里"只在全部成功时才发"的过时描述（09-17 通知改版后已改为无条件发送）。
  7. **试过但放弃**：用 DeepSeek 对照标准歌词纠正 ASR 听错的字（只返回 `{seg,pos,from,to}`、不给它看时间戳、逐条校验原字与替换字、改动超过 40% 整批作废）。实测《心之火》只提了 5 条同音字修改，锚点 7→7、残差与综合分一字不差——它的问题不是"听错几个字"而是"整句听岔"（ASR「谁让指尖停留为的想你沉默」对应原文「缠绕指尖停留 美得像一场梦」），单字替换救不了。代码和 13 项测试已删除，不保留。过程中还发现一个自造的坑：拿修正后的 words 重拼 `segment['text']` 会丢字，因为 Qwen 词单元并不完整覆盖句子文本，一次试跑 35 字掉成 26 字、锚点 7→3。
  事故教训另记：当天因为把"查队列"和"重启服务"写在同一条命令里，在看到结果之前就重启了转录服务，打断了一场已跑 10 分钟的整场 ASR（后经重试从分块断点恢复，未重复消耗算力）。**查与动必须分两步**。
  测试：完整后端套件 **148 项通过**，转录服务 19 项通过（含 `build_command` 的 4 项和零歌曲通知 2 项）。所有部署均在队列为空时进行。

- 2026-09-19：**歌曲身份不再允许被歌词候选反向覆盖**，并修掉行尾判据误砍慢句。起因是《读心术》查完对齐后顺藤摸到的一连串问题，最后落到一个自锁的反馈环上。
  1. **候选标题覆盖项目标题（根因）**：`auto_standard_timeline_task` 结尾用 `title=candidate.get('title')` 把选中歌词的标题写回 job。于是《夏天的风》被 lrclib 一条别名条目改名成《夏日の風》，**下一次重跑就拿这个错名去搜**，候选池退化成 `夏日の風/夏日晚风/夏日之风/夏日寒风/夏日の梦` 一堆近似词，真正的《夏天的风》逐字版（QQ/酷狗都有，46 行 verbatim）再也搜不到，只能退回行级歌词。越重跑越糟。只读审计 46 首有匹配结果的歌：**21 首标题与最初识别名不一致，且 100% 都等于选中候选的标题**——没有第二个机制改过标题。其中多首是改成了另一首歌（`西楼→孩子 (Live)`、`猫咪→他的猫`、`内线→犯贱`、`要抱抱→小野猫 (片段)(DJ默涵版)`），等于选错歌之后把犯罪现场也清理了。
  2. **改动**：新增 `backend/song_identity.py`。身份只由识别层写入——`create_imported_song_job`（DeepSeek，`identity_source=deepseek`）和 `adopt_identified_song`（指纹，`shazam`/`acrcloud`）；`jobs` 表迁移新增 `identified_title`/`identified_artist`/`identity_source`；歌词搜索改读 `resolve_search_identity(j)`，老项目回退显示标题并标记 `legacy_fallback`。候选信息只进报告的 `matched_title/matched_artist/matched_album/matched_source/matched_candidate_id`。`IDENTITY_SOURCES` 里**没有 `manual`**：人工在歌词页选哪份歌词，和候选自己声称叫什么，是同一种判断换个马甲，放进来等于把环从人工那头重新接上。`PUT /api/jobs/{id}/song` 因此不再写 title/artist。
  3. **历史回填默认关闭**（`IDENTITY_BACKFILL=1` 才执行）。只读预演 95 个项目：59 个"可回填"里，`很任性 (Live)` 会被退回成指纹已经纠正过的错猜 `人人心`，`归期` 会被指纹自带的装饰名 `归期(动画《凡人修仙传》插曲)` 覆盖，`向左转向右转` 会变成英文名 `Turn Left, Turn Right`（当搜索词更差）。**"能恢复"不等于"恢复的是对的"**，所以历史项目保持 `legacy_fallback` 原样不动，等专门的自动重新识别任务。后续实测又添一个反例：`要抱抱` 这首的 ASR 原文是"我是一只性感的小野猫喵"，DeepSeek 当初的原始名才是错的、被覆盖的名字反而对——历史身份恢复必须走重新识别拿证据，不能信任何单一来源。
  4. **顺带修掉两个同源问题**：`title_similarity` 之前用 `norm_text` 比较，不做繁简转换，于是 Shazam 给的繁体「讀心術」和平台简体「读心术」相似度只有 **0.333**，`choose_best_timeline_candidate` 的"逐字版优先"窗口（最高分 −0.05）直接把两个逐字版（综合分 251、78 个逐字锚点、p90 382ms）挡在外面，让一个行级版（224、9 个句段起点锚点、p90 1517ms）胜出，整首字幕偏早 2.7 秒还被判高置信。新增 `normalize_identity()`/`title_similarity()`（繁简+标点归一）置于 `standard_timeline.py`，刻意不动 `app.norm_text`——它同时兼着按字符过滤标点的活，有 11 处使用且部分要按下标映射回原文，在那里做繁简转换会让下标错位。同一套函数也用于指纹"是不是另一首歌"的判断，顺带消除了《读心术》切片被反复改名的折腾。
  5. **行尾判据改用末字时间**（`build_shifted_timeline`）。原来的保险是"行长超过全曲行间隔中位数的 1.5 倍就砍回中位数"，当初为《坏女孩》一行挂屏 32 秒而加。但中位数是一把全曲统一的尺子，对"开头慢、副歌快"的歌会砍掉真唱：《夏天的风》开头三句真实时长 7293/6832/7212 ms，中位数只有 4256 ms，于是被砍掉近 3 秒，`apply_hybrid_words` 还会把这行的字级时间压缩塞进砍短的框里——字幕唱到一半消失、跟唱整体偏快。改为：**带真实字级时间的行，行尾取末字唱完的时刻**（`min(原行尾, 末字 end)`）；没有字级时间的行保留原 `tail` 兜底。《坏女孩》那条照样被挡住——它的行虽然登记了"到下一句为止"，但歌声早停了。全量影子测量 37 首逐字项目：恢复 177 行、收紧 144 行（收紧的是"下一行起点比末字还晚"的，比原来更贴），没有任何行退回兜底路径。
  6. **另一处必须同时做的**：`INSERT INTO jobs` 原本是按位置的 13 列，加三列身份字段会重演 09-18 那次 `automation_runs` 的列数故障。已改为具名 `JOB_INSERT`，并补了"表上再多一个未来列也不影响插入"的回归测试。
  测试：新增 `backend/test_song_identity.py`（16 项：身份只能由识别层产生、`manual`/`candidate` 作为来源直接抛错、切换候选只改 `matched_*`、回填不得把可能被污染的当前标题写进身份、指纹优先于 DeepSeek 猜测、搜索必须从 `identified_title` 起）；`backend/test_standard_timeline.py` 新增繁简相似度 4 项和行尾 4 项（含《坏女孩》间奏防回归、《夏天的风》慢句保留）。容器内完整后端套件 **135 项通过**。
  部署：`backend/app.py`、`backend/standard_timeline.py`、`backend/song_identity.py` 及测试同步后 `docker compose build/up studio-api`。**踩坑记录**：`backend/Dockerfile` 是逐个文件名 COPY 的，新增模块没进清单，首次重建后容器 `ModuleNotFoundError: No module named 'song_identity'` 起不来约 2 分钟（当时队列为空，未影响任何任务）；已把 `song_identity.py` 加入 COPY 清单。以后新增后端模块必须同时改 Dockerfile。
  验证（只读模拟，未重跑任何历史歌曲）：9 首 `timing_type=line` 的歌分别用"被污染的当前标题"和"最初识别名"重跑候选选择——**前者 7/9 选中逐字版（繁简修复之功），后者 9/9**（身份修复补上《夏天的风》和《爱你》两首）。也就是说所谓的"没有逐字歌词只能走行级"的歌，一首都不是真的。另用 8 个独立测试项目把这批歌渲染到 `Folia成片/_新规则试渲染/逐字优先验证_20260919/` 供人工核对，未覆盖任何历史成片、未改历史项目的对齐记录、未重命名任何切片。
  仍然待解：(a) `choose_best_timeline_candidate` 的"逐字版优先"只看版本类型、不看这份逐字版是否真的匹配上，实测《爱你》选中一个 **0 个逐字锚点**的逐字版、平移直接跑到 −107 秒，需要给那一键加证据门槛；(b) 标题装饰（`(片段)`、`(DJ默涵版)`、`《X》插曲`）仍会压低正版逐字版的相似度，`归期`/`小野猫` 就栽在这里；(c) 21 首被污染身份的历史项目需要自动重新识别来恢复，连带它们按错名生成的成片目录；(d) `ROLE_LINE` 不认 `Written by：`，`Take My Love` 的制作名单混进了字幕。

- 2026-09-18：修复自动流水线自 09-17 19:05 起**完全停止接收新录播**。起因是用户反馈"自动流程没启动过"：三条规则都启用、容器全部健康、扫描线程也活着（`py-spy` 抓到 `automation-scan` 正停在 `app.py` 的 `automation_wakeup.wait(30)`），数据库没有被锁、`ffprobe` 秒回、按线上真实数据做的只读扫描模拟判定完全正确，但连续 8 小时零排队、零日志、零报错，`automation_seen` 里今早那条 1.93 GiB 的录播永远卡在 `observing / stable=1`。
  1. **根因**：`db()` 里那条 `ALTER TABLE automation_runs ADD COLUMN timings` 把表从 16 列变成 17 列，而 `scan_automation_profile`（自动排队）和 `run_existing_recording`（手动执行历史录播）两处仍是按位置写的 `INSERT INTO automation_runs VALUES(?×16)`，每次都抛 `OperationalError: table automation_runs has 17 columns but 16 values were supplied`；`automation_scan_loop` 外层的 `except Exception: pass` 把异常整个吞掉，于是故障一点痕迹都不留。已在事务里复现并回滚验证（未写入任何数据）。这也意味着**手动执行历史录播此前同样是坏的**。
  2. **插入改为具名且只写本次真正要设的列**：新增 `AUTOMATION_RUN_INSERT` 常量，列出 16 个业务列，`timings` 留给数据库，两处插入共用它。刻意不写成"跟表列数一致的 17 列"——那样下次再加列还得记得改；读取侧的 `automation_run_row` 和 `run_timings` 本就把空值当 `{}`。没有采用"给 `timings` 加 `NOT NULL DEFAULT '{}'`"的方案：线上既有行的该列已是 NULL，为此再补一次迁移是新风险。
  3. **两个后台循环不再静默**：新增 `automation_loop_error()`，`automation_scan_loop` 和 `automation_worker_loop` 的 `except` 改为输出完整 traceback 到 stderr；日志函数自身包了一层保护，不让"报告失败"把这两个必须长活的线程弄死。
  4. **仍然待办**：`db()` 里"检查列在不在然后 ALTER"的迁移方式散落各处，建议单独做成 `schema_version` + 有序迁移；后台线程还缺 `last_scan_at` / `last_success_at` / `last_error` 和每轮扫描/命中/入队计数——`py-spy` 只能证明线程活着，证明不了扫描成功，这次正是卡在这个盲区。
  测试：`backend/test_automation.py` 新增 3 项——禁止再出现按位置插入该表的语句（只做这一条源码文本断言，不解析 SQL 推导列集合）、用真实建表 DDL + 全部迁移列在内存库里把这条插入真跑一遍、**再额外加一个假想的未来迁移列后插入仍然成功**（后者正是当初 `timings` 干的事，是真正对症的回归）。隔离环境 12 项通过，容器内完整后端套件 111 项通过，新测试在修复前的代码上确实 3 项失败。
  部署：备份旧 `backend/app.py` 后同步 `backend/app.py`、`backend/test_automation.py`，`docker compose build/up studio-api`，健康检查 `ok=true`，启动日志无异常。重启后约 30 秒内自动排队今早两场录播——`小红泡-管珩心/2026-09-18/06-06-41`（1.93 GiB，已进入整场 ASR）和 `07-54-21`（1.07 GiB，排队中）。排查和验证全程未修改原录播、切片、成片和数据库数据。
  注意：`赛蒂娅Sentia` 规则是 09-17 21:40 才启用的，当天那两场（`18-40-31`、`17-10-14`）在启用时被记为基线，修复后也不会自动跑，需要在页面上用"手动执行以前的录播"触发（该入口此前同样受本 bug 影响，现已可用）。

- 2026-09-16：修掉两个把好结果误判成低置信的判定错误，并**整条关闭 DeepSeek 全曲重排**。起因是上一条改动部署后最近 13 首歌全部判低置信、全部走了 DeepSeek 全曲重排、零首高置信，而用户实测 DeepSeek 重排的字幕"整体偏移、对不上唱的位置"，质量还不如本地对齐——把一切推给 LLM 是错误方向。核对代码后确认低置信不是对齐能力的问题，是判定逻辑本身有两个错误：
  1. **`p90` 在锚点数 ≤9 时根本就是最大值**：`residuals[min(n-1, ceil(n*0.9)-1)]` 在 n=6 取 idx 5、n=9 取 idx 8，都落在最后一个元素上，要到 10 个锚点才真的是倒数第二。这批歌锚点数是 6/9/13/10/10/16/6，其中三首所谓的"九成锚点质量"其实是"最差的那一个锚点"。`p90 > 1500` 这条硬门槛因此被**删除**（不是调大数值）：现场翻唱与录音室母带天然有 1500~2700ms 的差异，拿它当硬失败判据本身就不成立。置信度现在只剩 `核心锚点数≥3 且 跨度≥10000ms`。
  2. **`max_anchor_drift_ms` 吃的不是核心锚点链**：`score_timeline` 返回的 `anchors` 是 `best_chain`，而 `best_chain` 在返回前被 `expanded_chain` 覆盖了——那是用 `max(8000, tolerance*4)` 的容忍窗把 `text_score>=0.8` 的额外候选重新收进来的链。于是 p90/置信度算的是 core_chain、`max_anchor_drift` 算的是 expanded_chain，**两个判据根本不是同一批锚点**，而且一条容忍窗 8 秒的链被拿去跟 2000ms 的漂移门槛比。上一条记录里"最大漂移 4300+"的那几首，数值差不多正好是这个窗口的一半。用最大值当判据的方向本身也是错的：最大值恰恰最容易被单个错配锚点污染，等于让中位数辛苦排除的离群点又从后门把好歌踢给 LLM。**第 6 条的漂移兜底机制就此作废**，`GLOBAL_SHIFT_DRIFT_LIMIT_MS` 删除，`max_anchor_drift_ms` 保留但降级为纯诊断日志，禁止任何分支读它。
  3. **返回值拆成 `core_anchors` / `evidence_anchors`**（`score_timeline`），不再有语义模糊的 `anchors` 键。core 是这首歌的时钟，所有置信度和漂移判定只准读它；evidence 是容忍窗数秒的证据链，只负责把 ASR 行挂到歌词行上（`build_shifted_timeline` 的 `anchors=` 参数收的就是它），一个时间都不移动。`word_timeline.score_provider_timeline` 里采集和筛选逐字锚点都走 evidence——那是证据工作不是置信度判定，而且局部漂移正需要更密的链，逐字锚点本身还有 ±1800ms 的硬约束兜底。
  4. **新增 `anchor_residual_stats()`**，给出 `median_abs_residual_ms` / `mad_ms` / `residual_p90_ms`。这批指标**当前只进日志、不参与任何判定**：锚点现在仍是 ASR 句段起点（句段起点常含语气词和呼吸，跟歌词首字差着一两秒），残差分布本身就不干净，阈值要等锚点改成逐字级之后再定。
  5. **DeepSeek 全曲重排整条关闭**：新增开关 `DEEPSEEK_FULL_REALIGN_ENABLED`（读环境变量 `DEEPSEEK_FULL_REALIGN`，默认 0，设 1 可临时打开做对照）。`confidence_tier` 相应改成三值——`high`（本地判定通过）/ `local`（判定不足但 AI 已关）/ `deepseek`（真的经过 AI），输出目录对应 `高置信` / `本地对齐版` / `DeepSeek版`。加 `local` 这一档是因为沿用二值的话，这些歌会被塞进"高置信"目录，回归时就分不清哪些是真高置信、哪些是本该送 AI 的。自动流水线汇总通知相应多一行"本地对齐版（N 首）"。
  测试：`backend/test_standard_timeline.py` 新增四组用例，其中两组是把坑本身写成回归测试——`residual_p90_ms` 在 n≤9 时确实等于最大值、单个 4300ms 离群锚点不影响 median_abs 和 MAD 但会让 max drift 爆掉；另两组覆盖"现场翻唱残差超过 1500ms 不再判低置信"和"core/evidence 分开返回"。隔离环境 63 项测试通过，`import app` 无误。
  真实回归（复用已有 ASR 和切片，未重新识别、未重新切片）：重跑 7 首，`median_abs_residual` 相对已知对得很好的《香水有毒》（200ms / MAD 297）作基准——《坏女孩》155ms、《夏日の風》180ms 比基准还好，而它们的 `p90` 精确等于 `max_drift`（2732 / 2409），证实那个"p90"就是单个离群锚点；《听到请回答》390ms、《很任性》408ms 接近基准；只有《完美比例》936ms 和《和你一样》1184ms 残差确实分散（MAD 1388 / 1755），是真正需要进一步处理的。也就是说被误送 LLM 的那批歌里，至少四首本地对齐质量本就足够。
  仍然待解：7 首重跑后 `tier` 全是 `local` 而非 `high`，说明 `find_suspect_anchor_regions` 是第二道闸，对锚点稀疏的歌几乎必然触发（连续≥4 行无锚点但中间有 ASR 句段这条规则，在一首 40+ 行、只有 6~16 个锚点的歌上很难不命中）。因为 AI 已关，这层目前只影响目录名不影响字幕质量，但下一阶段要一并处理。后续方向：锚点从 ASR 句段起点改为逐字时间（要定位的是歌词第 0 个字符在 ASR 逐字序列中的位置，ASR 漏首字时不能拿第二个字顶替，否则凭空推迟一个字），然后才用新的残差分布定 MAD / inlier_ratio 阈值，再考虑 Theil-Sen 平移+拉伸，LLM 最后回来只判结构（副歌唱了几遍、漏唱哪一行）而不再生成毫秒时间轴。

- 2026-09-16：歌名来源改为音频指纹，候选选择改为逐字版优先，时间轴对齐回退为整首平移 + DeepSeek 漂移兜底，并去掉了逐字级置信度判定。（其中第 6 条"漂移兜底"已被上一条推翻并删除。）起因是真实项目《很任性》（源切片 `赛蒂娅Sentia/2026-09-13/歌曲切片/人人心.mp4`，job `b738b70451df455487ccdc116ce212d9`）：自动流水线阶段 DeepSeek 按整场行级 ASR 把这首歌猜成了"人人心"（副歌"很任性的"被识别成"人人心的"，置信度 0.88），切片因此被命名为 `人人心.mp4`；后续按这个错名搜索标准歌词，匹配到了一首毫不相干的《心海寄托》（歌手名恰好叫"人人心"），整首歌词内容和演唱完全对不上。具体改动：
  1. **Shazam 音频指纹取代 AI 猜歌名**：新增 `identify_song_shazam`（`backend/app.py`），在补齐逐字 ASR 之后、搜索候选之前，用 30 秒窗口 / 25 秒步进**连续扫完整首**切片（最多 24 个窗口，首个命中即停，整体 240 秒硬超时），识别出歌名就直接采用。删除了 `verify_standard_lyric_match_deepseek`、`resolve_deepseek_match_verdict`、`_candidate_quality_key` 及其单测——让 DeepSeek 看 ASR 文本猜歌名实测完全不可靠：同一段文本，flash 模型先后给出"人间/王韵"和"人人心/魏佳艺"，pro 模型给出"拥抱你离去/张北北"，三个答案互相矛盾且逐一核对歌词后全部是错的；换成指纹后一次命中正确答案《很任性 (Live)》- 千百顺。指纹跑在**独立子进程**里（`SHAZAM_PROBE_SCRIPT`）：在进程内跑 shazamio 的 asyncio 会让后续 `asyncio.run` 无网络活动地永久挂起，实测复现过一次。`backend/requirements.txt` 新增 `shazamio`。
  2. **指纹认出不同歌名就改文件名**：新增 `adopt_identified_song`，重命名切片文件（目标名已存在则跳过不覆盖）、更新 job 的 `source`/`title`，并用 `sync_clip_rename_to_automation` 把新文件名同步回 `automation_runs.songs` 和 `clip_batches.items`——否则 `restore_completed_clip_paths` 按旧文件名找不到切片，重跑自动流水线会重新切一遍（本项目严禁重复切片）。改名后输出文件名（取自切片名）和输出文件夹（取自 job 标题）自动都正确。
  3. **同等标题匹配度下逐字版优先**（`choose_best_timeline_candidate`）：新增"逐字版且标题相似度在最高分 0.05 以内"作为最高优先级排序键。《很任性》的千百顺逐字版综合分 148.7、6 锚点，高于网易云 DJ 版的 147.2，但因为现场翻唱的行级残差不达标被判低置信，而排序第一优先级原本是"是否高置信"，于是 DJ 版（只有逐行时间、无逐字）赢了。标题相似度下限防止这个偏好跨到另一首歌的逐字版上。
  4. **去掉逐字级置信度判定**（`score_provider_timeline`）：`low_confidence` 现在只由行级证据决定。逐字锚点保留两个用途——喂 `apply_hybrid_words` 做逐字融合、给综合分加分（逐字优先排序仍在）——但不再参与置信度投票。原因：现场翻唱与录音室母带必然逐字漂移，这个判据实际衡量的是"这次演唱跟这个母带有多像"而不是"歌词选对没有"，两个方向都会误判。
  5. **时间轴对齐回退为整首平移**（`build_shifted_timeline`）：所有行统一加同一个 `shift_ms`（核心锚点链 delta 的中位数），不再在锚点之间做分段线性插值——单个错配锚点会把它周围的段落整体带偏，而每个锚点都带着一行 ASR 文字匹配的不确定性。锚点仍然用于给行挂 ASR 证据（`segment_ids`/`asr_start_ms`），逐字候选随后由 `apply_hybrid_words` 用真实 Qwen 字时间把每行拉到实际演唱位置，所以逐字版依然能跟住漂移的现场。
  6. **漂移兜底**：新增 `max_anchor_drift_ms` 和 `GLOBAL_SHIFT_DRIFT_LIMIT_MS=2000`（`backend/standard_timeline.py`）。任何锚点偏离整首 shift 超过 2 秒，就和"本地低置信"、"`find_suspect_anchor_regions` 探测到可疑区域"一样触发 DeepSeek 全曲重排——单一 shift 服务不了"越唱越拖"的现场，超过 2 秒字幕已经肉眼可见对不上。
  7. **卡死任务可恢复**：新增 per-job 线程注册表 `start_job_task`/`job_task_running`（recognize、force-align、standard-timeline 三个后台任务都已接入）。入口判据从"只看数据库状态"改成"状态忙 **且** 确实有活线程在写进度"；线程随容器重启消失、或活着但 30 分钟没写过任何进度，都判为卡死并放行重跑。此前任务一旦卡死，job 会永久停在 `timeline_matching`，接口一律返回 409，只能手改数据库才能重试——本次调试中就因此连续几轮在看同一份冻结快照。
  8. **署名过滤补漏**：`ROLE_LINE` 正则补上 `原唱`/`翻唱`/`主唱`，此前"原唱：千百顺"这类行会作为第一句歌词混进成品（《西楼》那个 job 也有同样的"原唱：西楼"残留）。
  测试：`backend/test_standard_timeline.py` 新增逐字版优先（含"不跨到另一首歌"的反向用例）、整首平移、漂移上报三组用例，删除分段插值相关断言；`backend/test_word_timeline.py` 把逐字置信度用例改成"逐字证据再强也不参与置信度判定"的回归用例，删除 900ms 阈值用例。隔离环境 59 项测试通过，`import app` 无误。
  真实回归（复用已有 ASR 和切片，未重新识别、未重新切片、未修改原录播）：《很任性》job 从错误歌名"人人心"开始全自动纠正——指纹在 75 秒处命中《很任性 (Live)》，切片被改名为 `很任性 (Live).mp4`，自动流水线记录同步更新，候选选中 `qq:201950985` 千百顺逐字版，歌词内容逐句核对正确（"一个人很寂寞 另一个很洒脱 / 谁先放开的手 当初却没有说"…），50 行 0 重叠。《世界上的另一个我》`a098c1c7c6aa496f8875702cc24c00fb` 用于验证漂移兜底：`shift_range_ms=2754` 超过 2000ms 阈值，正确触发全曲重排（`full_realign_used=True`）。卡死恢复双向验证：人为把 job 置于 `timeline_matching` 且无活线程时重跑返回 200，任务真正运行时重复请求仍返回 409。
  代码托管：项目首次纳入 git 并推送到私有仓库 `q1019161539/folia-`（88 个文件，`main` 分支）。NAS 上生成了专用 SSH 密钥（私钥留在 NAS，公钥以"folia NAS (feiniu)"加入 GitHub 账号）。提交前逐项核对过暂存内容，只有源码、文档和配置模板，`.env`、`data/`、`models/`、`work/`、备份和压缩包均已排除，无任何真实密钥入库。

- 2026-09-16：修复快速成片在 2% 阶段失败并只显示“Chromium DevTools 启动失败”。现场确认容器默认 Chromium profile 遗留 `SingletonLock`，且异常退出留下两个由 PID 1 持有的僵尸 Chromium 子进程；后续任务复用默认 profile 时被锁拒绝启动。现在每次浏览器渲染使用独立临时 `--user-data-dir` 和动态空闲 CDP 端口，结束时等待 `terminate/kill` 后的进程回收并删除临时 profile；容器以 `tini` 作为 init，负责回收 Chromium/Xvfb 的孤儿子进程。启动失败时会把 Chromium stderr 尾部写入任务错误，不再丢失直接原因。

- 2026-09-16：修复 Fonia 原生预览播放到结尾后再回拖出现黑屏。根因是 Chromium `captureStream()` 在媒体结束后可能不再向既有流推送新视频帧；主播放器虽然已经 seek 回去，iframe 内镜像仍停在结束流。桥接层现在记录结束状态，结束后发生 seek/重新播放时自动把 iframe 切换为同源静音视频镜像，并持续校准 `currentTime`、暂停和播放状态；正常首次播放仍优先使用开销较低的 capture stream。Fonia 原生高级设置新增“重置歌词位置到中心”按钮，一键恢复水平/垂直 `50% / 50%`，立即刷新预览，保存效果后进入成片配置。前端 build 更新为 `20260916-1`。

- 2026-09-15：修复“Fonia 原生预览歌词落后于时间轴、成品却正常”。离线导出逐帧设置绝对时间，不受影响；问题只在网页预览控制链。旧前端每 125 ms 无约束并发发送播放器时钟，预览或网络变慢时会累积旧请求；渲染服务收到后又把浏览器采样时间覆盖为 NAS 收包时间，使 Fonia 无法补偿 HTTP + SSE 延迟。现在前端最多保留一个在途请求，积压时丢弃旧样本、只发送最新时钟；时钟携带浏览器 `sentAtMs`，服务端原样传给同一浏览器中的 Fonia，由原版插值逻辑补偿传输时间。暂停、跳转和拖动仍强制发送最新状态。前端 build 更新为 `20260915-5` / `app.js?v=20260915-8`。

- 2026-09-15：Fonia 原生成片新增双输出方式，页面默认选择“快速成片 MP4（推荐）”。快速方式在独立 Xvfb 画布中让原视频与 Fonia 1.0.19 visualizer 同文档实时播放，再用 FFmpeg `x11grab` 直接录制 H.264/AAC MP4，不生成体积巨大的逐帧 ProRes Alpha 中间片；原“透明歌词 MOV + MP4”高质量链完整保留，可在输出方式下拉框手动选择。快速文件追加 `_fast.mp4`，不会覆盖同一效果的透明链成片。同步修复全局渲染锁误释放与重复点击竞态：未取得锁的线程不再释放别人的任务，接口在入队前原子占锁，繁忙时明确返回 409。已部署 `studio-web`、`studio-api`、`folia-renderer`，三个服务健康，Xvfb/x11grab 可用；Python 编译、前端语法和 6 项 Fonia 配置单测通过。使用现有《下一个天亮》项目做 15 秒真实快速烟测，约 31 秒（含 Chromium/Xvfb 冷启动）生成 1920×1080、30 fps、H.264 + AAC MP4，大小 5,180,921 字节；抽查 2 秒与 8 秒画面确认原视频正常、Fonia Partita 动态歌词已叠加。此前完整慢速任务也已安全完成，原 MP4 与 Alpha MOV 均未覆盖；未修改录播、切片、歌词或时间轴。

- 2026-09-15：修复 Fonia 原生 Tempera 在工坊中仍显示整屏灰白底、文字主色被强制成白/黑、无法调整位置及预览卡顿。根因是 Tempera 在透明 Shell 之内仍自行绘制全屏 paper wash/色块，并通过采样底图的 difference filter 决定文字颜色；此前传入的 `background.transparent` 只关闭公共背景，无法关闭这两层。现在工坊的 Tempera 固定使用前景配置：隐藏内部色块场景与不透明元数据片头卡、关闭依赖底图的动态反色，同时保留逐字入场、阴影、装饰、镜头运动和转场；根据用户主色选择虚拟对比底色，使最终 glyph 保留用户选择的准确颜色。新增原生水平/垂直位置滑块，参数同时应用于 iframe 预览和离线 Alpha MOV 渲染；Tempera 预览纹理分辨率降到 0.5 并关闭仅预览用的全屏后处理，导出质量设置不变。修复过程中补齐 Tempera 完整默认 tuning，避免只传局部参数时运行时读取 `layerImages.map` 导致空画面。已重建并启动 `studio-web`、`studio-api`、`folia-renderer`，全部健康；本地语法/编译与 6 项 Fonia 配置单测通过。NAS 使用真实项目 `b738b70451df455487ccdc116ce212d9` 做 1920×1080 单帧原生烟测：94.23% 像素全透明、119575 个像素可见，其中 118715 个符合指定粉红主色，Canvas 正常建立、无浏览器异常；位置变换实测为向下 15vh。未保存测试样式到项目，未生成或覆盖成片，未修改录播、切片和时间轴。

- 2026-09-15：修复 Fonia 原生特效在 Chromium 中通过透明 iframe 叠加时被浏览器合成为白底的问题。实测 Sonnet 顶层渲染截图的 94.4% 像素为全透明，但同一页面作为 iframe 时 Chromium 仍以白色补齐透明面。新增仅在 `studioPreview=1` 时启用的 `folia-studio-bridge.js`：在 Fonia iframe 内优先通过 `HTMLMediaElement.captureStream()` 显示主播放器的画面，再由原版 visualizer 在同一文档中叠加。不支持 `captureStream()` 时回退为静音同步视频。离线透明 MOV 渲染不带该参数，因此 alpha 通道、Fonia 原版特效及成片链未改。已重建并启动 `studio-web`，线上 HTML 已引用 `app.js?v=20260915-4`，Fonia OBS HTML 已确认注入桥接脚本。

- 2026-09-15：修复 Fonia 原生预览“容器已更新但浏览器仍显示旧降级字幕”。根因是早期 Fonia 页面在站点根作用域注册的 Service Worker 仍可接管工坊页面并返回旧缓存。现在 `/sw.js` 发布一次性退役脚本，自动删除旧 Cache Storage 并注销根 Service Worker；工坊 HTML 也在启动时做同样的自清理，根页和退役脚本均使用 `no-store`。Fonia iframe 增加 Canvas 就绪检测，加载期不再暴露原版 fallback 文字，45 秒未就绪时显示明确失败状态。已只重建 `studio-web`；线上 build `20260915-3`、`Cache-Control: no-store`、Service Worker 退役脚本和 Canvas 检测代码均已实请求确认。

- 2026-09-15：视频工坊新增与旧“Folia 原版”完全隔离的“Fonia 原生”引擎，固定复用 NAS 当前 Fonia 1.0.19 / revision `34e6d2258225610a178dde6ed1c406b699336c8a` 的 13 个 visualizer。预览通过同源 iframe 接收工坊歌词、播放器时钟和 WebAudio 频谱；导出服务按原版 44.1 kHz / FFT 2048 / smoothing 0.6 规则离线计算音乐响应，只设置 `background.transparent=true`，保留文字描边、阴影、发光、渐变、粒子、Canvas/Pixi/Three.js 和动画。输出固定为 1920×1080 30 fps：无声 ProRes 4444 Alpha MOV 永久保留，并生成叠回原视频、保留原音频的 H.264 MP4；支持 15 秒样片、完整成片、进度显示、中止、磁盘预检和 `.partial` 原子写入。新增 3 项配置转换单测；NAS 独立镜像健康检查通过，3 帧真实 Chromium 烟测生成 ProRes `yuva444p12le`（仅视频流、30 fps、1920×1080）及 H.264 MP4，Alpha 平面同时包含透明和非透明像素。旧 ASS/AMLL/Kinetic 路径未改视觉和输出协议。

- 2026-09-15（晚间，在当天早些时候的"逐字优先 + 三级置信度体系"重构之后）：修复 `confidence_tier` 误判高置信的 bug，收紧逐字置信度门槛，并删除"区域锚点合并"补救机制、统一改用全曲重排。三处改动均已部署并用真实项目回归验证，55 项后端单测通过：
  1. **`confidence_tier` bug 修复（本轮起因）**：真实项目《西楼》`f7d14fba309e4c5fbbf5ef6415a122ff` 本地打分低置信（候选选错成"孩子 (Live)"/华晨宇）、DeepSeek 选歌校验也正确判定 `is_match=False`，但按建议歌名重搜没能真正切换到正确候选（`switched=False`），此时旧公式 `confidence_tier='deepseek' if ai_helped else 'high'` 在"AI 没帮上忙"（`ai_helped=False`）时无条件判"高置信"，完全不看本地判断本身是否够格，导致选错歌、内容完全对不上的这首歌被当成高置信直接出片。修复为 `confidence_tier='high' if (is_high_confidence(result) and not ai_helped) else 'deepseek'`，之后进一步演进为下面第 3 点的 `need_ai_help` 判定。
  2. **逐字置信度门槛收紧**（`backend/word_timeline.py` 的 `score_provider_timeline`）：`word_high` 判据从 `exact>=15、覆盖行数>=3、跨度>=10000ms、残差<=900ms` 收紧到 `exact>=24、覆盖行数>=5、跨度>=15000ms、残差<=900ms`。原门槛偏松，翻唱/伴奏版可能靠几行巧合的高频词凑够门槛被误判高置信；真实验证案例《世界上的另一个我》（56 个逐字锚点、覆盖 11 行、跨度 200976ms）远超新门槛，未受影响。
  3. **删除"区域锚点合并"机制，统一改用全曲重排**：用户明确指出这个机制"没有存在的意义"——它只对本地初筛出的可疑片段打局部补丁、保留其余本地锚点不动，在补丁边界处容易和未改动的行产生时间重叠。真实回归对比：《世界上的另一个我》本地打分其实已经是高置信（逐字残差 807ms），但免费的 `find_suspect_anchor_regions` 探测发现了可疑区域，走区域打补丁路径时量出 30 处行重叠；改用全曲重排后降到 6 处（不是 0，DeepSeek 输出本身有随机性，且按用户此前明确要求，全曲重排是补救链最后一步、不再加本地二次校验/裁剪）。删除了 `align_lyrics_deepseek`（app.py）、`merge_local_and_deepseek_anchors`/`resolve_deepseek_lyric_matches`/`expand_deepseek_matches_to_anchors`（standard_timeline.py）及配套 9 项测试。新的判定逻辑：本地低置信 **或** `find_suspect_anchor_regions` 发现可疑区域，即 `need_ai_help=True`，统一触发 `full_song_deepseek_realign`；`confidence_tier` 唯一由 `need_ai_help` 决定，AI 没能给出可用结果时保留本地时间轴但 tier 仍是 `deepseek`，不会因为补救失败就回退成"高置信"。
  测试：`backend/test_word_timeline.py` 的两项核心回归测试改用 5 行/44 字符的合成数据以匹配新门槛（`LONG_LINE` 20 字符用于把逐字跨度撑到 15000ms 以上、同时保持行级跨度低于 10000ms），900/901ms 边界测试同步调整；`backend/test_standard_timeline.py` 删除 9 项区域锚点合并相关测试。隔离环境 55 项测试全部通过，`import app` 无误。
  部署：同步 `backend/app.py`、`backend/standard_timeline.py`、`backend/word_timeline.py`、`backend/test_standard_timeline.py`、`backend/test_word_timeline.py` 到生产，`docker compose build/up studio-api`，健康检查通过。
  真实回归（均复用已有 ASR 和切片，未重新识别、未重新切片、未修改原录播）：《西楼》`f7d14fba309e4c5fbbf5ef6415a122ff` 重跑后稳定输出 `confidence_tier='deepseek'`（不再是错误的 `high`），`ai_song_check.is_match=False`、`confidence=0.98`；候选仍未能自动切换到正确歌曲（LDDC 搜索"西楼"或 DeepSeek 建议的"西楼 等什么君"都没能命中真正对应的候选——"等什么君"其实是另一位歌手邓寓君的艺名，是 DeepSeek 猜词不准，不是重搜开关逻辑的 bug），仍属已知限制，见下。《世界上的另一个我》`a098c1c7c6aa496f8875702cc24c00fb` 重跑后 `full_realign_used=True`、`confidence_tier='deepseek'`，行重叠数从区域打补丁方案的 30 处降到全曲重排的 6 处。

- 2026-09-15（早间）：标准歌词对齐重构为"逐字优先 + 三级置信度体系"，修复了《世界上的另一个我》选错标准歌词候选（原唱阿肆/郭采洁逐字版被 DJ大大怪混音版压过）的根因，并顺带修复了成片输出日期文件夹时区错误。具体改动：
  1. **逐字ASR前置**：新增 `backend/app.py` 的 `ensure_word_level_asr`/`align_single_asr_segment`，在匹配标准歌词候选之前（`auto_standard_timeline_task` 最开始）先对整段 ASR 文本跑一次 Qwen ForcedAligner 整体对齐（复用 `global_force_align` 同款"整段拼接文本、一个大窗口"手法），把结果按字符数切回各 ASR 句段、打上 `timing_source='qwen-forced-aligner'` 标记；已有整场 Qwen 数据的自动流水线导入歌曲直接跳过、不重复花钱。个别没对齐上的句段单独用 `align_single_asr_segment` 局部补救，失败静默跳过不影响主流程。
  2. **置信度公式根因修复**：`backend/word_timeline.py` 的 `score_provider_timeline` 里，综合置信度判定从"行级 AND 逐字级都要达标"改成"行级 OR 逐字级任一达标即可"，逐字残差阈值从 800ms 放宽到 900ms（覆盖真实案例的 807ms）。根因是原来的与门会让"56个逐字锚点、逐字残差807ms、综合分275分（全场最高）"的原唱逐字版因为行级判据不达标被判"低置信"，被"0个逐字锚点、综合分只有200分"但行级判据凑巧达标的 DJ 版压过去。`choose_best_timeline_candidate` 排序逻辑本身不用改。
  3. **`force_align_task` 收紧快路径**：`preserved` 判定新增 `len(line.get('anchors') or [])>0`，避免纯插值（零真实 Qwen 命中）的行被误判为"已经对齐好，可以跳过"。
  4. **不再有"低置信版"，改为"DeepSeek版"**：`confidence_tier` 只有 `high`/`deepseek` 两档，唯一判定标准是"最终用于构建时间轴的锚点集合里，AI（`align_lyrics_deepseek`/`merge_local_and_deepseek_anchors`）是否真的贡献了内容"，跟本地判断高低置信、跟有没有问过 AI 选歌校验（`verify_standard_lyric_match_deepseek`）完全无关——选歌校验换到正确候选后如果本地已经高置信，就是"高置信"，不因为问过 AI 选歌而降级。渲染输出目录第二级从 `低置信` 改名为 `DeepSeek版`；旧的 `低置信` 目录和文件不删除、不搬动。
  5. **零锚点候选不再直接硬失败**：改为取综合分最高的候选（哪怕零锚点）送进补救链，先问一次 DeepSeek 是不是选错歌了；真正的硬失败只剩"连一个候选都搜不到"或者补救链跑完仍然建不出任何时间轴两种情况。
  6. **90 秒以下切片直接跳过**：`auto_standard_timeline_task` 最开始检查 `media_duration`，新增 `lyrics_skipped_short_clip` 状态。
  7. **自动流水线通知整合**：不新增独立 WeCom 事件，`outputs_completed`（整场结束统一发送的汇总通知）文案追加"DeepSeek 版（N首）"和"跳过（切片时长过短，N首）"两行，只在列表非空时输出；`transcriber/app/notify.py` 扩展文案，`AUTOMATION_NOTIFICATION_TITLES` 未新增事件名。手动单曲项目不涉及此通知。
  8. **时区 bug 顺带修复**：`render_task` 的 `day=datetime.now()` 直接取容器本地时间，而 `compose.yaml` 未给任何服务设置 `TZ`、`studio-api` 用的 `python:3.12-slim` 默认 UTC，导致北京时间凌晨 0:00~7:59 生成的成片被放进"昨天"的日期文件夹。改为 `datetime.now(ZoneInfo('Asia/Shanghai'))`，`backend/requirements.txt` 新增 `tzdata` 保证任意基础镜像都能正确解析时区。容器实测确认：裸 `datetime.now()` 是 UTC（当时北京时间 10:14，容器显示 02:14），修复后 `ZoneInfo('Asia/Shanghai')` 正确解析出 `+08:00`。
  新增测试：`backend/test_word_timeline.py` 新增 3 项（核心回归测试用真实数值特征复现原 bug、900ms 阈值边界测试、"仅行级证据"反向测试防止回归），`backend/test_standard_timeline.py` 新增 `is_high_confidence` 单测；隔离环境全部 59 项测试通过，`import app` 无误。
  部署：同步改动到 `backend/app.py`、`backend/standard_timeline.py`、`backend/word_timeline.py`、`backend/requirements.txt`、`backend/test_standard_timeline.py`、`backend/test_word_timeline.py`、`transcriber/app/notify.py`，重建 `studio-api` 和 `transcriber`，健康检查通过。
  真实回归：复用已有 ASR 和切片（未重新识别、未重新切片、未修改原录播）重跑《世界上的另一个我》`a098c1c7c6aa496f8875702cc24c00fb`：`ensure_word_level_asr` 补齐 376/376 个词的 `qwen-forced-aligner` 标记；候选正确切换到原唱对唱版 `qq:204851589`（阿肆/郭采洁，88行含"郭：""肆：""合："说话人标记，逐字锚点56个，逐字残差807ms）；`confidence_tier='deepseek'`（该候选本身行级 OR 逐字级已经够格高置信，但免费的 `find_suspect_anchor_regions` 探测仍发现并用 DeepSeek 修正了14个锚点，因此归入 DeepSeek 版而非高置信）；`force-align` 88行全部处理完，56成功、32行走粗时间轴兜底（其中18行是天然不可能有ASR证据的说话人标签，不算问题）；重叠数从候选阶段的42处降到最终17处（均为对唱快速接唱产生的轻微重叠，符合既有"允许现场接唱轻微重叠"设计）。成片 H.264 + AAC、`223.654 s`、`245538060` 字节，路径 `/vol1/1000/video/Folia成片/芒芒_Mou/2026-09-15/DeepSeek版/世界上的另一个我/`——日期文件夹和目录命名均已验证符合预期（此前测试当天已用 `datetime.now(BEIJING_TZ)` 生成正确的 `2026-09-15`）。验证过程中巧遇 `transcriber` 正在跑真实自动流水线整场识别任务（`芒芒_Mou` 当天新录播），`local-worker` 模型被暂时占用/卸载，`force-align` 排队等待约几分钟后自动完成，属于既有"重任务严格串行"设计的正常现象，不是本次改动引入的问题。

- 2026-09-14：标准歌词时间轴从“整首单一 `shift_ms` + 固定 LRC 行窗口”改为“全局偏移仅作 fallback + 多个可靠单调锚点分段插值”。Qwen ForcedAligner 的真实字时间不再被裁回标准 LRC 窗口，成功行会更新整行起止；顺序保护改为比较行起点，允许现场接唱和长音轻微重叠。候选置信度仍按紧密锚点簇判断，只有文字分数至少 `0.8` 的强匹配才可作为更宽漂移锚点，避免长 ASR 段开头制造假跳变。本地后端 37 项测试通过，API 已部署健康。复用既有切片和 ASR 重跑《世界上的另一个我》项目 `a098c1c7c6aa496f8875702cc24c00fb`：仍选中高置信 `netease:3383264482`，8 个锚点局部偏移 `+1650～+3956 ms`，Qwen `58/59`，唯一失败行“心有灵犀的”保留粗时间，最终行起点倒序 `0`。新成片为 H.264 + AAC、`158.254 s`、`172569753` 字节，位于 `/vol1/1000/video/Folia成片/芒芒_Mou/2026-09-14/高置信/世界上的另一个我/`；没有重新 ASR、重新切片或修改原录播。

- 2026-09-14：按交接文档要求，找一首仍停留在旧“整首单一 shift”模式且已知后半段偏移的现有项目做回归，验证分段插值修复的实际效果，未改动任何代码。候选来自 `studio.db` 中 60 个 `jobs`，筛选出唯一仍为 `standard-piecewise` 的项目（《世界上的另一个我》，已在上条验证）之外、`mode=standard-shifted` 且行级 `residual_p90_ms` 最大的《讲真的》项目 `45ca32cc9ec2460999949a0b22548617`（小红泡-管珩心，源切片 `小红泡-管珩心/2026-09-13/歌曲切片/讲真的.mp4`）：旧记录为 QQ 音乐 `qq:102197504`、12 锚点、跨度 `204560 ms`、行级 P90 残差 `2722 ms`、低置信。仅调用 `POST /api/jobs/{id}/standard-timeline/auto`（复用已有 `asr_segments`，未重新识别）→ `force-align`（复用整场 Qwen 逐字时间，65/65 成功、0 失败）→ `render` 三个接口做回归，未触碰 ASR 或切片流程。新结果改选 QQ 音乐 `qq:237535953`，12 锚点、跨度 `204560 ms`，行级 P90 残差降到 `473 ms`（逐字 P90 `440 ms`），置信度由低置信升级为高置信，`mode=standard-piecewise`。新成片 H.264 + AAC、`216.354 s`、`156019172` 字节，`trim_start_ms=0`、`trim_end_ms=216320`，位于 `/vol1/1000/video/Folia成片/小红泡-管珩心/2026-09-14/高置信/讲真的/`；2026-09-13 的旧低置信成片目录（MP4/LRC/对齐 JSON/渲染清单 4 个文件）原样保留未被覆盖或删除。原始切片 `讲真的.mp4` 校验：`171604844` 字节、mtime `Sep 13 21:07`、SHA-256 `afab567f4f0fec3704f49661613fa7ea00d742b53fb607af974c495efd5b7a68`，操作前后未变化，未重新 ASR、未重新切片。`/healthz` 确认 `ok=true`、`render_busy=false`，本次未重建任何容器。

- 2026-09-14：按用户要求，在部署「混音室：」署名过滤修复后再次重跑《世界上的另一个我》项目 `a098c1c7c6aa496f8875702cc24c00fb`（源切片未变，仍复用已有 `asr_segments`，未重新 ASR、未重新切片），确认该修复没有影响这首歌，且结果可复现。`standard-timeline/auto` 选中同一候选 `netease:3383264482`，8 个锚点、跨度 `145056 ms`、shift `+2596 ms`、P90 残差 `1360 ms`、高置信；`force-align` 仍为 `58/59`，唯一失败行仍是“心有灵犀的”（对齐器返回的逐字时间过度压缩）。渲染输出路径、大小（`172569753` 字节）、时长（`158.254 s`，H.264+AAC）与本次会话第一条记录完全一致，`trim_start_ms=0`、`trim_end_ms=158176`。

- 2026-09-14：上条回归验证的成片中发现标准歌词署名过滤漏掉「混音室：」简写。`backend/standard_timeline.py` 的 `ROLE_LINE` 正则中“混音”分支此前只匹配“混音工程师/混音工程室/混音工作室”，没有像“录音”分支那样兼容裸写的“室”，导致 QQ 音乐版《讲真的》里的“混音室：凃惠源音乐工作室”被当成第一句歌词，出现在回归渲染成片 `00:03.867–00:04.983` 处。修复为 `混音(?:工程师|工程室|工作室|室)?`，与“录音”分支写法一致；`backend/test_standard_timeline.py` 新增对应用例。先在 NAS 临时目录隔离跑 `standard_timeline` 模块 14 项单测通过，再同步到生产目录、`docker compose build/up studio-api`；容器健康后用 `docker compose run --rm -v backend:/app` 挂载完整 backend 目录跑全部单测，36/36 通过。`/healthz` 正常，其余容器未受影响。按用户要求本次未重新渲染《讲真的》，该项目当前线上成片仍是修复前生成的版本（含这行残留），下次涉及此项目时应先重新执行 standard-timeline/auto 消除这行残留。

- 2026-09-14：成品目录按置信度分层：`Folia成片/<主播>/<日期>/高置信/<歌名>/` 或 `低置信/<歌名>/`；MP4、LRC、对齐 JSON 和渲染清单文件名统一使用录播/歌曲名，不再在文件名追加 `_低置信`。重新渲染会写入对应置信度目录并覆盖同名输出；旧目录文件保留，不覆盖历史成片。

- 2026-09-14：修复多源标准歌词候选“只按总分取第一名”导致低置信 Live/改编版压过高置信原版、整份 LRC 整体平移后仍错位的问题。候选现在先比较是否高置信，再比较标题相似度、综合分和锚点数；以线上《下一个天亮》为例，旧逻辑误选逐字残差 P90 `1469 ms` 的低置信 Live 版，而同批存在 `500 ms` 的高置信原版。匹配前统一过滤制作名单、录音室、乐队/灯光统筹、和音、版权声明、平台广告及带已知歌名/歌手的标题横幅；渲染旧项目时也执行同一过滤，以上内容不再成为字幕或首尾裁切锚点。新增候选优先级和真实脏数据变体测试；既有错误成片不自动覆盖，需明确重新匹配并渲染才会改变。

- 2026-09-14：修复自动切片成功后调用 `publicclip()` 意外从原批次对象删除 `internal_path`，导致所有歌曲在创建歌词项目时收到空路径、只留下切片却没有成品的问题。公开 API 现在只清理切片数据副本；自动任务重试会从既有成功批次恢复切片路径，不重复切片。最终企业微信通知在流程结束时统一发送，正文分别统计成功、失败和跳过歌曲，并列出输出文件和目录；部分失败不再静默进入下一场 ASR。

- 2026-09-14：修复 `studio-api` 容器重启换 IP 后自动流水线页面的主播目录、监听规则和任务接口全部 502、页面看不到已锁定主播的问题。Nginx 现在通过 Docker DNS 动态解析 `studio-api` 与 `transcriber`，服务单独重启后无需再人工重启 Web；同时移除取消定时轮询后残留的 `automationTimer` 页面切换引用。线上持久化规则未丢失，当前 `芒芒_Mou` 与 `小红泡-管珩心` 均保持启用。

- 2026-09-14：自动录播流水线接入分阶段企业微信汇报，复用转录服务现有 `.env` Webhook，不新增或暴露凭据。自动任务开始整场 ASR、逐句 ASR 结果生成、歌曲切片批次结束时分别发送纯文字通知，正文包含主播目录名、录播文件名、逐句数量或切片成功/失败数量、成功文件名及输出目录。自动任务通过 `notification_mode=automation` 关闭原通用任务 ID 完成通知，避免 ASR 完成重复推送；普通转录任务的完成/失败通知保持不变，通知失败不影响主任务。飞牛端 Python 编译、31 项后端与 7 项转录测试、Compose 配置通过；`studio-api`、`transcriber` 重建后健康，其余服务未重启。确认 Webhook 已配置，并实发一条带“系统测试/【测试】”标记的 ASR 结果通知；未启动 ASR、切片或渲染。

- 2026-09-14：修复自动监控整场 ASR 因语音 VAD 跳过歌声而造成歌曲后半段缺失。自动任务的新建和 ASR 阶段续跑现在统一设置 `no_vad=true`，整场音频按连续 180 秒块串行送入本地 Qwen ASR；原始时间轴、CPU-only、逐块断点、人声分离关闭和 DeepSeek 分析逻辑均保持不变，转录工作台的手动任务仍可自行选择 VAD。新增自动 ASR 请求参数测试，飞牛端 Python 编译和 31 项后端单测、Compose 配置、线上请求参数实装检查、主 API 与转录服务健康检查通过；仅 `studio-api` 容器重建并重启，`transcriber`、`local-worker`、歌词服务均未重启。没有重新识别旧录播，也没有切片或渲染；此前由 VAD 生成的旧转录和两份不完整成片不会自动改变，需要明确重新执行录播后才会使用无 VAD 结果。

- 2026-09-13：自动流水线将 DeepSeek 歌曲分析结果在切片前同步发布到录播名目录。`<录播名>_歌曲分析.json` 保存模型名、ASR segment ID、本地换算的精确毫秒、置信度、判断依据、阈值、切片余量和未采用候选；`<录播名>_歌曲时间轴.txt` 提供可读歌单时间轴。文件是与数据库切片批次同源的人工审阅副本，切片仍直接使用本地校验后写入数据库的数据，不信任 AI 生成时间。Python 编译、本地 30 项后端与 6 项转录单测、线上容器健康和真实文件解析通过；仅重建 `studio-api`、`transcriber`。已为小红泡录播回填 4 首歌，JSON 共 4 条、0 条跳过，模型为 `deepseek-v4-flash`、时间来源为 `local-asr-segment-ids`；未重新分析、切片或渲染。

- 2026-09-13：整场 ASR 增加按原录播名称发布的用户目录，内部任务 ID 仅继续用于隔离 work、断点和重试。完成结果现在同步到 `folia-asr-mvp/output/recordings/<主播>/<日期>/<录播名>/`，文件名为 `<录播名>.txt`、`<录播名>.jsonl`、`<录播名>_逐字.jsonl`、统计 JSON 和日志；中途失败但已有逐块断点时发布 `<录播名>_未完成.txt` 与 `<录播名>_ASR断点.json`。启动时会回填已有任务，企业微信与 API 的 `output_path` 改为该可读目录，同时保留 `internal_output_path` 供维护。转录 5 项单测、Python 编译、Compose 和线上健康检查通过；仅重建 `transcriber`，回填得到 6 份 TXT。小红泡录播的后续重试已在 21:05 完成，完整 TXT/逐句/逐字文件均位于新的录播名目录，自动流水线最终完成并记录 4 首歌曲。

- 2026-09-13：修复自动录播整场 ASR 在 16 GB 主机被 OOM 杀死。任务 `c62c135d695347ffaa6ab84db489694f`（小红泡-管珩心）在 73/137 块时返回 `-9`；内核日志确认 19:28:49 触发全局 OOM，被杀 Python 匿名内存约 6.69 GiB，同时 `folia-video-ai` 仍常驻约 4.28 GiB 的 ForcedAligner，因此不是 137 块音频一起处理，而是两个容器各自一套 Qwen 模型叠加。转录服务现在每次本地 ASR 前调用 worker `/unload`，显式卸载 Whisper/ForcedAligner、回收对象并执行 `malloc_trim`；ASR 每完成一块即原子写入 `asr_chunks.json`，重试按路径、offset、时长复用已完成块，模型卸载后也执行内存 trim。Python 编译、本地 30 项后端与 3 项转录测试、Compose 配置、线上卸载接口和容器内断点复用检查通过；仅重建 `local-worker`、`transcriber`，重建后内存约 165 MiB/25 MiB、OOM 标记均为 false。旧失败发生在逐块落盘上线前，前 73 块无法恢复；任务保持失败状态，未自动重跑。

- 2026-09-13：取消自动流水线页面每 5 秒轮询；页面打开时读取一次，主播目录或任务状态变化后由用户点击“刷新名单 / 刷新录播 / 刷新”更新。新增“手动执行以前的录播”：从已锁定主播目录递归列出历史原录播 MP4，排除 `歌曲切片/`、partial 和无效文件，手动选择后绕过“只监听未来文件”的基线和自动监听 1 GiB 门槛，复用同一套串行 ASR、AI 歌曲分析、切片、标准歌词、逐字与成片流程；同一录播存在活动任务时拒绝重复排队，结束后允许明确再次执行。新增 `GET /api/automation/profiles/{id}/recordings` 与 `POST /api/automation/profiles/{id}/run`。本地 Python/Node 检查和 30 项后端单测通过；飞牛 `芒芒_Mou` 当前列出 129 场原录播且无歌曲切片混入，原监听规则保持启用。仅重建 `studio-api`、`studio-web`，健康与静态资源检查通过，本次验证未提交任何手动任务。

- 2026-09-13：自动流水线的主播锁定改为动态下拉选择。后端 `GET /api/automation/broadcasters` 实时枚举 biliLive-tools `video` 根目录的一级目录，直接以目录名作为主播名；页面每 5 秒随任务状态一起更新，也可手动刷新，新建主播目录无需改配置即可出现。既有规则可继续编辑；目录暂时不存在时保留原路径并明确标记。新增目录枚举测试，本地 Python 编译、Node 语法和 29 项后端单测通过；飞牛当前读到 18 个目录，原 `芒芒_Mou` 监听规则保持启用。仅重建 `studio-api`、`studio-web`，健康检查、线上接口及容器静态资源检查通过，未重建转录、歌词或 AI 服务，也未触发识别、切片或渲染。

- 2026-09-13：上线 LDDC 多源标准歌词与 Qwen/LDDC 混合逐字时间轴。新增内部 `folia-video-lyrics` 服务，固定 LDDC 提交 `84631e8`，统一搜索 QQ、酷狗、网易云和 LRCLIB；逐字候选会用 Qwen3-ForcedAligner-0.6B 的现场绝对字时间与平台标准字时间共同评分版本和全局平移，最终逐字优先级为“Qwen 原样字 → Qwen 受控纠错字 → LDDC 标准逐字 → 行内插值”，且所有字仍裁剪在固定标准行边界内。转录服务新增 `transcript_words.jsonl`，持久化 `segment_id`、`chunk_index`、绝对毫秒和 `qwen-forced-aligner` 来源；旧项目不自动切换、不重跑。飞牛端后端 28 项、转录 2 项单测、Python/Node 语法和 Compose 配置通过；《桃花旗袍》四源实调均成功，QQ/酷狗/网易云候选为逐字时间且覆盖率 100%，LRCLIB 为逐行时间，API 实际解析 QQ 版本得到 57 行、444 个逐字时间点。仅重建 `lyrics-service`、`studio-api`、`studio-web`、`transcriber`，所有容器健康；没有启动 ASR、切片或渲染，也未修改原录播和既有项目数据。

- 2026-09-13：上线“主播录播自动流水线”第四工作区。可保存并同时监听多个主播目录；启用时把现有合格 MP4 全部记为基线，此后只接收未来新增、至少 1 GiB、连续两次扫描大小不变且 `ffprobe` 成功的 MP4，并排除 `歌曲切片/`。整场录播只运行一次本地 Whisper/VAD/ForcedAligner，DeepSeek `deepseek-v4-flash` 只返回完整歌曲的首尾 ASR `segment_id` 和歌名，后端用本地句段换算时间；默认低于 0.80、短哼唱、背景音乐、严重打断、重叠或无效 ID 均跳过。歌曲以精确可见的 FFmpeg 流复制写入原视频同级 `歌曲切片/`，复用整场 ASR 后逐首执行网易云标准时间轴、Qwen 逐字和完整渲染；低置信照常标记出片，零锚点跳过。新增三张持久化表、断点重试与中止、逐首输出链接；所有重任务严格串行。DeepSeek Key 仅保存于飞牛 `.env`。后端共 25 项单测、Python/Node 语法、Compose 构建、DeepSeek 严格 JSON 实调、API/Web 健康及静态资源检查通过；仅重建 `studio-api`、`studio-web`，转录服务和本地 AI worker 未重建。上线后 `profiles=[]`、`runs=[]`，所有监听默认关闭，未识别、切片或渲染任何录播。

- Web 工作台、主 API、CPU 本地识别 worker 均由 `compose.yaml` 管理。
- 页面端口：`18081`；主 API 仅映射飞牛本机 `127.0.0.1:18082`。
- 支持 bililive-tools 目录浏览、恢复已有项目和原视频播放。
- 支持 Faster-Whisper `large-v3-turbo` CPU/int8 识别；可选 DashScope ASR，但不是必需依赖。
- 人声/伴奏分离当前不在 Folia 主流程中，避免 16 GB 内存机器因 Demucs 爆内存。
- 支持平台标准歌词、ASR 粗对齐、Qwen3-ForcedAligner-0.6B CPU 逐字对齐。
- Qwen 对齐已改成逐句处理，页面显示百分比、当前歌词、成功/失败数；每完成一句立即保存状态。
- 支持透明歌词覆盖预览、AMLL/Kinetic/Folia 效果和 FFmpeg 成片渲染。
- 支持导入歌单时间轴，批量流复制切歌到原视频同级 `歌曲切片/`，不会覆盖同名文件，并可中止。

## 最近实测

- 2026-09-13：使用此前未出片的《大圈圈》项目 `de6fd7c425704dac8990387145fc8b1a` 完整验证现有链路。ASR 得到 16 个片段；标准时间轴选择网易云 72 行版本，5 个锚点、跨度 73.72 秒、P90 残差 1546 ms、整体偏移 `-13465 ms`，按阈值标记低置信；Qwen 成功 71/72，1 行使用固定标准行边界回退，字幕重叠和逐字越界均为 0。成片 `/vol1/1000/video/Folia成片/芒芒_Mou/2026-09-13/大圈圈/大圈圈_低置信_folia_overlay.mp4` 为 H.264 + AAC、188.188 秒、180,048,506 字节，配套 LRC、对齐 JSON、渲染清单均已生成；最终成片只做流复制首尾裁切。原录播未修改。

- 2026-09-13：新增高置信成片《越来越不懂》。从《我的悲伤是水做的》《越来越不懂》《带我走》《不灵不灵》的临时副本中筛选，前两首高置信，选择锚点更多且残差更低的《越来越不懂》；所有筛选副本已删除。原项目 `43189823d7294edc9a1ca874fefccee1` 复用已有 ASR，标准时间轴 58 行、13 个锚点、跨度 136.01 秒、P90 残差 1300 ms、整体偏移 `+17310 ms`；Qwen 成功 46/58，12 行固定边界回退，重叠和逐字越界均为 0。首次真实验证成品 `-c copy` 裁切时发现 `-avoid_negative_ts make_zero` 会把关键帧预卷变成可见画面；移除该参数后，MP4 用隐藏预卷满足解码且可见时间从 0 开始。另补充“出品人”署名过滤，防止署名成为裁切锚点。现有成品仅通过流复制继续裁切，没有重新烧录或编码；最终范围 `31.900–247.480 秒`，文件 `/vol1/1000/video/Folia成片/芒芒_Mou/2026-09-12/越来越不懂/越来越不懂_folia_overlay.mp4` 为 H.264 + AAC、215.813 秒、228,548,488 字节，首条 LRC 为 `[00:05.000]在我二十二岁时`，57 行无署名。项目输出记录 `post_render_stream_copy_trim=true`。20 项测试通过，仅重建 `studio-api`，原录播未修改。

- 2026-09-13：提供高/低置信成片对照。高置信沿用《桃花旗袍》项目 `3d3a168bb1fb4c25a38bf2ace90d9e0a`；低置信选择《忽然之间》项目 `abfdd53c558d49bf8d347e3222943384`，复用已有 ASR 得到 31 行标准时间轴、8 个锚点、整体偏移 `-13855 ms`，因 P90 残差 `1915 ms` 标为低置信。Qwen 成功 28/31，3 行固定边界回退，61–68 秒活动字幕为 0，重叠和逐字越界均为 0。完整输出 `/vol1/1000/video/Folia成片/芒芒_Mou/2026-09-12/忽然之间/忽然之间_低置信_folia_overlay.mp4` 为 H.264 + AAC、172.053 秒、155,018,962 字节；因首尾空白均不足 5 秒，`trim_start_ms=0`、`trim_end_ms=172049`、`post_render_stream_copy_trim=false`，按规则两侧均未裁切。未重新 ASR、未切原录播。

- 2026-09-13：按用户澄清将自动首尾裁切从“改变原视频烧录窗口”修正为“完整成片生成后直接裁切”。渲染仍按原流程一次完成，随后以第一条/最后一条有效歌词为依据，对成品 MP4 使用 FFmpeg `-c copy` 裁切并原子替换；某侧空白不超过 5 秒时该侧不切，不重新计算字幕效果、不二次编码。配套 LRC 使用裁切后的相对时间，渲染清单和项目输出保存 `trim_start_ms`、`trim_end_ms`、`post_render_stream_copy_trim`。Python 编译、20 项后端测试和飞牛端测试通过，仅重建 `studio-api`；依用户要求未再次烧录《桃花旗袍》，当前已生成成片保持不动。

- 2026-09-13：完整成片新增统一自动裁切规则：第一条有效歌词前保留最多 5 秒，最后一条有效歌词后保留最多 5 秒，源视频边缘不足时不补内容；ASS 与 LRC 随裁切起点归零，样片逻辑不变。补齐古筝、录音师等平台署名过滤，署名不再作为歌词或裁切锚点。新增首尾正常留白和源边缘不足两项测试，后端共 20 项测试通过，仅重建 `studio-api`。用《桃花旗袍》从只读原视频重新渲染验证：有效歌词范围 `32.340–202.570 秒`，实际读取窗口 `27.340–207.570 秒`；新成片 `/vol1/1000/video/Folia成片/芒芒_Mou/2026-09-12/桃花旗袍/桃花旗袍_folia_overlay.mp4` 为 H.264 + AAC、180.254 秒、186,878,814 字节，首条 LRC 为 `[00:05.000]桃花坞里桃花屋旁`，56 行中无署名，渲染清单记录 `trim_start_ms=27340`、`trim_end_ms=207570`。原录播未修改。

- 2026-09-12：从尚未使用新标准时间轴、且未生成过成片的项目中，以临时副本比较《红昭愿》《爱你》《桃花旗袍》，筛选副本随后全部删除。《桃花旗袍》以 9 个锚点、115.35 秒锚点跨度、P90 残差 1470 ms 达到高置信，优于另外两个低置信候选；在原项目 `3d3a168bb1fb4c25a38bf2ace90d9e0a` 复用已有 ASR，选中 58 行标准 LRC 并整体移动 `+3000 ms`。Qwen 逐字成功 55/58，3 行保留固定标准边界并均匀分配字时间；固定边界变化 0、逐字越界 0、字幕重叠 0。完整成片 `/vol1/1000/video/Folia成片/芒芒_Mou/2026-09-12/桃花旗袍/桃花旗袍_folia_overlay.mp4` 为 H.264 + AAC、227.051 秒、226,659,932 字节，配套 LRC、对齐 JSON 和渲染清单同步生成。按用户要求以真正首句 `32.340 秒`为基准，仅保留前 5 秒，从成片开头精确裁去 27.340 秒，另存 `/vol1/1000/video/Folia成片/芒芒_Mou/2026-09-12/桃花旗袍/桃花旗袍_保留5秒前奏_folia_overlay.mp4`；裁切版为 H.264 + AAC、199.710 秒、191,350,052 字节，项目查看链接已指向裁切版，旧成片保留。同时补充古筝、录音师等 LRC 署名过滤并通过 18 项单测，仅重建 `studio-api`。未重新 ASR、未切原始录播，原录播未修改。

- 2026-09-12：上线“ASR 定位 + 标准 LRC 整体平移”模式。新增 `backend/standard_timeline.py` 和 `POST /api/jobs/{id}/standard-timeline/auto`，支持 LRC 多时间标签、`[offset]`、网易云多候选搜索去重、重复副歌顺序消歧、全局稳健偏移、置信度持久化、无时间歌词低置信插值，以及标准行固定边界内的 Qwen 单字裁剪；旧项目只有主动执行新入口后才切换模式。渲染允许新模式中无 ASR `segment_ids` 的标准行进入输出，低置信 MP4/LRC/对齐 JSON/渲染清单统一增加 `_低置信`。长间奏不再把上一行机械延长到下一行，而按该 LRC 的典型行距收尾。18 项后端单测、Python 编译、前端语法和 effects 构建通过；仅重建 `studio-api`、`studio-web`，转录服务和 AI worker 未重建。使用现有数据的临时任务副本验证且已清理：《请和这样的我恋爱吧》选中 49 行、36 锚点、整体偏移 `-8995 ms`、高置信，13 条无 ASR 行仍保留；《忽然之间》选中 31 行、8 锚点、整体偏移 `-13855 ms`，因 P90 残差 `1915 ms` 标为低置信，61–68 秒活动字幕为 0。随后经用户明确指定，在原《请和这样的我恋爱吧》项目复用现有 ASR 执行新模式：Qwen 逐字成功 43/49，6 行保留固定标准边界并均匀分配字时间；固定边界变化 0、逐字越界 0、字幕重叠 0。完整成片 `/vol1/1000/video/Folia成片/芒芒_Mou/2026-09-12/请和这样的我恋爱吧 (加速版)/请和这样的我恋爱吧_folia_overlay.mp4` 为 H.264 + AAC、107.051 秒、43,785,784 字节，LRC、对齐 JSON 和渲染清单同步生成。未重新 ASR、未切片，原录播未修改。

- 2026-09-12：重构标准歌词纠错为“ASR 片段主导”，并修复初版过严导致的漏词。新增 `backend/asr_matching.py`：片段开头匹配失败时不再丢弃整个 ASR 段；普通片段保持 60% 原样字门槛，同音错字较多的长句仅在“4 秒内已有前句锚点、只匹配下一条歌词、最多两个 ASR 段、长度相近”全部成立时使用顺序弱匹配；一个 ASR 段跨两行时可保留前一行短前缀再匹配后一行。无 ASR 的空白仍不会补词，Qwen 仍固定在 ASR 边界前后约 300 ms。单元测试扩充到 10 项并全部通过。《请和这样的我恋爱吧》项目 `b4f50c726d6b4c7b8129b79552dba2e9` 从 36 个片段恢复到 45 个、覆盖 42 条标准歌词；剩余未覆盖歌词无 ASR 证据。Qwen `44/45`，唯一未逐字的 0.36 秒“我要”保留 ASR 字时间；最终重叠 0。新成片 `/vol1/1000/video/Folia成片/芒芒_Mou/2026-09-12/请和这样的我恋爱吧/请和这样的我恋爱吧_folia_overlay.mp4` 为 H.264 + AAC、107.051 秒。回归《忽然之间》得到 12 个有证据片段，61–68 秒字幕事件仍为 0。原录播 SHA-256 保持 `1aad321fb4675033173037019637671807f5b2c0297305697ebdfa04d4597577`。

- 2026-09-11：修复 Qwen 逐字结果把字幕跨间奏拉到下一句的问题：检测单个开头字符异常占用数秒以及短句整体均匀过度拉长，只收缩已有逐字区间，不删行、不新增未唱歌词。现有《爱啦啦》项目 `46c58715119d4d509837d6845bd78b3f` 保持 42 行；`Come on` 由 `28.460–36.460` 收回到 `33.760–36.460`，`难道其实是我 我在发神经` 由 `61.020–68.460` 收回到 `63.510–68.460`，原先从 `2:04.700` 跨间奏显示的长句收回到 `2:21.660–2:27.500`。重新生成 `/vol1/1000/video/Folia成片/芒芒_Mou/2026-09-11/爱啦啦/爱啦啦_folia_overlay.mp4`，ASS 为 42 行且关键行均含 `\\kf`，成片 H.264 + AAC、190.059 秒；原录播 SHA-256 仍为 `1aad321fb4675033173037019637671807f5b2c0297305697ebdfa04d4597577`。

- 2026-09-10：基于长录播 `芒芒_Mou/2026-09-08/08-21-03_【歌杂杂】这回忆的漩涡.mp4` 的 691 行逐句转录，人工与独立复核共同筛出 13 段清晰、相对完整的现场演唱；时间轴保存为 `docs/artifacts/08-21-03-song-timeline.txt`，并同步到对应 ASR 任务输出目录。视频工坊成功解析 13 首正式歌曲、0 个疑似片段，批次 `c162a79b7660429e8232d0682e4ba178` 以流复制完成 13/13 个切片，前后各保留 2 秒，输出到原录播同级 `歌曲切片/`。逐个 `ffprobe` 验证均含 H.264 视频和 AAC 音频；原录播切片前后 SHA-256 均为 `1aad321fb4675033173037019637671807f5b2c0297305697ebdfa04d4597577`，未被修改。短哼唱、背景歌词及被聊天严重打断的片段未纳入正式切片；本次无代码改动、未重建服务。

- 2026-09-08：将独立 `folia-asr-mvp` 的核心流程“选择录播 → ASR → ForcedAligner → 逐句时间戳文件”并入歌词视频工坊：主页面增加“录播转逐句文字”入口，Nginx 通过 `/transcriber/` 代理独立转录服务，录播仍为只读挂载；原 ASR 的模型、过程任务、输出和企业微信配置继续使用原目录，不迁移数据。转录页面已适配子路径，历史任务继续按 `job_id` 隔离。线上验证主 API、转录 API、页面、静态资源和反向代理均正常；9 个历史任务可见，`pear-long-retry-20260906` 的 `transcript.jsonl` 仍为 637 行，迁移前后模型/过程/输出文件数保持 `55/1797/60`。旧 ASR 容器已移除但 Compose 与数据保留，能够回滚。视频服务统一为 `folia-video-*`，音乐服务统一为 `folia-music-*`，全部健康；未修改任何原录播。

- 2026-09-05：修复成片输出目录混放：完整成片与样片现在按 `Folia成片/<主播>/<日期>/<歌名>/` 分目录保存，歌名经过安全化处理；仅修改 `backend/app.py`，已在飞牛只重建 `studio-api`；重建后 `/healthz` 返回 `ok=true`、`render_busy=false`。

- 2026-09-05：按维护验证要求使用另一首《快乐女孩》完整跑通本地识别 → 网易云标准歌词 → Qwen 整首顺序逐字对齐 → Folia 覆盖成片。测试项目 `66e0a8d8efe341fbb3578ba7a9f6b7e6`，来源仅为 `bililive-tool/video/芒芒_Mou/2026-09-01/歌曲切片/快乐女孩.mp4`；ASR 完成，标准歌词 42 行，Qwen `42/42` 成功、`0` 失败、`order_repairs=7`。完整输出 `/vol1/1000/video/Folia成片/芒芒_Mou/2026-09-05/快乐女孩_folia_overlay.mp4`，时长 `195.051` 秒，H.264 + AAC，ASS 42/42 行包含 `\\kf`。首次提交渲染时出现一次 SQLite `database is locked`，未产生破坏性写入；确认渲染锁释放后重试成功。原录播只读，当前 SHA-256 为 `f2ed140b7c4c2768deb17779f6b1791e04d7a146844e67d8c7a14904b3898b82`。

- 2026-09-05：修复标准歌词“输入歌名也搜不到”：新建任务和标题为空的旧任务会用切片文件名预填歌名；网易云搜索与歌词读取改为可用的直连接口优先、旧网关回退，页面明确显示当前查询词。飞牛现有 `歌曲切片/快乐女孩.mp4` 恢复后标题自动补为“快乐女孩”；按歌名搜索第一候选为刘惜君《快乐女孩》（ID 255184），并成功加载以“我要甜甜的味道”开头的完整时间歌词；按该句歌词片段搜索也能返回正确歌曲候选。前端语法、后端编译、API/Web 镜像构建、容器健康和线上接口检查通过；未重新识别、未改动原视频。
- 2026-09-05：将 Qwen 从“每句独立搜索”升级为“整首标准歌词有序对齐优先、逐句回退”。《遇见》实测一次返回 237 个标准歌词字符，38/38 行获得 `forced-character` 时间，仅修复 1 个句界且最终重叠为 0；worker 同时修复末字零时长被拉到搜索窗口末端的问题，结尾歌词由错误的 205 秒收回到约 183 秒。重新生成整首成片，ASS 38/38 行均含 `\\kf`；抽查 45、140、180 秒画面均有对应单行逐字染色。成片 H.264 + AAC、212.053 秒、约 91 MB，原录播 SHA-256 未变化。
- 2026-09-05：针对整首成片“大段无字幕”继续修复：渲染端会保留可信逐字行，并为无时间的歌词在相邻锚点间生成整句近似时间；共用同一 ASR 区间的相邻行会重新分配区间，超长尾行也会与后续歌词共享尾段。重新生成《遇见》整片后，ASS 从 19 行增至完整 38 行，行间重叠为 0；分别抽查 20、140、190 秒画面均有单行字幕和染色。成片仍为 H.264 + AAC、212.053 秒，原录播未修改。
- 2026-09-05：按用户要求生成《遇见》整首 Folia 覆盖成片 `/vol1/1000/video/Folia成片/芒芒_Mou/2026-09-05/遇见_folia_overlay.mp4`。成片为 H.264 + AAC，时长 212.053 秒、大小约 90.4 MB；ASS 含 19 行有效逐字字幕，行间重叠为 0。原录播 SHA-256 再次确认未变化。
- 2026-09-05：修复 15 秒样片字幕挤在一起：无有效时间的未识别行不再被强制放到 00:00，样片 ASS 时间会随 `start_ms` 归零；对少量 ASR 行间重叠，成片按下一行开始时间截断上一行，保证单层字幕同一时刻只显示一行。重新生成《遇见》60–75 秒样片，ASS 共 6 行、起止时间均在 0–15 秒且互不重叠；抽帧确认单行逐字染色，视频为 H.264、音频为 AAC、时长 15.021 秒。原录播 SHA-256 保持不变。
- 2026-09-05：用现有《遇见》项目完整跑通“本地识别 → 标准歌词纠错 → Qwen 逐字对齐 → 15 秒样片”。新 Whisper 参数得到 25 个 ASR 片段（旧结果为 18）；过滤署名后共 38 行标准歌词，其中 19 行有可信时间、19 行保持未识别，保留 23 个黄色纠错字。实测发现并修复“长度接近但整句内容不同仍被全行纠错”的误判，长句现要求至少 2 个原样识别字且原样占比不低于 25%。Qwen 最终 19/19 行成功、0 失败，字符时间全部单调有效。样片保存为 `/vol1/1000/video/Folia成片/芒芒_Mou/2026-09-05/遇见_sample.mp4`，含 H.264 视频和 AAC 音频，时长 15.021 秒；ASS 含逐字 `\\kf` 且不含纠错黄色。原录播前后 SHA-256 一致。
- 2026-09-05：已部署“先识别、再用标准歌词改字”的纠错流程：整首 ASR 字符流可跨标准歌词分行对齐，平台署名行会被过滤，错字与补字保留原字来源，并仅在时间轴、Folia/Kinetic 编辑预览中显示黄色；ASS 成片明确忽略纠错色。小样本覆盖跨行、尾部错字、漏字和未唱行，前端语法、后端编译、effects 构建、浏览器黄色样式、ASS 无黄色及飞牛容器内算法测试通过；Web、API、worker 镜像均已重建，API 与 worker 健康、Web 新资源可用。没有重新处理现有项目，也没有读写原录播。
- 2026-09-04：逐字可见反馈改造已部署到飞牛；原版字幕、AMLL/Kinetic 与 ASS 成片均接入真实单字时间，时间轴新增“逐字成功/未逐字”标记和部分失败汇总。本机 `node --check`、effects 构建、Python 编译、浏览器时点测试和 ASS 时间测试通过；飞牛端完成 Python/Node 语法检查、Web/API 镜像构建与容器重建，API、worker、Web 首页、新脚本及 effects 资源健康检查通过。未用用户录播生成样片，避免覆盖同源已有样片。
- 2026-09-04：建立 `AGENTS.md`、根目录说明、状态页、架构页及四份模块文档，并同步到飞牛实际项目目录；未重启运行服务。
- 2026-09-02：Qwen 强制对齐在目标 CPU 上成功运行。
- 测试文本“我遇见谁会有怎样的对白”生成 11 个单字时间点。
- 对齐状态实测经历 `queued 0%` → `running` → `completed 100%`。
- 实测完成后已删除临时测试任务；未改动用户项目和录播。
- `studio-api`、`studio-web`、`local-worker` 部署后曾确认正常运行，API 与 worker 健康检查通过。

## 已知限制

本节包含历史观察；涉及混合时间轴、全曲重排与旧置信度门槛的描述已被后续改动替代，现行规则以模块文档和源码为准。


- 多源歌词站点可能独立限流或临时失败；搜索与候选解析会隔离单个平台/单个版本的失败，只要仍有可用候选就继续。低置信结果仍应先人工检查再运行 Qwen 或渲染。
- 只有新生成且明确标记为 `qwen-forced-aligner` 的逐字结果才参与平台逐字时间评分；旧项目保持原逻辑，除非重新执行相应对齐或标准时间轴匹配。
- `verify_standard_lyric_match_deepseek` 只能判断"选没选对歌"和给一个猜测的搜索关键词，猜词本身不保证准确（真实案例：《西楼》被 DeepSeek 建议按"西楼 等什么君"重搜，但"等什么君"其实是另一位歌手邓寓君的艺名，与这首歌无关，LDDC 搜索自然找不到真正对应的候选）。这类"AI 猜的搜索词本身就不准"导致重搜切换不到正确候选的情况，目前没有自动化兜底，最终会正常渲染并标记为 `DeepSeek 版` 供人工复核和手动重新指定标准歌词，不会被静默当成高置信。

- 2026-09-08：修复独立“ASR 语音转录”阶段即使勾选精细时间戳仍只输出最长 180 秒块级条目的问题。`stage=asr` 且未跳过对齐时现在会在 ASR 后自动运行 ForcedAligner，进度按 ASR `5%→75%`、对齐 `75%→100%` 展示；页面在完整处理和独立 ASR 中都显示“逐句时间戳”开关且默认开启。现有长录播可直接复用 `asr_chunks.json` 单跑对齐，不需要重新 ASR；对齐失败时保留原转录文件，不再用空结果覆盖。
- 2026-09-08：企业微信 ASR 完成/失败通知改为纯文字 `text` 消息，正文新增任务输出目录；同时修正转写 API 展示路径重复拼接 `jobs/jobs` 的问题。等待当时正在运行的长录播 ASR 完成后再部署，未中断任务。
- 2026-09-08：修复“录播转逐句文字”仅以链接跳转、进入后难以返回的问题；ASR 页面改为视频工坊内嵌第三工作区，顶部“歌词视频制作 / 歌单批量切片 / 录播转逐句文字”切换栏始终保留，ASR 页原返回链接也改为跳出内嵌页返回工坊顶层。

- 2026-09-05：验证逐字质量门槛：对《快乐女孩》项目重新执行 Qwen 逐字对齐并完整渲染，`42/42` 行成功、`0` 行触发异常回退，质量统计中压缩异常行 `0`；输出仍为 H.264 + AAC、195.051 秒，独立目录下成片可用。原录播未修改。
- 2026-09-05：优化逐字对齐质量：新增 Qwen 字符时间质量门槛，检测整句过度压缩、连续极短字时自动拒绝该结果并回退逐句/粗时间，避免“有 `\\kf` 但视觉上跳字”。仅重建 `studio-api`；容器内 Python 编译和 `/healthz` 通过。尚未重新跑片验证回退分支。
- 2026-09-05：使用现有《快乐女孩》项目 `66e0a8d8efe341fbb3578ba7a9f6b7e6` 重新生成完整成片，验证时间轴修复已进入实际渲染链路。输出 `/vol1/1000/video/Folia成片/芒芒_Mou/2026-09-05/快乐女孩/快乐女孩_folia_overlay.mp4`，H.264 + AAC，时长 `195.051` 秒；未重新识别，原录播未修改。
- 2026-09-05：修复逐字时间轴中“漏词/多词导致后续字幕提前”的问题：Qwen 投影不再对未匹配字符做整句全局线性分配，而是按左右可靠字符时间插值；渲染 ASS 时强制使用首字/末字作为整句边界，避免旧的粗粒度行时间提前触发字幕。已同步并仅重建 `studio-api`；容器内 Python 编译和 `/healthz`（`ok=true`、`render_busy=false`）通过。未重新识别或渲染项目，未修改原录播。仍需在下一首歌完整跑片时抽查漏词、多词和句间边界。

- 首次加载 Qwen 模型会明显变慢，占用约 5 GB 内存；worker 会在 Whisper 与 Qwen 之间卸载模型，避免同时常驻。
- Qwen 对齐依赖已经提供的标准歌词，它负责补齐逐字时间，不负责自动判断歌名。
- Qwen 逐字对齐目前没有“中止”按钮；批量切歌已有中止功能。
- Web 主脚本仍较集中，后续新增大型功能前应先按模块拆分，避免继续堆在 `web/app.js` 和 `backend/app.py`。
- 页面有 Basic Auth；自动化浏览器未携带凭据时会看到 401，不代表服务故障。
- AMLL 上游播放器没有提供稳定的单字“纠错色”接口；AMLL 仍使用纠正后的正文和字时间，黄色溯源以时间轴、Folia/Kinetic 编辑预览为准。成片不会显示黄色。

## 下一步候选

按优先级选择，不要在一次改动里全部实施：

1. 给 Qwen 逐字对齐增加中止与安全恢复。
2. 用一首完整歌曲人工抽查漏字、逐字时间和预览效果。
3. 将主 API 的 ASR、对齐、切片、渲染拆成独立模块。
4. 将前端工作台拆分为识别、时间轴、效果、切片四个脚本模块。
5. 基于稳定逐字数据继续改善歌词效果，而不是先堆更多预设。

## 维护规则

每次完成线上修改后，在本文件补充：日期、改动、验证方法、验证结果及仍存在的问题。不要把“聊天里说过”当作项目状态。

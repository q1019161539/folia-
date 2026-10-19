# 歌曲项目与高置信自动投稿（V2）

## 当前流程与边界

### 完整人物参考库与可选全身构图（2026-10-15，已部署）

用户纠正不应本地截上半身：完整透明PNG直接作为参考，提示词优先半身，适合歌曲内容与氛围时也允许全身，取消“不出现腿部或全身立绘”硬限制。经人工逐张复核16张，排除5张带话筒素材（正比4、Q版1），默认只启用6张无话筒正比完整图；5张无话筒Q版单独保留而不自动混用，原16张均保留不删。旧固定参考22-50-32确实带话筒，新库不再选择。

配置COVER_REFERENCE_CONFIG的主播项支持references列表，每项含id/path/sha256/has_microphone=false。以SHA-256(broadcaster_key+NUL+song_key)对按指纹排序后的池稳定映射，非随机，不引入收费视觉识别或自动情绪分类。同一歌曲项目已有成功封面/原图继续复用，不能为了换参考重新扣费。新参考写provided-full.png，字节及尺寸/透明度与所选PNG完全一致，不裁切、不缩放、不重新编码；reference_json保存参考ID/指纹/策略/crop=null，输入只发一张图。旧单图crop配置仅兼容历史，线上小红泡计划迁移到full-v1库；其他主播仍保持自己的选帧。

19项相关断网回归通过。首次部署预检遇到新整场ASR而停止；用户另行明确授权中断后，保存原任务，调用既有cancel并确认cancelled/重任务空闲后只更新API，随后通过原retry入口恢复该流水线。生产配置已切换full-v1池；未重启转录/渲染/录播/Bililive/Web容器。部署工具ops/reference-full-20261015/deploy.py分prepare/build/deploy；prepare仅一致性备份、build仅构建，真正deploy再次严格检查无重任务及外部请求。配置/素材写数据卷，不打包到镜像或Git；新模块未增加，Dockerfile既有COPY仍覆盖修改模块。

### Gemini主用（2026-10-15）

用户要求将已验证的Gemini改为主用。COVER_PRIMARY_PROVIDER=gemini使第一笔实际新生图直接使用原生Gemini 2K客户端，仍读取既有COVER_FALLBACK_*密钥/地址/模型配置，不迁移或输出密钥；保留GPT配置但不自动回切到已403的GPT。默认gpt保留旧部署兼容，其>5切备用规则不变；非法provider或Gemini未启用/未配置终态停止，不静默改走其他收费通道。控制接口及启用检查按当前主通道判断配置，投稿页显示Gemini/GPT主用，不再固定写GPT密钥。

小红泡今天10首GPT403封面失败任务经过单独授权恢复；只把明确10个未提交、无taskId/AID/BVID、无成功封面/冻结payload的原任务恢复pending，不新建歌曲或投稿行，不重置次数或水位。累计10次预算、付费并发1、600秒、无隐藏重试、缓存/重启恢复、权威身份、用户半身透明参考、书名号可选及投稿模板/合集策略不变。其他旧失败不自动恢复；已完成/已接受稿件不重新生图或上传。标题继续使用原gpt-6.1-sol，ASR/歌词/渲染不改。

### 封面书名号自由排版（2026-10-15）

用户认可无书名号封面，封面PROMPT改为左侧完整准确写出歌名，书名号可加可不加，由AI根据排版决定。保留人物身份、自然表情动作、右侧人物、独立歌曲场景及半身近景要求。此条替代下方历史记录中的强制《》约束，仅影响后续实际新生图请求；GPT主通道与Gemini备用共用，不改投稿AI标题/固定标题里的《歌名》。不清成功封面、原图缓存、冻结payload或次数，不重生成/重投。仍无OCR，不保证AI文字准确。

### Gemini备用与用户透明人物参考图（2026-10-15）

用户授权GPT累计失败/中断请求数严格超过5次后，下一次改用Gemini；总预算仍为每歌曲10次，不清零、不额外增加10次。前6次仍GPT，第7–10次在备用已配置时用Gemini；未配置备用保留原GPT行为。已有原始有效图片和成功封面优先恢复，后续Bililive错误不得重复生图。累计次数和cover_model请求前写库，额外保存attempt-N.json记录provider/model/参考指纹/提示词/状态，无密钥。重启未知请求仍占次数，无客户端隐藏重试。

配置COVER_FALLBACK_ENABLED=1、COVER_FALLBACK_BASE_URL、COVER_FALLBACK_MODEL=gemini-3-pro-image-preview、COVER_FALLBACK_API_KEY及可选COVER_FALLBACK_PROXY。备用独立密钥环境注入，原GPT/标题密钥不替换。用户要求先确认真2K后部署，已现场验证原生POST /v1beta/models/gemini-3-pro-image-preview:generateContent：contents含text+inlineData参考PNG，generationConfig.responseModalities=[TEXT,IMAGE]、candidateCount=1、imageConfig={aspectRatio:16:9,imageSize:2K}。网关仍接受Bearer鉴权，配置base若带/v1则构造原生路径时去掉；不改GPT原来的base。接收单张非thought的inlineData图片，不下载制品URL。HTTP429/5xx/网络/无效图可在剩余总预算内退避；400/鉴权错误终态停止。

独立原生2K实测一次HTTP200/88.52秒，API原始JPEG2752×1536（SHA256 f166798c2a12f051ebe575d3ea37a21d3b0b5d2f527e3c424c4e9f5b07e47886），未本地放大。原兼容/chat/completions只在提示词写2K而返回1376×768，现已不用于备用。生产客户端检查宽≥2048/高≥1152和横版比例，不再静默接受低分辨率；实际尺寸继续落库，原图保留，不叠字、不去水印。不据请求名证明实际后端模型。2K实测图漏书名号，已告知用户；纯尺寸校验不能证明AI文字准确，仍无OCR/收费视觉，不本地补字。

COVER_REFERENCE_CONFIG指向运行时JSON，以broadcaster_key精确匹配原始PNG路径、SHA256和crop。小红泡绑定bilibili:2516117，用户正比PNG裁剪(1500,350,2680,1250)，原图保留；GPT和Gemini都用这个半身副本。其他主播继续免费选帧，绝不按相似名字套用小红泡人物。已配置但素材损坏/指纹不符终止，不能静默用别人的图或选帧兜底。新提示词补充腰部以上半身近景、完整头饰顶部留安全距离；既有成功封面不重生成。

不新增数据库字段；保留权威身份、旧V1隔离、去重/高置信/响度/模板/上线水位、投稿及合集状态。当天显式恢复范围仅是原有4首未提交、封面失败且次数>5的芒芒任务：金风玉蝶、玻璃、我们俩、没关系。5次的你的酒馆对我打了烊和旧海绵宝宝/跳楼机不自动恢复。

### SQLite 临时锁与外部结果恢复（2026-10-12）

数据库使用 NAS 本地卷 WAL；app.db 只重试同一个 COMMIT，不重新进入包含 AI/上传的业务块。V2 的短 UPDATE 允许完整回滚后有限重试。SQLITE_BUSY/LOCKED 属于临时错误，准备保持 pending，提交/查询保留已有状态并写 next_retry_at；磁盘/损坏等错误不当作锁重试。

标题返回、上传返回 taskId、主任务返回 AID 先保存原子 checkpoint（歌曲资源目录 checkpoints/<publish_id>-title/accepted/published.json），再更新 DB。恢复只读取白名单结果和一致输入，不保存 Authorization/passkey；标题允许同身份的授权重制复用，上传/AID 与原输入和 payload SHA256 绑定。冲突停止处理，不新增 POST。封面使用现有原始图片缓存，不因 DB 锁重复生图；已知任务查询失效仍须核对，绝不自动重投。

每个 worker 实例首次 tick 只将精确锁错误、V2、无 taskId/AID/BVID、submit_attempts=0 的既有准备失败置 pending（提交前已有 payload 则 ready），不重置资源/次数。不接全库历史，不解除资格/水位/暂停。其他上传阶段历史错误需基于实际稿件人工核对恢复。这是局部可靠性修复，不是跨服务严格 exactly-once，也不引入 submit_unknown；双重存储均失败或请求响应丢失的残余风险仍存在。

完整自动成片 → 权威身份和高置信检查 → 按主播归档歌曲项目/去重 → AI投稿标题（固定标题兜底） → 免费选帧 → GPT完整封面 → 继承主播BililiveTool模板 → 参数校验 → BililiveTool上传 → AID完成、BVID/审核单独查询。

原视频工坊项目保留单次演唱。`publish_v2.py` 仅处理独立投稿状态，不回写原成片/ASR/歌词/渲染失败。B站登录、Cookie、分片上传和投稿API仍完全交给BililiveTool。旧本地叠字素材和预览接口保留，但新worker不调用旧prepare，不作为封面失败兜底。

## 资格、去重与上线水位

- 要求项目completed、完整非样片MP4、output与alignment.timeline_match均明确high、无song_identity_suspicious、已绑定本主播preset。缺置信度、local/deepseek对齐版、样片均不产生生图请求。
- 只使用identified_title/identified_artist/identity_source创建不可变输入快照，不读matched_*、显示/手工标题或LLM来替换身份。
- 主播键为录播平台+room_id，未绑定时profile ID；歌曲键按NFKC、繁简、空白、明确尾部括号Live/cover注记归一，不模糊匹配，不修改原身份。同名且已有明确歌手冲突时暂停人工核对。
- song_projects以(broadcaster_key,song_key)唯一；song_performances以source_job_id唯一，publish_jobs保留source_job_id唯一并新增song_project_id唯一。事务BEGIN IMMEDIATE保护并发归档。重复演唱只关联歌曲项目，记录未投稿原因，不重新生图。
- 历史publish_jobs默认pipeline_version=1，新worker只领取2。迁移不批量合并旧任务；已投稿/AID/BVID任务初始化为去重记录，即使稿件已删除也不重投。
- app_meta.publish_v2_rollout初始acceptance，白名单为空，只有显式选定的两首可以运行；两首均完成并取得AID才允许activate。激活后只接output.finalized_at高于cutover的新成片。使用渲染完成水位，不用可被编辑的updated_at误开历史补投。
- 历史补投只能指定白名单；没有全库自动补投或人工ready确认按钮。

2026-10-08 当前 mode=active、allowlist为空、cutover=1791411419.8232932。用户曾撤销历史补投，随后明确恢复芒芒既有逐帧批次26e223f70d714588b6e40cdca70e9fca，按原录播日期新到旧优先。authorized_render_batches显式保存batch_id+profile_id；只有归属匹配、项目render_revision_publish=1、完整smooth高置信、当前严格performance_gate pass及源stat匹配时才绕过水位/历史暂停区间。当前paused仍先拒绝；其他非授权项目遵循原水位。33首未投候选中3首重制失败不发布，已投5首不重投、3首本地版不投稿、望穿秋水低响度skip。没有下调全局cutover或启用逐首白名单，旧V1继续隔离，无全库历史补投。上文acceptance为初始/历史验收机制，非当前运行模式。

自动切片在创建项目前先过performance_gate低响度筛查，当前平均 RMS ≤−30 dB 或峰值 ≤−15 dB 任一满足即 skip，不产生任何生图/上传。publish_v2.eligible除拒绝显式skip外，在准备/提交边界按当前阈值重算已有测量，旧 AND pass 不得绕过新规则；已有筛查记录但测量缺失/非法时拒绝。授权批次还要求 quiet-clip-v2-any 版本、当前 settings 和源 stat 一致。新规则不撤回/重传已接受任务，不清空成功封面及请求次数。响度通过不证明是主播本人唱歌，较响原唱仍可能漏过，不能把这条保护当成声纹检测。

## 页面启用与暂停（2026-10-07）

投稿管理页“歌曲项目与投稿记录”顶部提供自动投稿开关，显示测试/开启/暂停、范围、首次启用与最近启用/暂停时间（上海时间）。初次启用前二次确认AI费用和真实投稿，只在两首验收均completed且取得AID后开放；PUBLISH_ENABLED、AUTO_PUBLISH_ENABLED及封面密钥仍为部署总门槛，页面不能绕过。部署此开关不会自行activate。

GET /api/publish-v2/control读取状态，POST同路径{enabled:boolean}持久化变更，严格布尔参数；旧activate入口复用相同检查。app_meta.publish_v2_rollout保留原acceptance/active并支持paused、resume_mode、paused_at、enabled_at、paused_periods。BEGIN IMMEDIATE串行化切换；重复启用不重设cutover，首次启用设当前时间，重启不会丢失状态。

暂停不创建新的投稿任务、不发起下一笔AI标题/封面请求或新上传；已发出的请求可以完成并保存，已接受的上传和审核仍查询，不取消、不重投。尚未提交的原队列/成功封面保留，恢复后继续；paused_periods排除暂停期间完成的成片，恢复不批量补投这些视频，不重设首次启用水位。测试模式另有“暂停测试任务”按钮；从暂停测试恢复需完成验收，才启用未来新成片。切歌/渲染不受开关影响。

## 免费选帧与GPT封面

2026-10-12 用户要求减少同场直播封面背景趋同，提示词追加：“参考图仅用于保持人物身份，不沿用直播背景。根据歌曲独立设计场景、主色调和光线，避免统一套用同一种背景风格。”原锁脸、允许表情/动作变化、人物右侧/歌名左侧及完整书名号约束不变。只影响后续实际新生图请求；既有成功封面/原图缓存/冻结 payload 不清空，不为此重生成、重投或增加请求数。提示词有助于背景差异，但无跨封面视觉检验，不能保证绝不趋同。

### 显式历史重制入队

render_revision_publish=1的新版完整高置信成片允许显式创建V2 pending；仅重制的项目不投稿。enqueue只控制任务落库，不绕过rollout白名单/水位/暂停，不自动进行AI付费请求或上传。未提交歌曲主任务可显式换用新版MP4并重新生成payload/校验，成功封面和已有AI标题复用；有任务ID/AID/BVID、已开始提交或上传/已完成的主任务不能更换源视频。render_revisions.publish_status独立记录pending/enqueued/ineligible/failed，投稿交接失败不改变新版或原版成片状态。旧V1记录继续隔离，不批量迁移。

2026-10-08 增加明确批次授权，enqueue本身仍不等于授权；仅上述authorized_render_batches合格分支可放行历史。publish_jobs.priority_at默认0，显式重制取recording_start_time，worker优先处理已有接受/提交任务，再按priority_at降序处理未提交任务，同优先级沿用created_at。已完成新版之间按原录播日期排序，不阻塞等待未完成新歌；成功封面/标题/payload及请求次数不重置。投稿页范围提示展示授权重制批次数，暂停对本批同样生效。

复用cover_frames.py的12候选、区域评分、画质过滤、去重、原尺寸PNG与缓存。投稿页配置0–1的左/上/右/下，预填实际核对的芒芒/小红泡区域；其他主播全画面评分局限明确提示。不使用收费视觉模型/OCR，不保证闭眼或遮挡判断。

环境：COVER_API_BASE_URL、COVER_API_KEY、COVER_API_MODEL，可选COVER_API_PROXY仅用于生图HTTP连接（NAS使用现有mihomo，不改变BililiveTool/其他流水线网络）；指定接口与请求模型gpt-image-2，单张2048×1152、quality=high，不据请求名证明真实后端模型。图片编辑接口使用原视频参考帧；用户对比后选择GPT锁脸版：保留脸型、五官比例、瞳色、发型和标志性配饰，不重新设计面部，允许表情、视线、动作和姿态随歌自然变化，不再锁死姿势。人物在右，左侧完整《歌名》，特别要求开头《及结尾》，背景/字体自由发挥，不加主播名或横线。提示词不能保证绝对人物保真或文字准确。

每首资源在/output/publish/songs/<song_id>/，包括参考帧及manifest、原始响应original-N.bin、格式原图original.png/jpeg/webp、可投稿cover.jpg。原图保留；只按整数16:9居中适配/JPEG，不叠字、不去水印、不放大。持久化实际提示词、模型请求名、时间点、生成次数、路径、尺寸与SHA。

单worker/进程锁保证付费并发1；httpx超时600秒、无隐藏重试。每首发请求前持久化次数，当前最多10次（2026-10-08用户明确由2次提高；是累计10次，不是额外10次）；网络/超时/5xx/坏图可余量内退避重试，鉴权/额度/明确参数错误终态停止。崩溃中的请求仍占一次；落盘原图可恢复，不再请求。已成功封面文件丢失或SHA不符需人工恢复，不自动再次扣费。BililiveTool失败重试只复用封面/已冻结payload。AI歌名文字不做自动核对，技术校验通过后自动继续。COVER_MAX_ATTEMPTS统一控制准备和请求边界；control接口返回cover_max_attempts，页面从接口读取显示/重试按钮上限。准备重试接口在没有成功封面且累计已达上限时返回409，不重置次数；已有成功封面的后续准备失败仍可复用。

## AI投稿标题（2026-10-07）

2026-10-08 用户要求歌名不带括号备注：title_generation.song_display_title 从权威歌名只派生展示文本，删除中英文圆括号及其内容（支持连续、嵌套和混用闭合）。投稿AI标题/固定兜底、GPT封面提示词、模板简介的title变量、tags和分P标题统一使用该文本。identified_title / identified_artist / identity_source、原歌词/成品、song_key及去重语义不改；不改已接受任务或既有冻结快照/成功封面，不重置次数重新扣费。清理后空歌名或括号不闭合时在付费请求前停止并提示人工核对。后续正常新准备直接应用，无需LLM执行清理。

title_generation.py使用用户核对的提示词：参考《离人赋》《晚夜微雨问海棠》的文案风格，只输出“emoji＋简短文案｜《歌名》｜【主播】翻唱”，不限定古风或意境描述。2026-10-08用户允许采用副歌歌词短句，准备阶段把项目已匹配标准歌词作为参考，只允许短句摘录（不超过10个汉字）或自然改写，不整段引用；未提供歌词时不编造歌词。不虚构现场/观众反应、不夸张营销。歌名、主播逐字保留，不超过80个字符，歌词内容不能用于覆盖权威身份。

配置AI_TITLE_ENABLED=1、TITLE_API_BASE_URL=https://www.codex789.com/v1、当前TITLE_API_MODEL=gpt-6.1-sol（2026-10-08用户指定）；TITLE_API_KEY仅运行环境，可选TITLE_API_PROXY。调用OpenAI兼容/chat/completions，httpx各阶段超时120秒；请求模型名不证明实际后端模型。旧45秒为客户端超时配置，不能据此判定模型本身故障。累计最多3次请求，超时/连接错误/429/5xx才在后台队列退避重试；400、鉴权/额度/明确参数错误、非法标题直接确定性兜底，无客户端隐藏重试。

严格校验完整歌名和主播后缀、单行、长度及emoji开头。临时错误仅在3次余量内短暂等待，下次后台prepare继续；耗尽或确定性错误使用固定标题，继续封面/投稿。title_generation_json在发请求前持久化attempts/in_flight，完成后保存history/耗时/脱敏错误/retry_pending；进程中断中的一次也算一次，不清零。请求前持久化失败不发请求；暂停请求边界保护保留。成功标题、终态兜底、成功封面和冻结payload继续复用，BililiveTool或封面重试不重新扣标题费。页面分别显示标题/封面次数，control返回模型、3次上限及120秒配置。没有身份字段写权限，不改已投稿或已冻结payload。

## 已核对的BililiveTool 3.18.0协议

### 单次指定演唱投稿维护（2026-10-19）

用户明确上传当天小红泡《要抱抱_02》，两遍合唱未执行。旧17日同名记录为已删除、创作中心172条无同名，今天两次仍被正常去重隔离。独立ops/publish-yaobaobao02-20261019/once.py只放行第二遍完整high成片，新投稿78cdc33b66245535a54bf8738175521b，AID117467137443746/BV12HnJ6HEN3，合集9133790 joined，初查审核中。复用封面／标题、简介展开当前录播日期，无新AI请求；新身份按第二遍权威字段快照，不补旧/候选歌手。

新任务先pipeline_version=1隔离，准备快照先持久化后校验；提交前落次数、返回ID先存专用receipt，再交接歌曲唯一主关联和pipeline_version=2供正常查询。首次已接受后通用checkpoint因song关联尚为空报错，专用receipt恢复未再次POST；顺序已修正，submit_attempts=1。旧发布核心字段不改，旧关联留在维护快照/原演唱历史，旧task/AID/BVID不清。此为显式单首例外，不改变自动同主播同歌去重，也不按稿件已删除批量重投。备份、共享路径核验、4项防重复测试及healthz通过；原MP4和封面不动，无服务重启或开关变化。

### 后续新任务的合集受跟踪步骤（2026-10-13）

当前3.18.0原实现创建稿件后另外加入合集；没有已验证的同一个B站请求加入合集字段。合集加入仍由BililiveTool SDK执行，不在Folia实现登录/投稿协议，不等审核通过。固定镜像上的可回滚适配只作用于options.foliaCollectionTracking=true的新任务：使用上传阶段已有CID，删除这个分支的getArchive详情依赖，持久化合集步骤并await请求、回查归属；非Folia请求不改。

GET /api/bili/folia-season/capabilities返回{version:1,durable:true}，GET /api/bili/folia-season/{aid}?uid=...返回持久化UID/AID/CID/seasonId/sectionId/title/taskId/status/attempts/error/nextRetryAt（毫秒）。沿用原passkey鉴权，没有历史补加接口。记录只保存白名单值，不存SDK客户端、Cookie或Authorization。

状态pending/processing/verifying/retry/joined/failed；单worker，累计最多6次流程尝试，请求前存次数，启动恢复，成功/损坏/人工错误不重试。已入目标合集只确认，其他合集不移动；小节归属明确校验，缺失时只允许唯一正片小节。412等待60分钟再查询，400/401/403人工处理，其他错误2分钟起指数退避。每次先查归属，响应丢失不直接重加；成功归属回查才joined。父上传completed/AID永远不因合集失败回退或重传。

用户2026-10-13后来明确授权用刚上传但早于适配部署的《游园惊梦》作单步测试，已真实确认joined/目标合集9133790。仅此维护脚本在严格核对MID/AID/标题/唯一CID和小节、备份后显式置collection_status并使用同一队列，不修改原payload。poll_collection以非NULL状态作为授权门槛，旧自动流程仍默认NULL而不补加；没有新增公开历史补加接口。真实合集步骤已验证，但尚无另一次新视频上传验证新opt-in回调。

Folia新payload在准备时检查适配能力、添加opt-in，提交前再次检查（包括重启后已有ready快照），不支持时停止POST保持退避；publish_jobs增加collection_status/error/attempts/next_collection_at，旧默认NULL不处理。合集检查独立于审核时间；页面区分“上传完成 · 合集待完成/失败”和“已加入合集”。用户2026-10-13已手工补齐旧稿件，不清旧快照，不为已有投稿排新合集任务。本版本没有额外真实投稿验收，下一条自然新投稿再核对实际结果。

### 显式歌词修正版重投（单首维护，不是自动重试）

2026-10-08用户自行删除《遇见》旧稿并明确要求对轴后重投。外置维护脚本repair-yujian-lyrics-and-repost.py先保存SQLite一致性/行快照，新增独立修正工坊项目；普通自动去重仍禁止重投。原completed记录不清空task/AID/BVID、身份或payload，成功封面/标题复用，无新AI请求。维护投稿行pipeline_version=1不由V2worker自动提交；准备快照先保存后校验，校验成功再事务转移song_projects.publish_job_id和唯一song_project_id主关联，旧演唱/旧发布结果留作历史。请求前保存submit_attempts=1，成功立即保存taskId；响应丢失需人工查任务，不自动第二次POST。取得AID后用现有poll取得BVID/审核。此授权只适用于指定修正版，不据稿件删除自动放行其他已投稿歌曲。

NAS侧run-yujian-repair-once.py使用进程文件锁、固定项目/投稿ID，普通队列等待最多12小时；不取消、重启其他任务。已知渲染完成但主状态滞留时恢复已有ID，不另POST。检查完整smooth MP4、歌曲时间质量、BililiveTool侧文件stat/封面SHA和旧稿已删除后才提交。终态渲染失败停止；本次首轮Chromium失败已显式重试一次，再失败不无限循环。已接受任务只查询，未知提交响应停止核对。运行日志/result.json位于/vol1/1000/docker/folia-yujian-repair-20261008/。这是外置运维工具，非新API运行模块，不改Dockerfile/镜像/自启动服务；每次操作复用部署环境的现有客户端，不持久化密钥。

- GET /api/preset/video/{id}；POST /api/bili/formatDesc {template,options}。
- 简介time由recorder_identity.recording_start_time读取，只读匹配原录播相对路径/文件stem及已绑定平台房间；兼容历史.flv转成.mp4，使用record_history.record_start_time毫秒值（分段录播开始，不是live_start_time、文件mtime或渲染/投稿时间），固定Asia/Shanghai。记录缺失/不可用时只按YYYY-MM-DD/HH-mm-ss_标题.mp4解析；冲突或无可靠时间在生图前终止准备。已冻结payload继续复用，不静默改写已投稿简介。
- 深拷贝完整config，只覆盖title/desc/tag/cover，其余tid、转载、声明及合集设置等保留。标题采用上述AI文案，不可用时回退{streamer}《{identified_title}》｜直播翻唱；简介继承主播模板并展开变量；tags确定性生成。
- 快照为{uid,videos:[{path,title}],config,options:{removeOriginAfterUploadCheck:false}}，不保存Authorization/passkey，先落库再校验。
- POST /api/bili/validUploadParams只传config；真实成功为HTTP200 success。
- POST /api/bili/upload传快照，读取taskId立即落库。
- GET /api/task?type=bili返回{list,runningTaskNum}；GET /api/task/{id}查询。父任务completed时output为AID字符串；取得AID即completed/success。
- GET /api/bili/platformArchiveDetail?aid=...&uid=...取archive.bvid/state/state_desc。审核中/拒绝/删除与上传完成分离，绝不因此重传。
- 有taskId只查询，已知task丢失时failed且提示核对；有AID/BVID或completed不提交。submitting无taskId先按新出现任务、完整标题、类型、启动时间可靠匹配；不匹配最多允许再POST一次。不实现严格exactly-once或submit_unknown，跨服务响应丢失仍存在重复投稿风险。没有真实重复返回样本，不猜错误码做duplicate识别。
- Folia/output → BililiveTool/app/Folia成片；/output-legacy → /app/历史Folia成片。严格目录边界、真实路径解析，不复制MP4；新封面写共享/output。源视频size/mtime在准备与提交前复核。

## 数据与页面/API

新增song_projects、song_performances；publish_jobs增加pipeline_version、song_project_id、failure_stage、submit_attempts、submit_started_at、submit_before_json、upload_progress、next_review_at、title_generation_json；规则增加cover_region_json。状态沿用pending/preparing/ready/submitting/uploading/completed/failed。投稿任务接口将title_generation_json解析为title_generation供检查。

GET /api/song-projects、GET /api/song-projects/{id}、GET .../{id}/cover（original/reference查询参数）提供歌曲、关联演唱、封面、身份快照、元数据和投稿详情。原有publish-jobs列表/详情扩展，retry只允许未提交的V2准备失败，不清空成功封面/次数；提交失败或已知taskId不得通过准备重试重投。POST /api/publish-v2/acceptance指定两首；POST .../activate须两首AID验收通过；GET/POST .../control供页面启用/暂停。生产入口仍受原有网页鉴权保护。

## 部署/回滚

备份SQLite一致性快照、compose/.env、backend/web/docs，确认队列/重任务空闲。只重建API/Web；新模块均显式加入backend/Dockerfile。凭据仅运行环境，不进Git/日志。NAS Git副本同步明确文件，保留其他改动。若验收未通过保持acceptance，不开放未来自动发布。回滚先关闭投稿/恢复旧API镜像，不删除成片、封面、投稿任务或已接受的BililiveTool任务。

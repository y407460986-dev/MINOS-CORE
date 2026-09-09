# MINOS-CORE 代码审核问题修复计划

**日期**: 2026-06-11
**范围**: 五个域审核发现的约 30 个问题,全部纳入,分 5 阶段修复
**前提**: 默认端点 `allincode.top` 经用户确认为可信,不在修复范围内
**性质**: 本文档仅为规划,不含代码改动

---

## 关键事实(影响排序)

`minos_core/ai_resilience/` 整层经 grep 确认**未被任何生产代码 import**,目前仅文档与自引用。因此其内部 bug 不影响线上运行,排在最后阶段。本计划中用户已确认韧性层也要修,故阶段 4 包含其完整修复,且修复后需补一条"接入生产链路"的集成验证。

---

## 阶段总览

| 阶段 | 主题 | 预估 | 风险 | 可独立交付 |
|------|------|------|------|-----------|
| 0 | 止血(小改) | 0.5 天 | 低 | 是 |
| 1 | 路径与边界校验 | 1-2 天 | 低 | 是 |
| 2 | 数据正确性根治 | 3-5 天 | 中高 | 否(内部咬合) |
| 3 | 并发与重复计算 | 2-3 天 | 中 | 是 |
| 4 | 结构债 + 韧性层 | 3-5 天 | 中 | 是 |

每阶段结束后运行:`cd "D:/MINOS-CORE" && python -m unittest discover -s tests -v`,确认全绿再进下一阶段。

---

## 阶段 0 — 止血(纯小改,零架构影响)

目标:用最小改动消除"安全暴露"和"数据静默丢失"两类立即风险。

### 0.1 平台 API 默认绑 127.0.0.1 + token 缺失拒绝启动
- **位置**: `minos_platform/app.py:35-41,68-83`、`minos_platform/cli.py:13`
- **根因**: token 未设只打 warning 全开放;`cli.py` 默认 `--host 0.0.0.0`,叠加后同网段任意主机可调全部接口。
- **改法**:
  - `cli.py` 默认 `--host` 改为 `127.0.0.1`,需要外网时由使用者显式传参。
  - `app.py` 鉴权中间件:`MINOS_PLATFORM_API_TOKEN` 未设置时,对所有非 localhost 请求返回 401(或启动时直接拒绝并打 error)。保留 localhost 放行以便本机开发。
- **验证**: 新增测试——未设 token 时远程请求被拒、localhost 放行;设置 token 后 Bearer 校验通过/失败两路。
- **新增网络暴露安全提示**: 在 README/启动日志明确"默认仅本机访问,开放外网需显式配 host + token"。

### 0.2 平台失败状态先 commit 再 raise
- **位置**: `minos_platform/routers/draft_runs.py:103-111`、`apply_review.py:116-123`、`exports.py:147-155`
- **根因**: `except` 里设 `status="blocked"` 后立即 `raise`,`commit()` 在 try/except 之后被跳过,异常触发回滚,失败 run 完全不入库。
- **改法**: 在每个 `except` 块内,设置 blocked 状态后显式 `await session.commit()` 再 `raise HTTPException`。仅提交状态变更字段。
- **验证**: 注入一个会失败的 run,断言 DB 中该 run `status=='blocked'` 且 `error_message` 非空。

### 0.3 undo/redo 栈 key 改为 (db_path, run_id)
- **位置**: `minos_desktop/services/run_service.py:50-68`
- **根因**: 类级共享 `_undo_stacks`/`_redo_stacks` 仅用 `run_id` 当 key,不同 db 的自增 run_id 会重复,多 db 时快照互相覆盖。
- **改法**: key 改为 `(self._store.db_path, run_id)` 元组。其余逻辑不动。
- **验证**: 构造两个不同 db_path、相同 run_id 的撤销场景,断言互不串扰。
- **备注**: 当前快照纯内存、进程重启即丢,与"持久化撤销"语义不符——本阶段只修串扰,落库与否留作后续(不在本计划)。

### 0.4 CORS 无效通配项清理
- **位置**: `minos_platform/app.py:54-65`
- **根因**: `allow_origins` 写 `localhost:*`,Starlette 精确比对不支持通配端口,永不命中,形成"已配置"假象。
- **改法**: 需要任意本地端口就改用 `allow_origin_regex=r"http://(127\.0\.0\.1|localhost):\d+"`;否则删除无效项只留实际用到的精确来源。
- **验证**: 测试预期允许的来源通过、预期拒绝的被挡。

### 0.5 坏 JSON 区分"文件为空"与"解析失败"
- **位置**: `minos_core/knowledge_base.py:349-361`(吞 `JSONDecodeError`/`OSError` 返回 `[]`)、`95-96`(空则报"解析为空")
- **根因**: 解析失败被静默转空列表,真实原因(损坏/编码/IO)被"解析为空"掩盖。
- **改法**: `_load_json_items` 捕获时保留原始异常上下文,对显式指定路径的解析失败 `raise` 带原因的错误;仅对"文件确实为空"返回空。
- **验证**: 分别用损坏 JSON、空文件、正常文件测三种结果。

---

## 阶段 1 — 路径与边界校验

目标:把现成但未被调用的 `InputValidator`(`validation.py:421` 起,工具完整)接到所有用户输入边界。纯加固,不动业务逻辑。

### 1.1 三处文件写入接路径遍历校验
- **位置**:
  - `minos_desktop/api/routes_knowledge.py:91-118`(`seed_dir` 读、`output_dir` 写、`family_key` 拼文件名)
  - `minos_desktop/api/routes_projects.py:20` + `schemas.py:30-37`(`drawing_path`/`output_dir`/`component_drawings`)
  - `minos_platform/routers/input_packages.py:42-53`、`review_patches.py:48-49`、`utils.py:16-39`(`safe_copy_input_file_or_dir` 名不副实)
- **根因**: 用户路径裸字符串直接拼接读写,可遍历到任意目录。CLAUDE.md 明确要求边界校验。
- **改法**:
  - 在每个边界对路径调 `InputValidator.validate_path_traversal(path, base_dir)`,base_dir 取 app 的 output_dir / 允许的数据根目录。
  - `family_key` 做字符白名单(仅 `[A-Za-z0-9_]`),拒绝含 `/ \ ..`。
  - `safe_copy_input_file_or_dir` 真正加入根目录校验,或改名去掉误导性的 "safe"。
- **验证**: 每个端点补 `../../../etc/...` 越界用例断言被拒;正常路径仍通过。

### 1.2 fixture 引用路径校验
- **位置**: `minos_core/adapters/fixture_json.py:137-141`
- **根因**: `evidence_path`/`review_patch_path` 来自 input_package,直接和 base_path 拼接读文件,无校验。
- **改法**: 拼接后调 `validate_path_traversal(path, base_dir=base_path)` 再读。
- **验证**: 构造越界引用断言被拒。

### 1.3 图片 base64 内联大小上限
- **位置**: `minos_core/adapters/multimodal.py:678-682`(`read_bytes()` 全读)、配合 `ocr.py:167` 2x 渲染
- **根因**: 大图纸全量 base64 拼 payload,内存峰值无上限保护。
- **改法**: 对单图字节数和总 payload 设上限常量(如单图 20MB、总 50MB),超限显式报错或降采样。
- **验证**: 超限图片触发明确错误而非 OOM。

---

## 阶段 2 — 数据正确性根治(本计划核心)

目标:根治"裸 dict + 就地修改 + ID 多套"的系统性问题。#2/#3/#4 共享"数据载体"根因,捆绑修复收益最大。**此阶段改动面最大、风险最高,需最充分的测试覆盖。**

### 2.1 ID 生成与 AP 阈值收敛为单一来源
- **位置**(现状散乱):
  - step_id: `pipeline_chain.py:672`(`P{i+1:02d}`)、`drawing_to_pfd.py:294,569`(`P{index*10}`/`P{int}`)、`generate_pfd.py:50`(`P{int}`)
  - pfmea_id: `pipeline_chain.py:1014`(`:02d`)、`pfd_to_pfmea_ai.py:110`、`generate_pfmea.py:156`(`:03d`)
  - cp_id: `generate_control_plan.py:237`(`CP-{pfmea_id}` 不带序号)、`pipeline_chain.py`(带序号)
  - AP 阈值: `pfd_to_pfmea_ai.py:437`、`generate_pfmea.py:160`、`three_table_linkage.py:572`、prompt 内
- **根因**: 同一语义多处各写一套,跨表对齐靠 step_id 字符串相等,格式不一即断链;cp_id 不带序号导致下游 `_dedupe_key`(`stage/_utils.py:28`)把不同 CP 当重复删掉(静默丢数据)。
- **改法**: 新建 `minos_core/_id_factory.py`(或并入 `_table_constants.py`):
  - `make_step_id(index)`、`make_pfmea_id(index)`、`make_cp_id(pfmea_id, index)` 三个统一函数,固定补零格式。
  - `judge_action_priority(severity, occurrence, detection)` 单一 AP 判定函数。
  - 全管线所有生成点改为调用这些函数,删除各处内联格式串。
- **验证**:
  - 单元测试覆盖三个 id 工厂的格式与边界(index=0、大 index)。
  - AP 判定函数与 AIAG-VDA 规则逐档对照测试。
  - 端到端:同一份输入跑完三表,断言 step_id↔pfmea_id↔cp_id 跨表能对齐。
- **顺序**: 先建工厂 + 测试(RED→GREEN),再逐个替换调用点,每替换一处跑一次测试。

### 2.2 联动 gap_id 撞车修复
- **位置**: `minos_core/three_table_linkage.py:381` 与 `:547`(都生成 `GAP-SPEC-CHAR-PFMEA-{step_id}-{pfmea_id}`)、去重在 `:674`
- **根因**: `special_char_step` 与 `special_char_pfmea` 两类语义不同的 gap 共用同一 gap_id,`_deduplicate_gaps` 保留第一个,后者基本永不出现。
- **改法**: 先确认这两个检查是否本就重复:
  - 若语义确实不同:给两处 gap_id 加区分段(`...-STEP-` / `...-PFMEA-`)。
  - 若实为重复:删其一并在注释说明。
- **验证**: 构造同时触发两类缺口的链,断言两条 gap 都出现在结果且 category_key 正确。

### 2.3 domain 模型不可变化 + 管线改"返回新对象"
- **位置**: `minos_core/domain.py`(全部 dataclass 无 `frozen=True`)、`pipeline_chain.py`、`drawing_to_pfd.py`、`generate_pfd.py` 等就地改 step/row 处
- **根因**: 有 `domain.py` 不可变模型却几乎不用,全程传 dict 并 `step[...]=...`;confirmed 快照与流转对象共享引用,后续就地改会回写快照。
- **改法**(分两步,降风险):
  - **2.3a 快照隔离(先做,小而关键)**: `pipeline_chain.py:898,1182` 存快照前 `copy.deepcopy`,立即阻断"快照被回写"。
  - **2.3b 不可变化(后做,面大)**:
    - `domain.py` 能加 `frozen=True` 的 dataclass 加上(`Product`/`ProcessStep`/`FailureMode`/`ControlItem` 等)。
    - `APQPChain` 自定义 `__init__`(:574)使类级字段声明(:559-572)失效——改回标准 dataclass 或删除误导性声明。
    - `model_dump`(:704-714)对 list 字段做浅拷贝,避免暴露内部可变引用。
    - 管线中就地修改改为"输入对象、返回新对象"(`{**old, field: value}` 或 `dataclasses.replace`)。
- **验证**:
  - `frozen=True` 后跑全量测试,逐个修复因冻结暴露的就地修改点。
  - 新增测试:对 domain 对象 dump 后修改返回值,断言原对象不变。
  - 快照测试:确认后下游任何修改不影响已存快照。
- **风险控制**: 2.3b 可能触发大量测试失败(正是暴露隐藏就地修改),按文件逐个推进,不要一次全改。

### 2.4 _dedupe_key 缺 id 回退内容哈希
- **位置**: `minos_core/stage/_utils.py:22-40`
- **根因**: 去重键按 `pfmea_id`→`process_step_id` 取第一个非空,两条 pfmea_id 都空、step_id 相同的不同失效行会被当重复删掉。叠加 2.1 的 cp_id 问题,丢行风险加重。
- **改法**: 缺 id 时回退到行内容哈希(关键字段拼接 hash),而非回退到 step_id。
- **验证**: 构造两条 step_id 相同但内容不同、均无 id 的行,断言都保留。

---

## 阶段 3 — 并发与重复计算

目标:消除并发覆盖、重复 LLM 调用、SSE 泄露。

### 3.1 编辑操作收进单事务/乐观锁
- **位置**: `minos_desktop/services/run_service.py:915-945`(apply_edit_patch)、`1162-1202`(save_with_undo)、`1204-1234`(undo/redo)
- **根因**: read-modify-write 跨多个独立连接独立事务,中间无锁,并发请求后写覆盖先写丢编辑;后台生成任务与用户编辑并发尤其危险。
- **改法**(二选一,推荐乐观锁):
  - **乐观锁**: envelope 加 `version` 字段,`UPDATE ... WHERE version = ?`,冲突时返回明确错误让前端重试。
  - **单事务**: 把"读 envelope→改→写回"收进同一连接的同一事务。
- **验证**: 模拟两个并发编辑同一 run,断言不丢更新(乐观锁路径返回冲突,而非静默覆盖)。

### 3.2 assemble 阶段消除重复跑
- **位置**: `minos_core/stage/__init__.py:281-321`
- **根因**: fixture 非 dict 分支里 control_plan/pfmea/pfd 各 `run_stage` 一次,而 control_plan 内部又自跑 pfmea→pfd→brainstorm,导致 PFD 约跑 4 次、PFMEA 约 2 次,LLM 入口下重复烧钱。
- **改法**: 先跑一次拿 pfd_result,后续阶段复用其 output,不从原始 fixture 重跑。
- **验证**: 用计数 mock 断言每阶段只跑一次;端到端结果不变。

### 3.3 SSE channel 鉴权 + 泄露清理
- **位置**: `minos_desktop/api/app.py:76-79`、`routes_sse.py`、`sse.py:15`、`run_service.py:565-567`(progress 带 `new_rows`)
- **根因**: SSE 流不鉴权,本机任意进程可订阅,progress 事件含生成中的 PFMEA 行内容(业务数据);`_channels` 全局 dict 无上限,无人订阅的 channel 只靠订阅端心跳超时兜底,会缓慢泄露。
- **改法**:
  - 给 SSE 端点加与其它端点一致的 token 校验(query param 或 header)。
  - channel 加创建时间戳 + 后台清理(或在后台任务 try/finally 里确保 `remove_channel`),不依赖订阅端心跳。
  - 修正"无 secrets"的不准确注释。
- **验证**: 无 token 订阅被拒;无人订阅的 channel 在超时后被回收(断言 `_channels` 不增长)。

### 3.4 multimodal HTTP 错误脱敏对齐
- **位置**: `minos_core/adapters/multimodal.py:364-371`
- **根因**: 同项目 `openai_llm.py:203-213` 已 `redact_sensitive_data`,multimodal 却 `from exc` 把原始 HTTPError 挂异常链,上层打完整 traceback 时第三方响应可能进日志。
- **改法**: 统一成 `openai_llm.py` 做法——读 body→脱敏→截断后放进错误消息;不直接 `from exc` 原始对象(或确保 body 不入链)。
- **验证**: 构造带敏感内容的 HTTP 错误响应,断言日志/异常消息中已脱敏。

---

## 阶段 4 — 结构债 + 韧性层

目标:拆超限文件、统一日志、外置硬编码样例数据、修复并接入韧性层。

### 4.1 超 800 行文件拆分 + structlog 统一
- **位置(超限文件)**: `table_editor.py`(2118)、`run_service.py`(2083)、`edit_patch.py`(1448)、`pipeline_chain.py`(1418)、`part_family_knowledge.py`(1374)、`drawing_to_pfd.py`(1294)、`drawing_ocr_analysis.py`(1082)、`knowledge_recommendation.py`(894)、`drawing_analysis.py`(887)、`multimodal.py`(839)、`live_linkage.py`(857)、`domain.py`(826)、`closure_tasks.py`(815)
- **改法**(按职责拆,逐文件独立 PR):
  - `table_editor.py` → 纯函数集合,拆 `table_model.py`/`automation_review.py`/`navigation.py`/`review_dashboard.py`。
  - `run_service.py` → 拆出"链式生成编排"与"undo/redo 栈",主类只留持久化。
  - `pipeline_chain.py` → prompt/schema 常量拆文件,并行批处理抽公共 helper;**同时把混用的标准 `logging`(:23)全改 structlog,删 `logger`**。
  - `multimodal.py` → prompt 文案 / payload 构造 / 流式解析分文件。
  - 其余按相同原则拆。
- **风险控制**: 纯拆分不改逻辑,每拆一个文件跑全量测试确认行为不变。优先拆 `table_editor.py`(纯函数,零风险高收益)。

### 4.2 样例数据硬编码外置
- **位置**:
  - `pipeline/hybrid_fusion.py:18`(`SUSPECT_OCR_TOKENS=("D00R","HIMGE")` 把某次具体识别错误写死)
  - `generate_pfd.py:11-15`(`_STEP_CHARACTERISTIC_RULES` 特性绑死 P10/P20/P30 工序号)
  - `part_family_knowledge.py:147-283`(`PROFILES` 只为 3 个族写死列映射,`:1001` 其他族直接 raise,但分类器能识别 15 个)
- **改法**:
  - OCR 可疑词:改为通用"OCR 身份置信度 + 字符合理性"校验,或词表外置成配置。
  - 特性规则:改按特性内容/工序语义匹配,不按工序号。
  - 零件族列映射:外置为按族配置文件;或明确文档"XLSX 转换仅支持这 3 个模板,其余走 JSON",并让分类器与转换能力对齐。
- **验证**: 换不同工序号/不同 OCR 错法/第 4 个零件族,断言不再误判或生硬 raise。

### 4.3 变更影响 item_id 稳定化
- **位置**: `minos_core/change_management.py:123-132`(`item_id = f"{target}.{kind}.{message}"`)
- **根因**: message 是长中文句,文案一改 ID 就变,已 resolve 的记录"复活"、去重失效。
- **改法**: ID 用稳定字段组合(target + kind + 目标行 id),message 单独存字段。
- **验证**: 改 message 文案,断言同一影响 ID 不变、resolve 状态保持。

### 4.4 空 candidate_id 唯一化
- **位置**: `minos_core/special_characteristic_candidates.py:213-216`、调用处 `:34`
- **根因**: confirmed 分支不校验 candidate_id 非空,空 id 时 `_confirmed_characteristic_id` 返回固定 `SC-001`/`CC-001`,多个空 id 撞号且可能与真实编号冲突。
- **改法**: confirmed 分支也要求 candidate_id 非空,或用全局自增/哈希生成唯一 ID。
- **验证**: 多个空 candidate_id 断言生成互不相同且不撞真实编号。

### 4.5 就地修改入参改副本返回
- **位置**: `special_characteristic_declarations.py:67-75`、`special_characteristic_candidates.py:89-100`
- **根因**: 原地改传入 dict 再返回,与 `characteristic_registry`(用 deepcopy)风格不一致,易产生隐藏副作用。
- **改法**: 改为基于副本返回新对象。
- **验证**: 调用后断言原始入参未被修改。

### 4.6 韧性层修复 + 接入生产链路
- **位置**: `minos_core/ai_resilience/`(circuit_breaker / service_pool / retry_strategy / fallback / service_pool)
- **前提事实**: 该层当前未被任何生产代码 import。用户确认要修并启用。
- **改法**:
  - **circuit_breaker.py**: 给 `_state`/`_failure_count`/`_success_count` 读改写包 `threading.Lock`(`call` 判断+记录的临界区)。
  - **service_pool.py:100-167**: `get_next_endpoint` 记录本轮已尝试端点并跳过,实现按优先级真正逐个 failover,而非每次返回第一个。
  - **retry_strategy.py:138-168**: `create_default_retry_strategy`/`execute` 把 `is_retryable_error` 设为默认 `should_retry`,避免 401/400 被无脑重试。
  - **llm_text.py:185 等** 指数退避加 `max_delay` 显式封顶。
- **接入**: 把适配器调用包进韧性层(熔断 + 重试 + failover),这是**新增集成点,需端到端验证**。
- **验证**:
  - 并发压测熔断器状态机正确(无竞态)。
  - 模拟多端点失败,断言真正轮转到次优先级而非反复打第一个。
  - 401/400 不重试、429/5xx 重试。
  - 接入后端到端跑通三表生成,确认韧性层不破坏正常路径。
- **风险控制**: 修复(改 ai_resilience 内部)与接入(改适配器调用)拆成两步,各自独立验证。先修内部并补单测,绿了再接线。

### 4.7 低优先级零散项(随手清理)
- ThreadPoolExecutor `max_workers=len(batch)` 改固定 `PARALLEL_BATCH_SIZE`,防 batch 空崩溃(`pipeline_chain.py:818,1109`)。
- 多处 `except Exception: pass` 至少加 `logger.warning`(`settings_store.py:49`、`api_key_store.py:68` 等),keyring 读失败别静默变"未配置"。
- 置信度阈值散落硬编码(0.85/0.78/0.75)集中为命名常量。
- LLM 输出递归归一化加最大深度参数(`drawing_analysis.py:786-861`)。
- `recent_projects` 统一走 `DesktopSQLiteStore.connect()`(`routes_projects.py:42`)。
- PPAP `ready_for_submission` 三处逻辑抽单一判定函数(`ppap_packages.py:49,74,196`)。
- 公差正则仅在含 ± / 公差关键词时取值,排除螺纹/型号串(`semantic_review.py:273`)。
- 声明计数正则放宽位数(`special_characteristic_declarations.py:18,27`)。

---

## 跨阶段约束(每阶段都遵守)

- **测试先行**: 每个修复点先写能复现问题的测试(RED),再实现(GREEN),覆盖率维持 ≥80%。
- **手术刀式**: 只改追溯得到本计划条目的行,不顺手优化相邻代码。
- **不可变优先**: 新代码一律"返回新对象不就地改"。
- **结构化日志**: 一律 structlog,禁 `print()`,敏感数据过 `redact_sensitive_data`。
- **每阶段收尾**: `cd "D:/MINOS-CORE" && python -m unittest discover -s tests -v` 全绿 + `pip check` 通过。
- **流程图同步**: 按 CLAUDE.md 要求,每阶段改动同步更新 `project_flow.mmd`。

---

## 阶段依赖与建议顺序

```
阶段0(独立) ──┐
阶段1(独立) ──┼─→ 可并行起步
阶段3(独立) ──┘
阶段2(核心,内部 2.1→2.2→2.3a→2.3b→2.4 有序)── 依赖最重,单独推进
阶段4(独立,4.6 修复→接入两步)
```

- 阶段 0/1/3 之间无强依赖,可按人力并行。
- 阶段 2 内部有序、风险最高,建议独占一段时间专注完成。
- 阶段 4 的拆分(4.1)最好放在阶段 2 之后做,避免与数据载体重构争抢同一批文件。

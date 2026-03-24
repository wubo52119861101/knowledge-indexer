# 技术方案

## 1. 方案概览

### 1.1 目标

围绕一期当前四个限制点，完成以下优化：

1. 将 `/internal/ask` 从“检索结果拼装”升级为“检索 → 可选 rerank → 大模型生成 → 兜底响应”的正式问答链路。
2. 为同步任务提供可取消的 HTTP 接口，并让 `CANCELLED` 成为正式可观测状态。
3. 将 `rerank` 从占位扩展点升级为可配置、可启用、可降级的标准能力。
4. 让 `pipeline_engine` 按实际执行分支返回真实信息，而不是固定文案。

### 1.2 设计原则

- **接口基本兼容**：保留现有 `/internal/search`、`/internal/ask`、`/internal/jobs/{id}` 路径与请求结构；仅做响应字段追加和新接口补充。
- **先抽象、后替换**：优先补齐服务抽象和配置开关，不强依赖二期完整基础设施。
- **默认安全降级**：LLM、rerank、外部 pipeline 任一不可用时，自动退回内置能力，主链路仍可用。
- **软取消优先**：本期采用“安全检查点尽快停止”的软取消方案，不引入进程级强杀。
- **可观测优先**：新能力必须能通过 API/健康信息准确表达当前执行来源和降级结果。

### 1.3 本期默认决策

针对 `requirements.md` 中未决问题，本方案先按以下默认决策推进，后续如需调整可在实现阶段做配置化：

- `/internal/ask` **维持现有入参结构不变**，响应做“向后兼容的追加字段”。
- LLM 接入采用 **统一 HTTP Provider 抽象**，不在本期绑定单一厂商；若未配置则走兜底回答。
- `rerank` 采用 **全局配置开关**，本期不增加按请求开关，避免放大 API 变更面。
- 任务取消采用 **软取消 + 检查点终止**；`RUNNING` 任务会先进入 `CANCELLING`，最终落到 `CANCELLED`。
- `pipeline_engine` 暴露位置覆盖：`/health`、`/internal/ask`、`/internal/search`、`/internal/jobs/{id}`。

---

## 2. 整体架构设计

### 2.1 当前现状与根因

结合现有代码，问题根因如下：

- `app/services/qa_service.py` 当前直接调用 `RetrievalService.search()` 后拼接文本，不存在生成器抽象、提示词构造、模型调用和失败降级分层。
- `app/models/common.py` 中 `JobStatus` 仅有 `PENDING/RUNNING/SUCCEEDED/FAILED`，`app/api/jobs.py` 也没有取消入口。
- `app/services/indexing_service.py` 的执行循环没有取消检查点，任务一旦开始就会一路执行到结束。
- `app/api/health.py` 当前只暴露 embedding 占位信息，没有统一的执行引擎解析器，导致 `pipeline_engine` 无法真实表达。
- `app/core/container.py` 中问答、检索、同步流程都直接绑定内置实现，没有 `rerank` / LLM / pipeline resolver 的统一注入点。

### 2.2 目标架构

#### 2.2.1 问答链路

```text
/internal/ask
  -> QaService (Orchestrator)
     -> RetrievalService.search()
     -> EvidenceEvaluator
     -> RerankService.rerank()   # 可选
     -> AnswerGenerator.generate()  # 可选 LLM
     -> FallbackAnswerBuilder
     -> AskResponseData
```

问答链路由现有“单层 QaService”升级为“编排式 QaService”：

- `RetrievalService` 继续负责召回与 ACL 过滤。
- 新增 `RerankService` 抽象，用于对候选证据重排。
- 新增 `AnswerGenerator` 抽象，用于封装 LLM 调用与超时/异常处理。
- 新增 `EvidenceEvaluator` 或等价逻辑，统一判定证据是否充足、是否允许进入生成阶段。
- 新增 `FallbackAnswerBuilder`，统一处理证据不足、模型不可用、模型报错时的兜底语义。

#### 2.2.2 任务执行与取消链路

```text
POST /internal/sources/{source_id}/sync
  -> create_job()
  -> JobRunner.submit(job, flow)
  -> IndexingService.run_job()
     -> cancellation checkpoints
     -> terminal status

POST /internal/jobs/{job_id}/cancel
  -> JobService.request_cancel(job_id)
  -> JobRunner / IndexingService observe cancellation
  -> CANCELLING -> CANCELLED
```

为满足“运行中可取消”而又不强依赖 Redis 队列，本期补一个轻量级执行抽象：

- 新增 `JobRunner`/`JobExecutionRegistry`，负责登记任务执行句柄与取消标记。
- 兼容现有 `SYNC_RUN_INLINE`：
  - `true`：继续内联执行，适合本地快速验证；但 `RUNNING` 取消能力仅 best effort。
  - `false`：改为进程内后台执行（线程池或 `asyncio.to_thread`），便于通过独立 HTTP 请求发起取消。
- `IndexingService.run_job()` 在关键检查点读取取消标记，尽快终止。

> 说明：为了满足需求，“支持 `RUNNING` 任务取消”的标准能力以 `SYNC_RUN_INLINE=false` 的后台执行模式为准；`inline` 模式保留开发兼容，但不作为联调推荐模式。

#### 2.2.3 pipeline_engine 解析链路

```text
PipelineEngineResolver
  -> resolve_for_request(scene)
  -> resolve_for_job(source_type, mode)
  -> return PipelineEngineInfo
```

新增统一的 `PipelineEngineResolver`，作为所有对外 `pipeline_engine` 字段的唯一来源：

- 内置执行：返回 `type=builtin`，`name=knowledge-indexer` 或具体内置 flow 名称。
- 外部执行：返回 `type=external`，`name` 为配置的引擎标识，例如 `cocoindex`。
- 任务对象在创建时记录当次解析出的 `pipeline_engine`，避免查询时受运行期配置漂移影响。

### 2.3 建议新增/修改模块

#### 现有文件修改

- `app/core/config.py`
- `app/core/container.py`
- `app/api/internal_ask.py`
- `app/api/internal_search.py`
- `app/api/jobs.py`
- `app/api/health.py`
- `app/services/qa_service.py`
- `app/services/job_service.py`
- `app/services/indexing_service.py`
- `app/schemas/retrieval.py`
- `app/schemas/job.py`
- `app/models/common.py`
- `app/models/job.py`
- `docs/usage.md`

#### 建议新增文件

- `app/services/rerank_service.py`
- `app/services/answer_generator.py`
- `app/services/pipeline_engine_service.py`
- `app/services/job_runner.py`

上述拆分的目标是将“问答编排”、“任务执行控制”、“执行引擎解析”从当前单文件逻辑中解耦，便于后续替换外部能力。

---

## 3. 接口 / 数据结构定义

### 3.1 配置项扩展

建议在 `app/core/config.py` 中新增以下配置：

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `LLM_ENABLED` | `false` | 是否启用大模型生成 |
| `LLM_PROVIDER` | `http` | 大模型 provider 类型，先保留统一 HTTP 抽象 |
| `LLM_BASE_URL` | `None` | 大模型服务地址 |
| `LLM_API_KEY` | `None` | 大模型鉴权信息 |
| `LLM_MODEL` | `None` | 模型名 |
| `LLM_TIMEOUT_SECONDS` | `8.0` | 单次生成超时 |
| `ASK_EVIDENCE_TOP_N` | `3` | 进入提示词的证据条数 |
| `ASK_MAX_CONTEXT_CHARS` | `4000` | 生成上下文长度上限 |
| `RERANK_ENABLED` | `false` | 是否启用 rerank |
| `RERANK_PROVIDER` | `http` | rerank provider 类型 |
| `RERANK_BASE_URL` | `None` | rerank 服务地址 |
| `RERANK_API_KEY` | `None` | rerank 鉴权信息 |
| `RERANK_TIMEOUT_SECONDS` | `3.0` | rerank 超时 |
| `RERANK_TOP_N` | `10` | rerank 候选窗口 |
| `PIPELINE_ENGINE_TYPE` | `builtin` | `builtin` / `external` |
| `PIPELINE_ENGINE_NAME` | `knowledge-indexer` | 当前执行引擎标识 |
| `JOB_RUNNER_MODE` | `inline` | `inline` / `background` |

说明：

- `JOB_RUNNER_MODE` 与现有 `SYNC_RUN_INLINE` 可在实现阶段做兼容映射，避免一次性删除旧配置。
- 所有外部能力默认关闭，未配置即不生效。

### 3.2 新增数据结构

#### 3.2.1 `PipelineEngineInfo`

建议新增统一模型，作为所有 `pipeline_engine` 字段的结构化值：

```python
class PipelineEngineInfo(BaseModel):
    type: Literal["builtin", "external"]
    name: str
    scene: str
```
```

字段语义：

- `type`：引擎类型，区分内置或外部。
- `name`：引擎名称，如 `knowledge-indexer`、`cocoindex`。
- `scene`：执行场景，如 `ask`、`search`、`sync`。

#### 3.2.2 `JobStatus` 扩展

建议将 `app/models/common.py` 中的 `JobStatus` 扩展为：

```python
PENDING
RUNNING
CANCELLING
CANCELLED
SUCCEEDED
FAILED
```

状态说明：

- `CANCELLING`：已收到取消请求，但执行线程尚未在检查点停止。
- `CANCELLED`：已停止后续处理，不再推进 checkpoint、`last_sync_at`、成功态落库。

#### 3.2.3 `IndexJob` 扩展字段

建议在 `app/models/job.py` 中新增：

- `pipeline_engine: PipelineEngineInfo | None`
- `cancel_requested_at: datetime | None`
- `cancel_requested_by: str | None`
- `cancel_reason: str | None`

这些字段用于支持取消审计和执行来源追踪。

### 3.3 `/internal/ask` 响应扩展

现有请求结构保持不变，建议将 `AskResponseData` 扩展为：

```python
class AskResponseData(BaseModel):
    answer: str
    citations: list[SearchItem]
    evidence_status: EvidenceStatus
    reason: str | None = None
    answer_mode: Literal["generated", "fallback"] = "fallback"
    pipeline_engine: PipelineEngineInfo
    rerank_applied: bool = False
```
```

兼容性说明：

- 原有字段全部保留。
- 新增字段均为追加字段，对上游 JSON 解析兼容。

### 3.4 `/internal/search` 响应扩展

建议将 `SearchResponseData` 扩展为：

```python
class SearchResponseData(BaseModel):
    items: list[SearchItem]
    pipeline_engine: PipelineEngineInfo
    rerank_applied: bool = False
```
```

说明：本期 `rerank` 主要作用于问答证据排序；若后续需要，也可对纯搜索场景复用同一能力。

### 3.5 `/internal/jobs/{job_id}` 响应扩展

建议将 `JobItem` 扩展为：

- `pipeline_engine: PipelineEngineInfo | None`
- `cancel_requested_at: datetime | None`
- `cancel_requested_by: str | None`
- `cancel_reason: str | None`

### 3.6 新增取消任务接口

#### 接口定义

- **Method**：`POST`
- **Path**：`/internal/jobs/{job_id}/cancel`

#### 请求体

```json
{
  "operator": "system",
  "reason": "manual cancel"
}
```

#### 响应体

直接复用扩展后的 `JobItem`，方便调用方立刻拿到当前状态：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "id": "job_xxx",
    "status": "CANCELLING",
    "cancel_requested_by": "system"
  },
  "request_id": "req_xxx"
}
```

#### 状态码约定

- `404`：任务不存在。
- `200`：取消成功，或任务已处于 `CANCELLING/CANCELLED`（幂等）。
- `409`：任务已完成（`SUCCEEDED/FAILED`），不可取消。

### 3.7 `/health` 响应扩展

建议在 `app/api/health.py` 中追加：

```json
{
  "pipeline_engine": {
    "type": "builtin",
    "name": "knowledge-indexer",
    "scene": "service"
  },
  "llm": {
    "enabled": false,
    "status": "disabled"
  },
  "rerank": {
    "enabled": false,
    "status": "disabled"
  }
}
```

`health` 中的能力信息表达“默认配置态”；实际请求/任务仍以各自返回值为准。

---

## 4. 核心逻辑说明

### 4.1 问答链路执行逻辑

建议保留 `QaService` 名称，但将其升级为编排服务，核心流程如下：

1. 先调用 `RetrievalService.search(question, candidate_top_k, filters, acl_context)` 获取候选证据。
2. 用统一的证据判定逻辑校验：
   - 命中数 `< MIN_EVIDENCE_COUNT` → 直接返回 `INSUFFICIENT`。
   - 最高分 `< SEARCH_SCORE_THRESHOLD` → 直接返回 `INSUFFICIENT`。
3. 若 `RERANK_ENABLED=true` 且 provider 配置完整：
   - 对候选结果执行 `rerank(query, items)`。
   - 若超时/报错，记录日志并降级到原始排序，`rerank_applied=false`。
4. 选择前 `ASK_EVIDENCE_TOP_N` 条证据构建 prompt。
5. 若 `LLM_ENABLED=true` 且 provider 配置完整：
   - 调用 `AnswerGenerator.generate(question, evidence_items)`。
   - 若成功，返回 `answer_mode=generated`。
   - 若超时/限流/报错，进入 fallback。
6. fallback 输出统一模板：
   - 证据不足：返回固定“不足以回答”语义。
   - 生成失败但证据充分：返回“已找到相关依据，但生成失败，请参考引用内容”的保守答复。
7. 始终返回 `citations`，并保持顺序与最终参与回答的证据顺序一致。

### 4.2 Prompt 组织原则

为降低幻觉风险，prompt 仅允许模型基于召回证据回答：

- System Prompt：要求“仅基于给定证据作答；无法确认则明确说不知道”。
- User Prompt：包含问题、证据列表、引用编号。
- 上下文截断：按 `ASK_MAX_CONTEXT_CHARS` 做长度裁剪，超长时优先保留高分证据。

输出要求：

- 生成答案不直接暴露 ACL 过滤后的隐式信息。
- 若证据冲突，优先提示“依据存在冲突”，不强行汇总为确定性结论。

### 4.3 rerank 降级策略

`rerank` 必须是“增强项而不是硬依赖”，因此实现上遵循：

- 未启用或未配置：直接跳过。
- 调用异常：记录 warning，继续使用召回原顺序。
- 响应为空：视同异常降级。
- 仅影响最终证据排序，不改变 ACL 和过滤逻辑。

### 4.4 任务取消执行逻辑

#### 4.4.1 状态流转

```text
PENDING --cancel--> CANCELLED
RUNNING --cancel--> CANCELLING --checkpoint--> CANCELLED
SUCCEEDED/FAILED --cancel--> 409 Conflict
CANCELLING/CANCELLED --cancel--> idempotent 200
```

#### 4.4.2 检查点设计

在 `IndexingService.run_job()` 中至少增加以下取消检查点：

1. 拉取原始数据前。
2. 每条 `raw_record` 开始处理前。
3. 文档切块与 embedding 前。
4. 更新 checkpoint 前。
5. `mark_succeeded()` 前。

命中取消后执行以下动作：

- 停止继续处理后续记录。
- 不推进 checkpoint。
- 不更新 `source.last_sync_at`。
- 将任务终态写为 `CANCELLED`。

#### 4.4.3 幂等性策略

- 对 `PENDING` 任务：直接写为 `CANCELLED`。
- 对 `RUNNING` 任务：首次写为 `CANCELLING` 并记录取消人/原因；后续重复调用直接返回当前任务。
- 对 `CANCELLING/CANCELLED`：返回当前任务，保持幂等。

### 4.5 pipeline_engine 解析逻辑

建议新增 `PipelineEngineResolver`，遵循以下规则：

1. 若配置 `PIPELINE_ENGINE_TYPE=external` 且对应外部能力已启用，则返回外部引擎信息。
2. 否则返回内置引擎信息。
3. `sync` 任务优先记录“本次实际执行的 flow 来源”；`ask/search` 返回“本次请求实际使用的问答/检索编排来源”。
4. 若未来出现“检索内置 + 问答外部”的混合场景，优先以当前接口主链路来源为准：
   - `/internal/search`：看检索链路。
   - `/internal/ask`：看问答编排链路。
   - `/internal/jobs/{id}`：看同步链路。

### 4.6 与现有实现的兼容策略

- **请求兼容**：不修改已有接口路径和请求体。
- **响应兼容**：仅追加字段；既有字段语义保持不变。
- **配置兼容**：`SYNC_RUN_INLINE` 继续支持，内部映射到新 runner 配置。
- **能力兼容**：LLM/rerank 默认关闭时，系统行为尽量接近当前版本。

---

## 5. 依赖与风险点

### 5.1 外部依赖

- 继续复用现有 `httpx` 作为 LLM/rerank HTTP 客户端。
- 不强制新增数据库、队列、中间件；后台执行先使用进程内实现。
- 若接入外部 pipeline，仅要求能通过配置识别和暴露，不要求本期完成完整编排迁移。

### 5.2 风险点与缓解

#### 风险 1：`inline` 模式下运行中取消能力有限

- **原因**：当前同步流程可能阻塞请求线程，取消请求不一定及时进入。
- **缓解**：联调/生产推荐 `JOB_RUNNER_MODE=background`；文档明确说明 `inline` 仅适合开发验证。

#### 风险 2：新增状态枚举可能影响上游兼容

- **原因**：若上游对 `status` 做严格枚举判断，`CANCELLING/CANCELLED` 可能需要同步适配。
- **缓解**：文档先明确新增状态；若有强兼容要求，可在接入方完成适配前仅先暴露 `CANCELLED`，`CANCELLING` 作为短暂过渡态。

#### 风险 3：大模型生成引入时延与不确定性

- **原因**：LLM 调用存在超时、限流、波动。
- **缓解**：设置独立超时、重试上限和兜底策略；默认关闭，逐环境灰度开启。

#### 风险 4：rerank 与召回阈值叠加后可能改变结果顺序

- **原因**：启用 rerank 后，引用顺序与答案内容都可能变化。
- **缓解**：增加 `rerank_applied` 标志；测试覆盖启用/关闭/异常降级三种场景。

#### 风险 5：取消中途可能留下部分已写入结果

- **原因**：当前索引处理按记录逐步写入，没有事务性批处理。
- **缓解**：取消后不推进 checkpoint 和 `last_sync_at`，允许后续重跑修正；本期不承诺“回滚已写入分块”。

---

## 6. 工作量估算

### 6.1 总体估算

在当前代码规模下，预计 **4.5 ～ 6 人日**，适合两名 agent 并行推进。

### 6.2 双 Agent 分工建议

#### Agent A：问答链路增强（约 2.5 ～ 3 人日）

负责范围：

- `qa_service` 编排改造
- `AnswerGenerator` 抽象与 HTTP LLM provider
- `RerankService` 抽象与降级逻辑
- `Ask/Search` schema 扩展
- 问答相关单测与文档

交付结果：

- `/internal/ask` 完成“召回 → 可选 rerank → 生成/兜底”闭环
- `/internal/search` 与 `/internal/ask` 正确返回 `pipeline_engine` / `rerank_applied`

#### Agent B：任务与执行链路治理（约 2 ～ 2.5 人日）

负责范围：

- `JobStatus` / `IndexJob` 扩展
- 取消任务 API
- `JobRunner` 与取消检查点
- `PipelineEngineResolver`
- `health/jobs` 接口与文档更新

交付结果：

- `/internal/jobs/{id}/cancel` 可用
- `jobs/health` 返回真实 `pipeline_engine`
- `RUNNING` 任务在后台模式下可取消

### 6.3 依赖关系

- 可并行：Agent A 与 Agent B 的主体改动可并行推进。
- 串行收口：
  - `PipelineEngineInfo` 数据结构需先统一。
  - 文档与测试用例需要最后合并一次。

### 6.4 完成定义（技术方案阶段）

本 `spec.md` 作为后续“任务拆分”和编码实现的输入基线，后续拆任务时应严格围绕以下完成标准展开：

- 接口改动范围已明确。
- 数据模型扩展已明确。
- 降级与兼容策略已明确。
- 双 Agent 并行边界已明确。


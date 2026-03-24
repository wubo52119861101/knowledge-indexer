# 任务拆分

## 1. 拆分原则

- 以 `spec.md` 中“双 Agent 分工建议”为主线，先完成共享基线，再并行推进问答链路与任务治理。
- 子任务按“先打基础、后并行开发、最后收口”的顺序排序，尽量减少跨模块反复冲突。
- 所有子任务均要求保持现有接口路径与请求结构兼容，仅做响应字段追加和新接口补充。

## 2. 子任务清单

| 编号 | 名称 | 负责模块 | 建议负责人 | 预估工作量 | 依赖关系 | 优先级 |
| --- | --- | --- | --- | --- | --- | --- |
| T1 | 共享基础能力与配置扩展 | `app/core/config.py`、`app/core/container.py`、`app/models/common.py`、`app/models/job.py`、`app/schemas/job.py`、`app/schemas/retrieval.py` | Agent B 主负责，Agent A 对齐接口 | 0.5 ~ 1 人日 | 无 | P0 |
| T2 | 问答链路编排与生成能力 | `app/services/qa_service.py`、`app/services/answer_generator.py`、`app/services/rerank_service.py`、`app/api/internal_ask.py`、`app/api/internal_search.py` | Agent A | 1.5 ~ 2 人日 | T1 | P0 |
| T3 | 任务取消接口与执行器治理 | `app/api/jobs.py`、`app/services/job_service.py`、`app/services/indexing_service.py`、`app/services/job_runner.py`、`app/core/container.py` | Agent B | 1.5 ~ 2 人日 | T1 | P0 |
| T4 | `pipeline_engine` 统一解析与接口出参补齐 | `app/services/pipeline_engine_service.py`、`app/api/health.py`、`app/api/internal_ask.py`、`app/api/internal_search.py`、`app/api/jobs.py`、`app/models/job.py` | Agent B 主负责，Agent A 配合问答出参 | 0.5 ~ 1 人日 | T1，建议与 T2/T3 并行收口 | P0 |
| T5 | 文档与实现侧单测补齐 | `tests/test_qa_service.py`、`tests/test_retrieval_service.py`、新增任务相关测试文件、`docs/usage.md`、`README.md` | Agent A / Agent B 各自补齐，最后合并 | 0.5 ~ 1 人日 | T2、T3、T4 | P1 |

## 3. 子任务说明与完成标准

### T1 共享基础能力与配置扩展

**关键实现要点**

- 在 `Settings` 中补齐 LLM、rerank、pipeline engine、job runner 相关配置，并兼容现有 `SYNC_RUN_INLINE`。
- 新增统一的 `PipelineEngineInfo` 结构，扩展 `JobStatus` 为 `PENDING/RUNNING/CANCELLING/CANCELLED/SUCCEEDED/FAILED`。
- 为 `IndexJob`、`JobItem`、`AskResponseData`、`SearchResponseData` 补齐共享字段，避免后续任务重复改 schema。
- 在 `ServiceContainer` 中预留 `answer_generator`、`rerank_service`、`pipeline_engine_service`、`job_runner` 的注入点和默认降级实现。

**完成标准（DoD）**

- 配置项可通过环境变量正常读取，默认行为与当前版本兼容。
- 新旧接口模型能成功实例化，不引入启动时报错。
- 共享数据结构命名和字段定义与 `spec.md` 保持一致。

### T2 问答链路编排与生成能力

**关键实现要点**

- 将 `QaService` 从字符串拼装改为“检索 → 证据判定 → 可选 rerank → LLM 生成 / fallback”的编排逻辑。
- 新增 `AnswerGenerator` 统一封装 LLM HTTP 调用、超时控制和错误降级；未配置时明确走 fallback。
- 新增 `RerankService`，支持启用、关闭、异常降级三种状态，并保证只影响证据排序，不绕过 ACL 与过滤。
- 扩展 `/internal/ask` 和 `/internal/search` 响应，返回 `pipeline_engine`、`rerank_applied`、`answer_mode` 等追加字段。

**完成标准（DoD）**

- `/internal/ask` 在证据充足时可输出生成态或可靠兜底态，而不再直接拼接检索文本作为唯一主路径。
- LLM 未配置、超时、报错时，接口仍稳定返回保守回答和引用。
- `citations` 顺序与最终参与回答的证据顺序一致。

### T3 任务取消接口与执行器治理

**关键实现要点**

- 在 `jobs` API 中新增 `POST /internal/jobs/{job_id}/cancel`，补齐请求体、幂等返回和错误码约定。
- 在 `JobService` 中实现取消请求登记、状态机流转和取消审计字段写入。
- 新增 `JobRunner` 或等价执行器，兼容 `inline/background` 两种模式，支持后台模式下独立发起取消。
- 在 `IndexingService.run_job()` 中增加取消检查点，保证 `RUNNING -> CANCELLING -> CANCELLED` 的软取消闭环。

**完成标准（DoD）**

- `PENDING` 任务可直接取消为 `CANCELLED`，`RUNNING` 任务可在检查点尽快停止。
- 已完成任务取消时返回 `409`，已取消或取消中重复调用保持幂等 `200`。
- 取消后不再推进成功态、checkpoint 或 `last_sync_at`。

### T4 `pipeline_engine` 统一解析与接口出参补齐

**关键实现要点**

- 新增统一解析服务，按 ask/search/sync/health 场景返回真实的 `pipeline_engine` 信息。
- 在任务创建或启动时记录本次同步实际使用的 `pipeline_engine`，避免运行后查询受配置漂移影响。
- 更新 `/health`、`/internal/ask`、`/internal/search`、`/internal/jobs/{id}` 出参，移除固定占位文案。
- 统一 `builtin` / `external` 的命名和 scene 取值，避免上下游理解偏差。

**完成标准（DoD）**

- 四类接口都能返回结构一致的 `pipeline_engine` 字段。
- 未启用外部能力时，接口清晰反映“内置引擎 + 当前场景”，不再使用误导性描述。
- 任务查询拿到的是任务执行时的真实引擎信息，而不是当前瞬时配置。

### T5 文档与实现侧单测补齐

**关键实现要点**

- 为问答链路补齐“证据不足”“LLM 关闭”“LLM 异常降级”“rerank 启用/失败降级”单测。
- 为任务链路补齐“取消成功”“重复取消幂等”“已完成任务不可取消”“后台模式检查点终止”单测。
- 更新 `docs/usage.md` / `README.md` 的配置说明、接口响应字段和推荐运行模式。

**完成标准（DoD）**

- 关键路径至少覆盖正常流程和主要异常/降级流程。
- 文档明确说明新增配置项、取消接口、`pipeline_engine` 语义和 `inline/background` 差异。
- 测试与文档内容能够支撑后续 Code Review 与测试验证步骤直接开展。

## 4. 并行与串行执行建议

### 推荐顺序

1. **串行启动 T1**：先统一配置、模型和容器注入点，减少后续反复改公共文件。
2. **并行推进 T2 / T3**：
   - Agent A 负责问答链路增强。
   - Agent B 负责取消接口、执行器和状态机治理。
3. **并行收口 T4**：由 Agent B 主导解析服务，Agent A 配合补齐 ask/search 的接口返回。
4. **最后执行 T5**：双方各自补齐本模块测试与文档，再集中合并。

### 双 Agent 分工建议

- **Agent A**：T2 + T5（问答/检索相关测试与文档）。
- **Agent B**：T1 + T3 + T4 + T5（任务/健康检查相关测试与文档）。
- **协作边界**：
  - T1 完成前，Agent A 不修改共享 schema 定义，只可先完成服务内部草拟。
  - T4 的 `pipeline_engine` 字段结构由 Agent B 定版，Agent A 只消费统一结构。

## 5. 任务优先级排序

1. `T1` 共享基础能力与配置扩展
2. `T2` 问答链路编排与生成能力
3. `T3` 任务取消接口与执行器治理
4. `T4` `pipeline_engine` 统一解析与接口出参补齐
5. `T5` 文档与实现侧单测补齐

## 6. 交付检查清单

- [ ] 共享配置、模型、schema 已统一
- [ ] `/internal/ask` 升级为正式生成链路并保留安全兜底
- [ ] `/internal/jobs/{job_id}/cancel` 可用且状态机正确
- [ ] `/health`、`/internal/ask`、`/internal/search`、`/internal/jobs/{id}` 返回真实 `pipeline_engine`
- [ ] 关键单测与文档已补齐，可进入 Code Review

# knowledge-indexer 二期任务拆分

## 1. 拆分原则
- 以 `requirements.md` 中的五条主线能力为主轴：持久化、异步任务、`postgres` 数据源、检索 / 问答增强、运维联调。
- 优先保证 M1（底座生产化）闭环，再推进 M2（效果增强）与文档收口，避免“接口写完但链路不可用”。
- 子任务尽量映射到现有仓库模块，便于直接分配到对应代码目录与负责人。
- 预估工作量沿用 `spec.md` 中的模块估算，并按可交付粒度重新拆分。

## 2. 子任务清单

| 编号 | 子任务名称 | 负责模块 | 主要内容 | 预估工作量 | 依赖关系 | 优先级 | 执行方式 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T1 | 持久化仓储底座落地 | `app/repositories/*`、`app/models/*`、`app/core/database.py`、`migrations/`、`docker/init.sql` | 将当前内存仓储替换为 PostgreSQL + pgvector 可落地实现，补齐表结构、索引、Repository 抽象与容器装配。 | 3 ~ 4 人天 | 无 | P0 | 串行起步 |
| T2 | 异步同步任务与状态机实现 | `app/services/job_service.py`、`app/api/jobs.py`、`app/flows/*`、`app/core/redis.py`、`app/core/container.py` | 引入 Redis 队列 / worker、任务状态流转、互斥控制、任务追踪与失败摘要，打通“触发同步 -> 后台执行 -> 查询任务”。 | 2 ~ 3 人天 | T1 | P0 | 可并行 |
| T3 | `postgres` 数据源接入生产化 | `app/connectors/postgres_connector.py`、`app/schemas/source.py`、`app/services/source_service.py`、`app/flows/postgres_index_flow.py` | 完善连接配置校验、批量拉取、增量游标、删除标记处理、normalize 映射，形成可用数据库源。 | 2 ~ 3 人天 | T1 | P0 | 可并行 |
| T4 | 检索与问答链路增强 | `app/services/retrieval_service.py`、`app/services/qa_service.py`、`app/services/embedding_service.py`、`app/schemas/retrieval.py` | 接入真实 embedding provider，改造 PostgreSQL + pgvector 检索链路，优化过滤顺序并保留 rerank 扩展点。 | 2 ~ 3 人天 | T1，建议依赖 T3 输出的数据样例联调 | P1 | 可并行 |
| T5 | MinIO 归档与可观测增强 | `app/core/minio.py`、`app/api/health.py`、`app/core/logger.py`、`app/services/indexing_service.py` | 增加原文 / 失败样本归档、健康检查能力状态、结构化日志和关键指标埋点。 | 1.5 ~ 2 人天 | T2，部分依赖 T3 | P1 | 可并行 |
| T6 | 联调文档与迁移说明补齐 | `docs/usage.md`、`README.md`、`scripts/*` | 补齐配置说明、迁移步骤、接入示例、同步模式说明与 Java 联调手册。 | 1 ~ 1.5 人天 | T2、T3、T4、T5 基本稳定后 | P2 | 串行收口 |
| T7 | 测试与回归验证 | `tests/*` | 覆盖 Repository、同步任务、`postgres` connector、检索 / 问答、健康检查等关键路径，输出测试报告。 | 2 ~ 3 人天 | T1 ~ T5 完成后集中执行；也可随开发滚动补齐 | P0 | 串行验收 |

## 3. 优先级排序
1. **T1 持久化仓储底座落地**：决定后续任务的数据模型和运行边界，是所有能力的共同前置。
2. **T2 异步同步任务与状态机实现**：决定同步链路是否具备生产可追踪性。
3. **T3 `postgres` 数据源接入生产化**：二期明确要求的核心生产级数据源。
4. **T7 测试与回归验证**：虽然验收发生在后段，但需从开发开始同步设计测试点，优先级按交付门槛计为 P0。
5. **T4 检索与问答链路增强**：在底座稳定后提升效果与可用性。
6. **T5 MinIO 归档与可观测增强**：支撑运维、联调与问题排查。
7. **T6 联调文档与迁移说明补齐**：在接口和实现稳定后统一收口。

## 4. 并行 vs 串行执行建议

### 4.1 推荐执行波次
- **Wave 1（串行）**：先完成 T1，冻结核心表结构、Repository 接口和容器装配方式。
- **Wave 2（双线并行）**：T2 与 T3 并行推进。
  - 负责人 A：聚焦任务队列、worker、任务状态机。
  - 负责人 B：聚焦 `postgres` connector、增量同步、字段映射。
- **Wave 3（双线并行）**：T4 与 T5 并行推进。
  - T4 基于 T1 的持久化检索能力改造检索 / 问答。
  - T5 基于 T2 / T3 的同步结果补齐归档、健康检查、日志指标。
- **Wave 4（串行收口）**：T6 与 T7，先补文档，再完成回归与验收报告。

### 4.2 并行约束
- T1 未完成前，不建议开始任何需要改动 Repository 或数据库表结构的实现工作。
- T2 与 T3 可并行，但要约定统一的 `job` / `checkpoint` / `document` 状态字段，避免联调返工。
- T4 可在 T1 完成后先行开发接口和查询层，但最终效果验证需使用 T3 产出的真实数据样本。
- T5 中的 MinIO 归档可先基于任务框架预埋接口，待 T2 的任务上下文稳定后再补落盘细节。
- T7 建议采用“随开发补单测 + 末尾做集成回归”的模式，而不是全部压到最后。

## 5. 每个子任务的完成标准（DoD）

### T1 持久化仓储底座落地
- PostgreSQL / pgvector 表结构、索引和初始化脚本齐备，字段与 `spec.md` 保持一致。
- `SourceRepository`、`JobRepository`、`CheckpointRepository`、`DocumentRepository`、`ChunkRepository` 至少具备生产实现与接口切换能力。
- `app/core/container.py` 不再默认绑死纯内存实现，支持按配置切换真实仓储。
- 基础 CRUD 与 upsert 行为有对应单元测试或仓储测试覆盖。

### T2 异步同步任务与状态机实现
- 触发同步接口能够创建任务并异步执行，不再仅依赖 inline 执行完成闭环。
- 任务状态覆盖 `PENDING` / `RUNNING` / `SUCCEEDED` / `FAILED` / `CANCELLED`，并有明确状态流转规则。
- 支持查询任务进度、处理数量、失败摘要、失败阶段等核心字段。
- 至少对重复触发、任务失败、worker 异常退出三类场景有处理说明或测试覆盖。

### T3 `postgres` 数据源接入生产化
- 数据源创建 / 更新时可完成连接信息校验、字段映射校验和敏感配置脱敏。
- 支持全量与增量同步，增量游标可通过 checkpoint 持续推进。
- 支持删除标记、ACL 字段、metadata 字段映射到统一文档结构。
- 至少有一份真实或模拟的 `postgres` 数据源联调样例可用于回归。

### T4 检索与问答链路增强
- 检索链路从内存遍历切换到 PostgreSQL + pgvector 查询。
- embedding 服务可替换为真实 provider，保留开发 / 演示模式兜底。
- 检索过滤顺序、ACL 判定、问答证据不足兜底逻辑与技术方案一致。
- 检索 / 问答关键路径有单测或集成测试，且返回结构保持兼容。

### T5 MinIO 归档与可观测增强
- 同步任务支持原文快照和失败样本归档，路径约定与技术方案一致。
- `/health` 能输出数据库、Redis、MinIO、embedding、pipeline engine 的状态分层信息。
- 同步任务日志具备 `job_id`、`source_id`、`mode`、`status`、`duration_ms` 等结构化字段。
- 至少具备关键指标采集方案或日志替代方案，支持定位失败阶段与耗时问题。

### T6 联调文档与迁移说明补齐
- `docs/usage.md` 与 `README.md` 能覆盖二期新增配置、接口变化、运行方式和排障指引。
- 至少提供一份 Java 调用方可直接参考的接入 / 联调示例。
- 明确一期迁移到二期时的环境依赖、数据初始化、回滚注意事项。
- 文档内容与实际代码实现一致，不把未落地能力写成既成事实。

### T7 测试与回归验证
- 输出覆盖主流程与异常场景的测试清单，并形成测试报告。
- 单测覆盖 Repository、同步任务、connector、检索 / 问答等核心模块。
- 至少完成一次端到端验证：创建数据源 -> 触发同步 -> 查询任务 -> 检索 / 问答。
- 未覆盖风险点有显式记录，并附后续补齐建议。

## 6. 建议的人员分工
- **后端负责人 A**：T1 + T2，负责底座与任务编排。
- **后端负责人 B**：T3 + T4，负责数据接入与检索效果。
- **公共支持 / 联调**：T5 + T6 + T7，可由两位负责人在各自模块稳定后共同收口。

## 7. 拆分结论
- 若按双人并行推进，建议以 **T1 -> (T2 || T3) -> (T4 || T5) -> (T6 + T7)** 的顺序执行。
- 在该拆分下，首批可交付目标聚焦于 M1 + M2 的核心闭环：**可持久化、可异步同步、可接入 `postgres`、可检索问答、可观测可联调**。
- M3（如 CocoIndex 灰度、rerank 正式接入、任务取消接口）建议作为后续增量任务，不纳入当前首批交付的必达范围。

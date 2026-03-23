# knowledge-indexer 二期技术方案

## 1. 方案概述

### 1.1 目标
- 在保持一期内部 API 语义基本稳定的前提下，将 `knowledge-indexer` 从“内存原型链路”升级为“可持久化、可异步执行、可持续扩展”的内部知识处理底座。
- 二期重点落地五条主线：持久化存储、异步同步任务、`postgres` 数据源正式可用、检索 / 问答能力增强、运维与联调规范补齐。
- 方案设计需兼容当前代码结构，优先复用 `app/api`、`app/services`、`app/connectors`、`app/flows` 既有边界，避免推翻一期骨架。

### 1.2 设计原则
- **兼容优先**：继续保留 `/internal/sources`、`/internal/jobs/{id}`、`/internal/search`、`/internal/ask` 的整体合同，新增能力优先通过补字段、补配置、补后端实现完成。
- **存储与计算解耦**：仓储、向量索引、对象存储、任务队列分别抽象，避免单个基础设施与业务逻辑硬耦合。
- **同步流程可观测**：每次同步必须可追踪到来源、模式、处理数量、失败摘要、checkpoint、归档位置和耗时。
- **渐进替换**：保留当前内置 `IndexingService` 链路作为降级方案；CocoIndex、真实 embedding、rerank 通过可替换接口接入。
- **安全内聚**：继续使用内部接口 + Token 鉴权模型，ACL 过滤保持在检索服务内统一收口，敏感配置不进入业务日志。

### 1.3 基于仓库现状的关键判断
- 当前仓库已具备源管理、同步任务对象、文本清洗切块、哈希向量检索、ACL 过滤和证据不足兜底问答能力，二期应以“替换占位实现 + 补全生产能力”为主，而非重新定义产品。
- `postgres` 数据源、PostgreSQL 持久化、Redis 队列、MinIO 归档、CocoIndex 正式流程目前在仓库中均为预留点或配置占位，因此本方案将它们定义为二期明确交付目标，而不是既有事实。
- 考虑接入稳定性，二期首批建议继续沿用当前 API 入口，不额外新增面向终端用户的公开接口；所有能力仍作为 Java 后端可调用的内部服务提供。

## 2. 整体架构设计

### 2.1 目标架构

```text
Java Backend / Internal Caller
        |
        v
FastAPI Internal APIs
  - source management
  - sync trigger / job query
  - search / ask
        |
        v
Application Services
  - SourceService
  - SyncOrchestrator
  - RetrievalService
  - QaService
        |
        +-------------------------------+
        |                               |
        v                               v
Queue / Worker Layer               Retrieval Layer
  - Redis enqueue                    - pgvector ANN / SQL filter
  - worker consume                   - ACL filter
  - retry / timeout                  - optional rerank
        |
        v
Index Pipeline Engine
  - builtin pipeline (default)
  - cocoindex pipeline (feature flag)
        |
        v
Persistence Layer
  - PostgreSQL + pgvector
  - MinIO raw snapshot / failed sample
  - Redis job queue / lock / retry metadata
```

### 2.2 与一期代码结构的映射关系
- `app/api/`：保留现有路由分层，主要补充返回字段与异常语义，不重构入口。
- `app/core/container.py`：从“直接实例化内存实现”调整为“按配置装配 repository / queue / object storage / embedding provider / pipeline engine”。
- `app/repositories/`：抽象 Repository 接口；保留 InMemory 实现用于本地开发，新增 PostgreSQL 实现用于二期默认运行。
- `app/services/`：`SourceService`、`JobService`、`RetrievalService`、`QaService` 继续保留；新增 `SyncOrchestrator` 负责触发、排队、幂等、状态流转。
- `app/connectors/`：保留 `file`、`api`、`postgres` 三类 connector；其中 `PostgresConnector` 从占位变为正式实现。
- `app/flows/`：保留按源类型选择 flow 的模式；新增 pipeline engine 选择逻辑，默认 `builtin`，预留 `cocoindex`。

### 2.3 关键运行模式
- **本地开发模式**：允许继续使用 InMemory Repository + Inline Sync，便于联调和单测。
- **二期默认模式**：使用 PostgreSQL + pgvector + Redis + MinIO；同步任务异步执行。
- **降级模式**：当 CocoIndex、rerank 服务未启用时，回退到内置切块 + embedding + 向量检索，不影响主链路可用性。

## 3. 模块设计

### 3.1 数据源管理模块

#### 3.1.1 职责
- 维护数据源基础信息、启停状态、同步模式、配置摘要。
- 在创建 / 更新时完成类型相关校验和配置脱敏。
- 为同步任务提供 connector 选择依据。

#### 3.1.2 建议配置结构

**file source**

```json
{
  "root_path": "./sample_docs",
  "file_patterns": ["**/*.md", "**/*.txt"],
  "encoding": "utf-8",
  "max_file_size_mb": 20
}
```

**api source**

```json
{
  "base_url": "http://example.internal/knowledge",
  "method": "GET",
  "headers": {
    "Authorization": "***"
  },
  "params": {
    "scene": "faq"
  },
  "pagination": {
    "type": "page",
    "page_param": "page",
    "size_param": "page_size",
    "start": 1,
    "size": 100
  },
  "timeout_seconds": 10,
  "rate_limit_qps": 5
}
```

**postgres source**

```json
{
  "connection_dsn": "postgresql://user:***@host:5432/db",
  "schema": "public",
  "table": "knowledge_articles",
  "primary_key": "id",
  "title_column": "title",
  "content_column": "content",
  "doc_type_column": "doc_type",
  "updated_at_column": "updated_at",
  "deleted_flag_column": "is_deleted",
  "acl_columns": {
    "roles": "visible_roles",
    "departments": "visible_departments"
  },
  "where_clause": "status = 'ONLINE'"
}
```

#### 3.1.3 校验要求
- `file`：`root_path` 必填；路径必须存在；`file_patterns` 为空时回退默认值；超大文件直接跳过并记失败原因。
- `api`：`base_url` 必填；支持 `GET` / `POST` 两种拉取方式；鉴权头与 query 参数需脱敏存储展示。
- `postgres`：必须提供连接串、表名、主键列、正文列、增量列；启动前做连接性与列存在性校验。

### 3.2 同步任务模块

#### 3.2.1 目标
- 将当前 `trigger_sync -> inline run` 模式升级为“创建任务 -> 入队 -> worker 执行 -> 持久化状态”的异步流程。
- 一个 source 在同一时刻仅允许一个运行中任务，避免重复构建和 checkpoint 冲突。

#### 3.2.2 状态机设计

```text
PENDING -> RUNNING -> SUCCEEDED
                 └-> FAILED
PENDING/RUNNING -> CANCELLED   (二期预留终态)
```

- `PENDING`：已创建并进入队列，等价于“排队中”。
- `RUNNING`：worker 已取到任务并开始拉取 / 清洗 / 切块 / 入库。
- `SUCCEEDED`：任务主流程完成，checkpoint 已提交。
- `FAILED`：任务失败；至少记录失败摘要、失败数、失败阶段。
- `CANCELLED`：状态预留；如二期首批不开放取消接口，也需在 schema 与 worker 终态判断中预留。

#### 3.2.3 任务模式语义
- `incremental`：按 source checkpoint 拉取新增 / 变更数据；默认模式。
- `full`：拉取完整快照并对缺失文档做软删除；不强制清空历史源记录。
- `rebuild`：按 source 维度重建索引；可清空旧 chunk / vector / checkpoint 后重跑。

#### 3.2.4 同步编排流程
1. API 层校验 source 存在且已启用。
2. `SyncOrchestrator` 创建 job，写入 PostgreSQL。
3. job 入 Redis 队列，并以 `source_id` 做互斥锁。
4. worker 拉起执行，状态更新为 `RUNNING`。
5. 根据 source type 选择 connector + flow。
6. 拉取原始记录，并按批次写入临时处理上下文。
7. 对每条记录做 normalize、清洗、切块、embedding、文档 / chunk upsert。
8. 全量 / 重建任务结束后，对未命中文档做软删除。
9. 成功后提交 checkpoint、写归档路径、更新统计信息。
10. 失败时记录失败摘要、失败样本、阶段信息，并释放锁。

### 3.3 索引与存储模块

#### 3.3.1 存储抽象
- `SourceRepository`
- `JobRepository`
- `CheckpointRepository`
- `DocumentRepository`
- `ChunkRepository`
- `ObjectStorageRepository`（新增，用于 MinIO 归档）

#### 3.3.2 PostgreSQL / pgvector 数据结构建议

**kb_sources**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | varchar(32) | `src_xxx` |
| `name` | varchar(128) | 数据源名称 |
| `type` | varchar(32) | `file` / `api` / `postgres` |
| `config_json` | jsonb | 原始配置，敏感字段加密或脱敏 |
| `config_masked_json` | jsonb | 返回给接口的脱敏配置 |
| `sync_mode` | varchar(32) | 默认同步模式 |
| `enabled` | boolean | 是否启用 |
| `last_sync_at` | timestamptz | 最近成功同步时间 |
| `created_at` / `updated_at` | timestamptz | 审计字段 |

**kb_sync_jobs**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | varchar(32) | `job_xxx` |
| `source_id` | varchar(32) | 关联 source |
| `mode` | varchar(32) | `full` / `incremental` / `rebuild` |
| `status` | varchar(32) | `PENDING` / `RUNNING` / `SUCCEEDED` / `FAILED` / `CANCELLED` |
| `triggered_by` | varchar(64) | 操作人 |
| `processed_count` | integer | 成功处理文档数 |
| `failed_count` | integer | 失败文档数 |
| `error_summary` | text | 摘要错误 |
| `failure_stage` | varchar(64) | `pull` / `normalize` / `embed` / `persist` |
| `snapshot_path` | varchar(255) | MinIO 原文 / 失败样本位置 |
| `checkpoint_before` | varchar(255) | 任务开始前 checkpoint |
| `checkpoint_after` | varchar(255) | 任务完成后 checkpoint |
| `started_at` / `finished_at` / `created_at` | timestamptz | 时间字段 |

**kb_sync_checkpoints**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | varchar(32) | `ckp_xxx` |
| `source_id` | varchar(32) | 关联 source |
| `checkpoint_key` | varchar(64) | 当前固定 `default`，后续可扩展子流 |
| `checkpoint_value` | varchar(255) | 增量游标 |
| `updated_at` | timestamptz | 更新时间 |

**kb_documents**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | varchar(32) | `doc_xxx` |
| `source_id` | varchar(32) | 来源数据源 |
| `external_doc_id` | varchar(255) | 外部主键；与 `source_id` 唯一 |
| `title` | varchar(255) | 标题 |
| `content_text` | text | 清洗后的正文 |
| `content_hash` | varchar(64) | 内容哈希 |
| `doc_type` | varchar(64) | 文档类型 |
| `metadata_json` | jsonb | 业务元数据 |
| `acl_json` | jsonb | ACL 列表 |
| `status` | varchar(32) | `ACTIVE` / `DELETED` / `FAILED` |
| `version` | integer | 版本号 |
| `created_at` / `updated_at` | timestamptz | 时间字段 |

**kb_chunks**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | varchar(32) | `chk_xxx` |
| `document_id` | varchar(32) | 关联 document |
| `chunk_index` | integer | 切片序号 |
| `content` | text | 切片正文 |
| `summary` | text | 摘要 |
| `token_count` | integer | 估算 token 数 |
| `metadata_json` | jsonb | 检索过滤字段 |
| `embedding` | vector | pgvector 向量 |
| `embedding_status` | varchar(32) | `PENDING` / `DONE` / `FAILED` |
| `created_at` / `updated_at` | timestamptz | 时间字段 |

#### 3.3.3 索引建议
- `kb_documents(source_id, external_doc_id)` 唯一索引。
- `kb_documents(source_id, status)` 普通索引。
- `kb_chunks(document_id, chunk_index)` 唯一索引。
- `kb_chunks using ivfflat (embedding vector_cosine_ops)` 向量索引。
- `kb_sync_jobs(source_id, created_at desc)` 索引，用于查最新任务。
- `kb_sync_checkpoints(source_id, checkpoint_key)` 唯一索引。

#### 3.3.4 MinIO 归档策略
- 原文快照路径：`raw/{source_id}/{job_id}/records.jsonl.gz`
- 失败样本路径：`failed/{source_id}/{job_id}/records.jsonl.gz`
- 可选存储切块前清洗内容，用于定位 connector / normalize 问题。
- 归档对象默认保留 7~30 天，超过期限可由生命周期策略自动清理。

### 3.4 检索与问答模块

#### 3.4.1 检索链路
- 保留现有 `RetrievalService.search(query, top_k, filters, acl_context)` 入口。
- 二期改造重点：
  - 向量从 `HashEmbeddingService` 迁移到真实 embedding provider。
  - 数据读取从内存遍历迁移为 PostgreSQL + pgvector 检索。
  - 过滤顺序调整为“source/doc_type/metadata 粗过滤 -> 向量召回 -> ACL 过滤 -> rerank（可选） -> top_k”。
- `SearchFilters` 保持现有结构，允许后续新增时间范围、标签、业务线等 metadata 过滤字段。

#### 3.4.2 ACL 策略
- 保持一期 deny 优先、allow 次之、无 ACL 默认开放的判断逻辑。
- ACL 仍以 document 维度存储和过滤，避免 chunk 级 ACL 扩散复杂度。
- 若后续业务需要 chunk 级敏感信息裁剪，可在切块阶段继承 document ACL，并通过 metadata 标识细粒度范围。

#### 3.4.3 问答策略
- 问答继续采用“检索优先、证据驱动”的模式，不在二期内直接引入面向终端用户的自主生成问答接口。
- `QaService.ask` 返回字段继续包含：`answer`、`citations`、`evidence_status`、`reason`。
- 若接入真实 LLM，建议采用两段式：
  1. 先检索得到证据；
  2. 仅在 `evidence_status=SUFFICIENT` 时调用 LLM 对证据进行答案拼装。
- 证据不足时沿用当前兜底话术，不强制生成高风险答案。

### 3.5 运维与可观测模块

#### 3.5.1 健康检查
- `/health` 保留，但状态需从“配置级”增强为“配置 + 连通性 + 能力状态”三层信息。
- 建议输出：
  - `database`: `disabled` / `configured` / `reachable`
  - `redis`: `disabled` / `configured` / `reachable`
  - `minio`: `disabled` / `configured` / `reachable`
  - `embedding`: `development` / `configured` / `reachable`
  - `pipeline_engine`: `builtin` / `cocoindex`

#### 3.5.2 日志与指标
- 每次请求附带 `request_id`，沿用当前中间件。
- 每次同步任务输出结构化日志字段：`job_id`、`source_id`、`mode`、`status`、`processed_count`、`failed_count`、`duration_ms`。
- 关键指标：任务成功率、平均耗时、失败阶段分布、单 source 最新 checkpoint 延迟、检索 QPS、平均 top_k 命中率。

## 4. 接口设计

### 4.1 保持兼容的现有接口

#### 4.1.1 创建数据源
- `POST /internal/sources`
- 请求结构保持当前 `CreateSourceRequest`，其中 `config` 按 source type 做细化校验。
- 响应继续返回 `SourceItem`，但 `config` 应改为脱敏后结构。

#### 4.1.2 查询数据源详情
- `GET /internal/sources/{source_id}`
- 返回 `source + latest_job` 结构保持不变。
- 建议补充 `latest_job.status_detail`、`latest_job.finished_at` 等更完整执行语义。

#### 4.1.3 触发同步
- `POST /internal/sources/{source_id}/sync`
- 请求保持：

```json
{
  "mode": "incremental",
  "operator": "system",
  "options": {
    "force_rebuild": false
  }
}
```

- 二期默认语义改为“异步入队”；成功返回：

```json
{
  "job_id": "job_xxx",
  "status": "PENDING",
  "queued_at": "2026-03-23T00:00:00Z"
}
```

- 当同一 source 已有运行中任务时，返回 `409 Conflict`。

#### 4.1.4 查询任务
- `GET /internal/jobs/{job_id}`
- 保持当前 `JobItem` 主结构，新增字段建议：`failure_stage`、`checkpoint_before`、`checkpoint_after`、`queue_latency_ms`。

#### 4.1.5 检索与问答
- `POST /internal/search`
- `POST /internal/ask`
- 请求结构可保持现状，二期主要更换后端检索实现。

### 4.2 建议新增但非必需接口
- `POST /internal/sources/{source_id}/test-connection`：提前校验连接与配置，降低同步失败成本。
- `GET /internal/sources/{source_id}/jobs`：查看某数据源近期任务列表。
- `POST /internal/jobs/{job_id}/cancel`：如二期首批资源允许则实现；否则保留在下一阶段。

## 5. 核心逻辑说明

### 5.1 Repository 装配逻辑
- 在 `app/core/container.py` 中引入配置开关，例如：
  - `REPOSITORY_BACKEND=inmemory|postgres`
  - `SYNC_EXECUTION_MODE=inline|queue`
  - `INDEX_PIPELINE_ENGINE=builtin|cocoindex`
- `local` 环境默认 `inmemory + inline + builtin`。
- `test` 环境可按测试目标切换。
- `prod` / `staging` 环境默认 `postgres + queue + builtin`，待 CocoIndex 稳定后切换。

### 5.2 同步执行逻辑
- **触发阶段**：创建 job 并立即返回；不在 API 请求生命周期内执行拉取和入库。
- **执行阶段**：worker 根据 source type 调用不同 connector；统一经过 `IndexingService` 或 `PipelineEngine`。
- **提交阶段**：只有文档 / chunk upsert 成功后才推进 checkpoint，避免增量丢数。
- **失败阶段**：失败摘要最多保留首批错误样本；原始失败记录进入 MinIO，避免数据库中堆积大文本。

### 5.3 `postgres` 数据源同步逻辑
- `pull_full`：执行完整查询，按批次分页拉取。
- `pull_incremental`：基于 `updated_at_column > checkpoint_value` 拉取变更记录；如果配置了删除标志列，则保留删除状态同步。
- `normalize`：将数据库行转换为统一 `DocumentPayload`，字段缺失时直接报配置错误而非静默跳过。
- 若 `updated_at_column` 不可用，则拒绝启用 `incremental`，要求使用 `full` / `rebuild`。

### 5.4 文档 upsert 逻辑
- `source_id + external_doc_id` 作为自然唯一键。
- 同一文档内容哈希未变化时，可跳过重新 embedding，仅更新时间与 metadata。
- 内容变化时重新切块并替换对应 chunk 集合。
- `full` / `rebuild` 完成后，对本次未出现的外部文档标记 `DELETED`，同时清空对应 chunk。

### 5.5 检索与排序逻辑
- 第一阶段：pgvector 相似度召回 `top_n`。
- 第二阶段：按 `source_ids`、`doc_types`、`metadata` 做过滤。
- 第三阶段：ACL deny / allow 规则过滤。
- 第四阶段：若配置 rerank，则以交叉编码器或外部排序服务对前 `N` 个候选重排。
- 第五阶段：输出最终 `top_k`，并保留 citation 信息。

## 6. 依赖与风险点

### 6.1 依赖清单
- **PostgreSQL + pgvector**：承载 source、job、checkpoint、document、chunk、vector。
- **Redis**：承载异步队列、任务锁、重试计数。
- **MinIO**：承载原文快照、失败样本、调试归档。
- **Embedding Provider**：真实向量生成服务，可为内部模型网关或第三方模型代理。
- **可选 Rerank Provider**：提升检索排序质量。
- **CocoIndex**：作为后续正式 pipeline engine，可通过 feature flag 接入。

### 6.2 风险与应对
- **真实 embedding 接入延迟高**：通过批量 embedding、缓存和超时熔断控制影响面。
- **Postgres 数据源 SQL 配置不规范**：采用白名单字段映射，限制动态 SQL 拼接，仅允许表名 / 列名配置化。
- **大批量同步占用数据库资源**：使用批次拉取、分批提交、异步 worker 并发限制。
- **checkpoint 推进错误导致漏数**：仅在批次成功提交后推进 checkpoint，并保留任务级 before / after 对比。
- **对象归档成本增长**：启用生命周期策略和压缩存储。
- **CocoIndex 与内置链路行为不一致**：在 feature flag 灰度期保留双写 / 对账验证能力。

## 7. 工作量估算

### 7.1 按模块估算

| 模块 | 主要内容 | 预估人天 |
| --- | --- | --- |
| 持久化仓储 | Repository 抽象、PostgreSQL 表结构、pgvector 检索实现 | 3 ~ 4 |
| 异步任务 | Redis 队列、worker、互斥锁、任务状态流转 | 2 ~ 3 |
| `postgres` 数据源 | 连接校验、批量拉取、增量同步、normalize | 2 ~ 3 |
| 检索 / 问答增强 | 真实 embedding 接入、过滤优化、rerank 预留 | 2 ~ 3 |
| MinIO 归档与可观测 | 原文归档、失败样本、健康检查、日志指标 | 1.5 ~ 2 |
| 联调与文档 | 配置说明、迁移说明、接入示例 | 1 ~ 1.5 |
| 测试与回归 | 单测、集成测试、联调验证 | 2 ~ 3 |

### 7.2 总体估算
- 单人串行开发：约 `13.5 ~ 18.5` 人天。
- 双人并行开发：约 `8 ~ 11` 个工作日可完成首批交付。
- 若 CocoIndex 与 rerank 需要在本期一起正式落地，建议额外预留 `3 ~ 5` 人天缓冲。

## 8. 分阶段落地建议

### 8.1 M1：底座生产化
- PostgreSQL + pgvector 落地。
- Redis 队列与 worker 落地。
- `postgres` 数据源可用。
- `/health`、日志、任务追踪增强。

### 8.2 M2：效果增强
- 真实 embedding 接入。
- 检索过滤与召回优化。
- MinIO 原文 / 失败样本归档。
- Java 联调文档补齐。

### 8.3 M3：能力预埋 / 灰度
- CocoIndex 灰度接入。
- rerank 服务接入。
- 任务取消接口和更完整调度策略。

## 9. 技术方案结论
- 二期技术方案的核心不是推翻一期，而是把一期已经存在的模块边界替换成生产可用实现：仓储从内存切到 PostgreSQL + pgvector，任务从同步调用切到 Redis 异步执行，数据接入从 `file/api` 扩展到正式 `postgres`，检索从哈希演示升级为真实向量召回。
- 对外接口保持稳定、内部模块增强可替换性，是降低 Java 接入改造成本与后续演进成本的关键。
- 后续任务拆分阶段可直接围绕“持久化、异步任务、`postgres` 数据源、检索问答增强、运维联调”五条主线拆解执行。

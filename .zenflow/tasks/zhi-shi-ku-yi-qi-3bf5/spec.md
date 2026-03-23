# knowledge-indexer 技术方案

## 1. 方案概述

### 1.1 目标定位
- 项目名称：`knowledge-indexer`
- 项目类型：独立 Python 后端服务
- 项目职责：负责知识数据接入、清洗切分、embedding 生成、增量同步、索引写入、内部检索与问答接口
- 非目标：不负责前端页面、不承担对外开放 API、不替代现有 Java 主后端的鉴权与业务聚合职责

### 1.2 设计原则
- **职责解耦**：保留 Java 后端作为统一业务入口，`knowledge-indexer` 聚焦知识处理和检索能力
- **增量优先**：优先支持可追踪、可断点恢复的同步链路，而不是一次性离线导入
- **统一抽象**：文件源、API 源、数据库源统一抽象为 Source + Sync Job + Document + Chunk 模型
- **可追溯**：每个检索结果都能追溯到数据源、文档、chunk 和任务
- **安全内聚**：外部用户身份与权限由 Java 后端负责，内部服务按权限上下文做 ACL 过滤
- **一期可落地**：优先跑通文件源/API 源，数据库源保留扩展位

### 1.3 一期交付范围
- 数据源管理：新增、查看、启停、触发同步
- 索引构建：文件源、API 源全量/增量同步
- 数据处理：文本抽取、清洗、切分、embedding、元数据落库
- 内部检索：支持语义检索、元数据过滤、ACL 过滤
- 内部问答：基于检索结果返回答案与引用
- 运维接口：健康检查、任务状态查询、失败信息记录

---

## 2. 整体架构设计

### 2.1 架构分层

```text
                        ┌──────────────────────┐
                        │     Java Backend     │
                        │  - Auth / ACL / API  │
                        │  - Biz aggregation   │
                        └──────────┬───────────┘
                                   │ Internal HTTP
                        ┌──────────▼───────────┐
                        │ knowledge-indexer    │
                        │  FastAPI + Services  │
                        │  CocoIndex Flows     │
                        └──────┬─────┬─────┬───┘
                               │     │     │
                 ┌─────────────▼┐ ┌──▼───┐ ┌─────────────▼─────┐
                 │ PostgreSQL   │ │Redis │ │ MinIO             │
                 │ + pgvector   │ │Queue │ │ Raw files/snapshot│
                 └──────────────┘ └──────┘ └───────────────────┘
                               ▲
                               │
                 ┌─────────────┴──────────────────────────────┐
                 │ Sources: Files / APIs / Databases          │
                 └────────────────────────────────────────────┘
```

### 2.2 系统职责划分

#### Java Backend
- 对外暴露统一业务 API
- 承担用户登录态、鉴权、组织与角色解析
- 将检索所需权限上下文透传给 `knowledge-indexer`
- 对搜索/问答结果做业务侧封装

#### knowledge-indexer
- 维护数据源配置与同步任务
- 通过 CocoIndex Flow 执行数据处理与索引更新
- 提供检索、问答、任务状态等内部 API
- 做 ACL 过滤、证据拼装、失败记录和健康检查

### 2.3 部署形态
- **一期部署**：`Docker Compose`
- **服务组成**：`knowledge-indexer`、`postgres`、`redis`、`minio`
- **生产演进**：后续可迁移至 `Kubernetes`，将同步任务、API 服务拆分为独立 Deployment / Worker

### 2.4 目录建议

```text
knowledge-indexer/
├── app/
│   ├── api/
│   ├── flows/
│   ├── connectors/
│   ├── services/
│   ├── repositories/
│   ├── models/
│   ├── schemas/
│   ├── workers/
│   ├── core/
│   └── main.py
├── scripts/
├── migrations/
├── tests/
├── docker/
├── pyproject.toml
├── .env.example
├── README.md
└── .gitignore
```

### 2.5 模块设计

| 模块 | 职责 | 一期状态 |
| --- | --- | --- |
| `source-manager` | 管理数据源配置、校验参数、生成同步任务 | 必做 |
| `flow-runner` | 调度 CocoIndex flow，执行全量/增量同步 | 必做 |
| `document-processor` | 文本抽取、清洗、切分、摘要/标签预留 | 必做 |
| `index-store` | 写入文档、chunk、embedding、checkpoint | 必做 |
| `retrieval-service` | 向量检索、元数据过滤、ACL 过滤、重排预留 | 必做 |
| `qa-service` | RAG 问答、引用拼装、证据不足兜底 | 必做 |
| `job-service` | 任务状态、重试、日志、失败记录 | 必做 |
| `graph-service` | 图谱能力扩展 | 二期 |

---

## 3. 核心流程设计

### 3.1 数据源接入流程
1. Java 或运维侧调用 `POST /internal/sources` 新增数据源
2. `source-manager` 校验数据源类型、连接参数、同步策略
3. 配置写入 `data_source` 表
4. 若需要测试连通性，可执行轻量探测并记录结果

### 3.2 同步任务流程
1. 调用 `POST /internal/sources/{id}/sync` 创建任务
2. `job-service` 写入 `index_job`，状态初始化为 `PENDING`
3. `flow-runner` 从 Redis 队列消费任务，切换为 `RUNNING`
4. 根据数据源类型加载对应 Connector：
   - 文件源：扫描目录/同步目录
   - API 源：调用上游接口获取分页或变更数据
   - 数据库源：按增量列或更新时间拉取数据
5. Connector 将原始记录映射为统一文档结构
6. CocoIndex Flow 执行文本抽取、清洗、切 chunk、embedding 生成
7. `index-store` 写入文档、chunk、embedding，并更新 `sync_checkpoint`
8. 任务完成后将状态更新为 `SUCCEEDED` 或 `FAILED`

### 3.3 检索流程
1. Java 侧调用 `POST /internal/search`
2. 传入查询语句、过滤条件、权限上下文
3. `retrieval-service` 生成查询向量
4. 基于 `knowledge_chunk.embedding` 做向量检索
5. 按数据源、业务字段、文档类型做元数据过滤
6. 按 `document_acl` 与权限上下文做 ACL 过滤
7. 聚合 chunk、文档信息、匹配分数并返回引用结果

### 3.4 问答流程
1. Java 侧调用 `POST /internal/ask`
2. `qa-service` 先调用内部检索流程拿到候选证据
3. 若命中证据不足，直接返回“证据不足”兜底结果
4. 若证据充分，则调用大模型生成答案
5. 返回答案正文、引用片段、引用文档、置信说明

### 3.5 失败与重试策略
- 任务级失败：更新 `index_job.status=FAILED`，保留错误摘要与失败样本位置
- 文档级失败：写入失败计数，不阻断整批任务完成
- embedding 失败：标记 chunk 状态并支持后续补偿重跑
- API 超时/限流：采用指数退避与最大重试次数控制
- 幂等策略：同一 `source_id + external_doc_id + content_hash` 识别新增/更新/跳过

---

## 4. 接口定义

### 4.1 通用约定
- 协议：内部 HTTP/JSON
- 鉴权：一期建议通过网关内网访问控制 + 服务间 Token；业务用户权限由 Java 透传
- 返回结构统一：`code`、`message`、`data`、`request_id`

### 4.2 数据源管理

#### `POST /internal/sources`
新增数据源。

请求体示例：

```json
{
  "name": "product-docs",
  "type": "file",
  "config": {
    "root_path": "/data/docs/product",
    "file_patterns": ["**/*.md", "**/*.pdf"]
  },
  "sync_mode": "incremental",
  "schedule": null,
  "enabled": true
}
```

返回字段：
- `id`：数据源 ID
- `name`：数据源名称
- `type`：数据源类型
- `status`：启用状态

#### `GET /internal/sources/{id}`
查询数据源详情，返回配置摘要、最近任务、最近同步时间。

#### `POST /internal/sources/{id}/sync`
触发同步任务。

请求体示例：

```json
{
  "mode": "incremental",
  "operator": "system",
  "options": {
    "force_rebuild": false
  }
}
```

返回字段：
- `job_id`
- `status`
- `queued_at`

### 4.3 任务接口

#### `GET /internal/jobs/{id}`
查询任务状态。

返回字段：
- `id`
- `source_id`
- `mode`
- `status`
- `processed_count`
- `failed_count`
- `started_at`
- `finished_at`
- `error_summary`

### 4.4 检索接口

#### `POST /internal/search`

请求体示例：

```json
{
  "query": "退款规则是什么",
  "top_k": 5,
  "filters": {
    "source_ids": ["src_001"],
    "doc_types": ["faq", "policy"]
  },
  "acl_context": {
    "user_id": "u123",
    "roles": ["cs"],
    "departments": ["support"],
    "tags": ["internal"]
  }
}
```

返回体示例：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "items": [
      {
        "chunk_id": "chk_001",
        "document_id": "doc_001",
        "score": 0.91,
        "content": "退款需在订单完成后 7 天内发起申请。",
        "source": {
          "source_id": "src_001",
          "source_type": "api"
        },
        "document": {
          "title": "售后规则",
          "external_id": "faq-1001"
        },
        "citation": {
          "doc_title": "售后规则",
          "chunk_index": 3
        }
      }
    ]
  },
  "request_id": "req_xxx"
}
```

### 4.5 问答接口

#### `POST /internal/ask`

请求体示例：

```json
{
  "question": "退款必须多久到账？",
  "top_k": 5,
  "filters": {
    "source_ids": ["src_001"]
  },
  "acl_context": {
    "user_id": "u123",
    "roles": ["cs"]
  }
}
```

返回字段：
- `answer`：问答结果
- `citations`：引用片段列表
- `evidence_status`：`SUFFICIENT` / `INSUFFICIENT`
- `reason`：证据不足时的说明

### 4.6 健康检查

#### `GET /health`
返回应用、数据库、Redis、对象存储和模型依赖的健康状态摘要。

---

## 5. 数据结构定义

### 5.1 表结构设计

#### `data_source`
用于维护数据源配置。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | varchar | 主键 |
| `name` | varchar | 数据源名称 |
| `type` | varchar | `file` / `api` / `postgres` |
| `config` | jsonb | 连接配置与拉取参数 |
| `sync_mode` | varchar | `full` / `incremental` |
| `enabled` | boolean | 是否启用 |
| `last_sync_at` | timestamptz | 最近同步时间 |
| `created_at` | timestamptz | 创建时间 |
| `updated_at` | timestamptz | 更新时间 |

#### `knowledge_document`
文档主表。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | varchar | 主键 |
| `source_id` | varchar | 归属数据源 |
| `external_doc_id` | varchar | 源系统文档 ID |
| `title` | varchar | 文档标题 |
| `content_text` | text | 清洗后的全文 |
| `content_hash` | varchar | 内容哈希，用于幂等判断 |
| `doc_type` | varchar | 文档类型 |
| `metadata` | jsonb | 扩展元数据 |
| `status` | varchar | `ACTIVE` / `DELETED` / `FAILED` |
| `version` | integer | 版本号 |
| `created_at` | timestamptz | 创建时间 |
| `updated_at` | timestamptz | 更新时间 |

建议索引：
- `(source_id, external_doc_id)` 唯一索引
- `metadata` 的 GIN 索引

#### `knowledge_chunk`
文档切片表。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | varchar | 主键 |
| `document_id` | varchar | 所属文档 |
| `chunk_index` | integer | 在文档中的顺序 |
| `content` | text | chunk 内容 |
| `summary` | text | 摘要，可空 |
| `token_count` | integer | token 数 |
| `metadata` | jsonb | 扩展字段 |
| `embedding` | vector | pgvector 向量 |
| `embedding_status` | varchar | `PENDING` / `DONE` / `FAILED` |
| `created_at` | timestamptz | 创建时间 |
| `updated_at` | timestamptz | 更新时间 |

建议索引：
- `document_id + chunk_index` 唯一索引
- `embedding` 向量索引（HNSW/IVFFlat，视数据规模选型）

#### `document_acl`
文档权限信息。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | varchar | 主键 |
| `document_id` | varchar | 文档 ID |
| `acl_type` | varchar | `user` / `role` / `department` / `tag` |
| `acl_value` | varchar | 权限值 |
| `effect` | varchar | `allow` / `deny` |
| `created_at` | timestamptz | 创建时间 |

#### `index_job`
同步任务表。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | varchar | 主键 |
| `source_id` | varchar | 关联数据源 |
| `mode` | varchar | `full` / `incremental` / `rebuild` |
| `status` | varchar | `PENDING` / `RUNNING` / `SUCCEEDED` / `FAILED` |
| `triggered_by` | varchar | 触发人/系统 |
| `processed_count` | integer | 已处理文档数 |
| `failed_count` | integer | 失败文档数 |
| `error_summary` | text | 失败摘要 |
| `snapshot_path` | varchar | 快照/失败样本路径 |
| `started_at` | timestamptz | 开始时间 |
| `finished_at` | timestamptz | 结束时间 |
| `created_at` | timestamptz | 创建时间 |

#### `sync_checkpoint`
增量游标表。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | varchar | 主键 |
| `source_id` | varchar | 数据源 ID |
| `checkpoint_key` | varchar | 游标类型 |
| `checkpoint_value` | text | 游标值 |
| `updated_at` | timestamptz | 更新时间 |

### 5.2 核心对象模型

#### SourceConfig
```json
{
  "id": "src_001",
  "type": "api",
  "config": {
    "base_url": "http://xxx/internal/knowledge",
    "auth": {
      "type": "token"
    },
    "pagination": {
      "page_size": 100
    }
  },
  "sync_mode": "incremental"
}
```

#### DocumentPayload
```json
{
  "external_doc_id": "faq-1001",
  "title": "售后规则",
  "content": "原始内容或抽取后的正文",
  "metadata": {
    "category": "faq",
    "updated_at": "2026-03-23T10:00:00Z"
  },
  "acl": [
    {
      "type": "role",
      "value": "cs",
      "effect": "allow"
    }
  ]
}
```

---

## 6. 核心逻辑说明

### 6.1 Connector 抽象
定义统一 Connector 接口，屏蔽不同数据源的拉取差异：
- `test_connection()`：连通性探测
- `pull_full()`：全量拉取
- `pull_incremental(checkpoint)`：增量拉取
- `normalize(record)`：标准化为统一文档结构

一期实现：
- `FileConnector`
- `ApiConnector`

二期扩展：
- `PostgresConnector`

### 6.2 文档标准化
所有来源统一映射为标准文档对象：
- 主标识：`source_id + external_doc_id`
- 内容字段：`title + content + metadata`
- 权限字段：`acl`
- 增量字段：`updated_at` / 自定义 checkpoint

这样可以保证文件源、API 源、数据库源在后续处理链路上共享同一套逻辑。

### 6.3 切分与向量化策略
- 切分规则：按段落优先、长度兜底，保留上下文重叠
- 推荐参数：每块 300~800 tokens，重叠 50~100 tokens
- embedding：封装为统一 Provider 接口，兼容不同模型供应商
- 向量写入：与 chunk 同步写入 `knowledge_chunk`

### 6.4 增量同步策略
- 文件源：基于文件修改时间 + 内容哈希判断增量
- API 源：基于更新时间、水位 ID 或分页游标推进 checkpoint
- 数据库源：预留基于 `updated_at` / `ordinal_column` 的增量实现
- 删除处理：源记录缺失时可标记 `knowledge_document.status=DELETED`

### 6.5 ACL 过滤策略
- Java 后端负责产出调用上下文：`user_id`、`roles`、`departments`、`tags`
- `retrieval-service` 在检索结果阶段按 `document_acl` 做 allow/deny 计算
- 推荐默认策略：
  - 无 ACL 配置的文档视为内部公开
  - 命中显式 deny 时拒绝返回
  - 命中任一 allow 且未命中 deny 时允许返回

### 6.6 问答兜底策略
- 低召回：检索条数不足或分数低于阈值时直接返回证据不足
- 低置信：模型生成答案前先校验引用数量和覆盖度
- 输出格式中显式包含 `evidence_status` 和 `citations`
- 不返回未引用的推测性事实

---

## 7. 依赖设计

### 7.1 技术栈
- Python `3.11` 或 `3.12`
- FastAPI：内部 API 服务
- CocoIndex：索引编排与增量处理框架
- PostgreSQL + pgvector：元数据、chunk、向量、任务状态
- Redis：任务队列、幂等控制、缓存
- MinIO：原始文件、快照、失败样本存储

### 7.2 推荐 Python 依赖
- `fastapi`：Web 框架
- `uvicorn`：应用启动
- `pydantic`：配置与请求模型校验
- `sqlalchemy` / `sqlmodel`：数据库访问
- `psycopg`：PostgreSQL 驱动
- `redis`：Redis 客户端
- `minio`：对象存储客户端
- `alembic`：数据库迁移
- `httpx`：调用外部 API
- `tenacity`：重试策略
- `structlog` 或标准 logging：结构化日志

### 7.3 外部依赖
- embedding 模型供应商或内部模型网关
- 问答模型供应商或内部模型网关
- 文件抽取工具链（PDF/Office 解析能力按数据类型补齐）

---

## 8. 风险点与应对

| 风险 | 描述 | 应对方案 |
| --- | --- | --- |
| 权限上下文不统一 | Java 侧角色/部门/标签格式尚未收敛 | 在一期接口层定义 `acl_context` 标准结构，并留扩展字段 |
| API 源不稳定 | 上游接口超时、限流、数据结构变更 | 做重试、熔断、失败记录，Connector 统一做 schema 校验 |
| 文档格式复杂 | PDF/扫描件/OCR 内容抽取质量不稳定 | 一期优先支持文本、Markdown、基础 PDF，复杂格式后补 |
| 向量成本不可控 | embedding 调用次数大，成本和耗时高 | 通过内容哈希避免重复生成，支持批量 embedding |
| 检索质量不稳定 | chunk 粒度不合适导致召回差 | 将 chunk 参数配置化，并预留 rerank 接口 |
| 任务堆积 | 大批量同步导致 Worker 堵塞 | Redis 队列限流、任务并发控制、按数据源串行化 |
| 模型依赖不可用 | 外部模型服务波动 | 预留降级策略，检索接口与问答接口解耦 |

---

## 9. 工作量估算

### 9.1 阶段拆分

| 阶段 | 主要内容 | 预估工作量 |
| --- | --- | --- |
| Phase 1 | 项目骨架、配置体系、数据库/Redis/MinIO 接入 | 3~4 人日 |
| Phase 2 | 文件源 Connector、CocoIndex Flow、文档/Chunk 入库 | 4~6 人日 |
| Phase 3 | 数据源管理接口、任务接口、健康检查 | 3~4 人日 |
| Phase 4 | 检索接口、向量查询、ACL 过滤 | 4~5 人日 |
| Phase 5 | API 源 Connector、增量 checkpoint、失败重试 | 4~6 人日 |
| Phase 6 | 问答接口、引用拼装、证据不足兜底 | 3~5 人日 |
| Phase 7 | 联调、测试、部署脚本与文档 | 3~4 人日 |

### 9.2 总体估算
- **一期可用版本**：约 `24 ~ 34 人日`
- **建议投入**：1 名后端主力 + 1 名协作开发 / 测试支持
- **优先级建议**：先交付文件源检索闭环，再扩展 API 源和问答能力

---

## 10. 待确认事项
- Java 传入的 `acl_context` 字段定义是否能在一期前冻结
- API 源的具体接入系统清单、QPS、鉴权方式是否明确
- 一期问答能力是否直接接入大模型，以及具体模型网关方案
- 文件源是否直接消费 MinIO，还是通过挂载目录间接消费
- 生产环境部署标准是继续 Compose 还是直接落 Kubernetes

## 11. 本阶段结论
- `knowledge-indexer` 应建设为独立 Python 后端服务，而非前端项目或 Java 子模块
- 一期以 `Python + CocoIndex + FastAPI + PostgreSQL/pgvector + Redis + MinIO` 为核心技术栈最稳妥
- Java 后端继续承担对外 API、鉴权与业务整合，`knowledge-indexer` 聚焦索引生命周期与内部检索/问答能力
- 交付顺序建议优先打通“文件源 -> 索引 -> 检索”闭环，再逐步扩展 API 源、问答与任务中心增强能力

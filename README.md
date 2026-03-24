# knowledge-indexer

`knowledge-indexer` 是企业知识库二期的索引、检索与内部问答底座，面向 Java 业务后端提供内部能力。它负责数据源接入、同步任务编排、文档切分、向量检索、ACL 过滤、任务追踪与运行时可观测；用户体系、外部业务接口、最终页面交互仍由现有 Java 后端负责。

## 二期能力概览

- 内部接口保持稳定：`/internal/sources`、`/internal/jobs/{id}`、`/internal/search`、`/internal/ask`、`/health`
- 仓储支持按配置切换：`inmemory` / `postgres`
- 同步链路支持两种执行模式：接口内联执行，或 Redis 队列 + worker 异步执行
- 数据源支持 `file`、`api`、`postgres`，其中 `postgres` 支持字段映射、增量 checkpoint、删除标记、ACL / metadata 映射
- 检索链路支持基于 `pgvector` 的向量召回、过滤与 ACL 校验
- 健康检查覆盖 PostgreSQL、Redis、MinIO、embedding provider、pipeline engine
- 同步过程支持快照 / 失败样本归档到 MinIO

## 职责边界

- `knowledge-indexer`：知识抽取、索引构建、检索与问答、内部同步任务管理
- Java 后端：登录态、租户 / 用户体系、业务权限解析、外部 API 编排、页面展示

推荐接入方式：Java 后端在收到用户请求后，完成身份与权限解析，再调用 `knowledge-indexer` 的内部检索 / 问答接口，并把 ACL 上下文透传过来。

## 快速开始

### 1. 仅本地跑通链路

适合开发调试、接口联调。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
uvicorn app.main:app --reload
```

默认配置下：

- `REPOSITORY_BACKEND=inmemory`
- `SYNC_RUN_INLINE=true`
- `EMBEDDING_PROVIDER=hash`

这意味着服务不依赖 PostgreSQL / Redis / MinIO 也能跑通，但重启后数据不会保留。

### 2. 启用二期基础设施

适合联调、预发或生产化验证。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[infra]
cp .env.example .env
```

至少补齐以下配置：

- `REPOSITORY_BACKEND=postgres`
- `DATABASE_URL=...`
- `REDIS_URL=...`
- `SYNC_RUN_INLINE=false`
- `SYNC_WORKER_ENABLED=true`
- `MINIO_ENDPOINT` / `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` / `MINIO_BUCKET`
- `EMBEDDING_PROVIDER=http`
- `EMBEDDING_API_URL=...`

然后初始化数据库：

```bash
psql "$DATABASE_URL" -f migrations/001_init_postgres.sql
```

最后启动服务：

```bash
uvicorn app.main:app --reload
```

## 关键配置

复制 `.env.example` 为 `.env` 后按需修改。

- 鉴权：`INTERNAL_API_TOKEN`
- 仓储：`REPOSITORY_BACKEND`、`DATABASE_URL`
- 队列：`SYNC_RUN_INLINE`、`SYNC_WORKER_ENABLED`、`SYNC_WORKER_POLL_TIMEOUT_SECONDS`、`SYNC_LOCK_TTL_SECONDS`、`REDIS_URL`
- embedding：`EMBEDDING_PROVIDER`、`EMBEDDING_API_URL`、`EMBEDDING_MODEL`、`EMBEDDING_API_KEY`、`EMBEDDING_TIMEOUT_SECONDS`
- 检索：`SEARCH_SCORE_THRESHOLD`、`MIN_EVIDENCE_COUNT`、`RETRIEVAL_CANDIDATE_MULTIPLIER`
- 归档：`MINIO_ENDPOINT`、`MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY`、`MINIO_BUCKET`

完整说明见 `docs/usage.md`。

## 接口与运行方式变化

二期没有新增面向终端用户的公开接口，也没有改动已有内部路径；主要变化在于运行时语义增强：

- 数据可持久化到 PostgreSQL，而不是仅存在内存
- 同步任务可异步执行，任务状态包含 `PENDING` / `RUNNING` / `SUCCEEDED` / `FAILED` / `CANCELLED`
- `/health` 会返回分层健康信息，而不只是简单存活结果
- 检索可以切换到真实 embedding provider 与 `pgvector` 检索

这意味着 Java 调用方通常不需要改路径，但需要根据部署方式决定：

- 是否轮询 `/internal/jobs/{job_id}`
- 是否传递完整 ACL 上下文
- 是否在联调时检查 `/health` 中各层依赖状态

## Java 联调建议

推荐的调用顺序：

1. 调用 `/health` 检查数据库、Redis、MinIO、embedding 状态
2. 创建或查询数据源
3. 触发 `full` / `incremental` / `rebuild` 同步
4. 轮询 `/internal/jobs/{job_id}` 直到任务完成
5. 调用 `/internal/search` 或 `/internal/ask`
6. 将 `acl_context` 中的 `user_id`、`roles`、`departments`、`tags` 从 Java 后端透传

`docs/usage.md` 中提供了可直接参考的 Java `HttpClient` 示例。

## 一期迁移到二期

建议按“低风险逐步切换”迁移：

1. 先保持接口路径不变，只升级服务版本
2. 在联调环境准备 PostgreSQL + pgvector、Redis、MinIO
3. 执行 `migrations/001_init_postgres.sql`
4. 先切换 `REPOSITORY_BACKEND=postgres`，确认数据源、任务、文档和 chunk 持久化正常
5. 再切换 `SYNC_RUN_INLINE=false` 与 `REDIS_URL`，验证异步任务链路
6. 最后切换 `EMBEDDING_PROVIDER=http`，验证真实向量召回效果

回滚时优先回退配置，而不是先改接口：

- 回退到一期式运行：`REPOSITORY_BACKEND=inmemory`、`SYNC_RUN_INLINE=true`、移除 `REDIS_URL` / `MINIO_*`
- 若真实 embedding provider 不稳定，可先回退到 `EMBEDDING_PROVIDER=hash` 应急
- 已写入 PostgreSQL 的数据可以保留，不影响回退到内存模式启动；只是后续新写入不再落库

## 目录说明

- `app/api/`：内部 HTTP 接口
- `app/connectors/`：文件源、API 源、PostgreSQL 数据源连接器
- `app/services/`：同步、索引、检索、问答、embedding 等核心逻辑
- `app/repositories/`：`inmemory` / `postgres` 两套仓储实现
- `migrations/`：PostgreSQL + pgvector 初始化脚本
- `docker/`：本地基础设施编排
- `docs/usage.md`：详细配置、接口、联调与迁移手册

## 当前限制

- 当前问答仍是“检索结果拼装回答”，不是完整大模型生成链路
- 当前未提供取消任务的 HTTP 接口，`CANCELLED` 状态仅保留状态机兼容能力
- rerank 仍为扩展点，默认未启用
- `pipeline_engine` 当前显示为内置索引引擎，而非外部编排引擎

## 相关文档

- 详细使用说明：`docs/usage.md`
- 数据库初始化：`migrations/001_init_postgres.sql`
- 迁移说明：`migrations/README.md`
- 环境变量示例：`.env.example`

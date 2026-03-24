# knowledge-indexer 使用文档

本文档面向接入方、开发同学和联调同学，描述知识库二期当前已经落地的能力、配置方式、接口用法、Java 联调示例，以及从一期迁移到二期时的操作建议。

## 1. 项目定位

`knowledge-indexer` 是知识库内部能力服务，职责聚焦在：

- 管理数据源
- 执行同步任务与索引构建
- 提供内部检索接口 `/internal/search`
- 提供内部问答接口 `/internal/ask`
- 提供任务查询接口 `/internal/jobs/{id}`
- 提供运行时健康检查接口 `/health`

系统边界保持不变：

- Java 后端负责登录态、用户体系、外部业务接口与 ACL 上下文计算
- `knowledge-indexer` 负责知识接入、切分、向量化、检索、ACL 过滤与内部问答

## 2. 二期已落地内容

当前版本已经具备以下能力：

- 仓储支持 `inmemory` / `postgres` 双模式
- PostgreSQL + `pgvector` 表结构与检索实现已落地
- 同步任务支持 inline 执行或 Redis 队列异步执行
- 数据源支持 `file`、`api`、`postgres`
- `postgres` 数据源支持字段映射校验、增量 checkpoint、删除标记、ACL / metadata 映射
- 检索链路支持真实 embedding provider 或本地 `hash` provider
- `/health` 输出数据库、Redis、MinIO、embedding、pipeline engine 的分层状态
- 同步任务支持原文快照 / 失败样本归档到 MinIO

当前仍未作为正式能力交付的部分：

- 取消任务的 HTTP 接口
- 默认开启的 rerank 服务
- 外部编排引擎替代当前内置索引引擎
- 面向终端用户的公开 API

## 3. 环境依赖

### 3.1 最低依赖

- Python `3.11` 或 `3.12`
- 建议使用虚拟环境 `venv`

### 3.2 可选依赖

- PostgreSQL `16+`，并安装 `pgvector` 扩展
- Redis `7+`
- MinIO
- 可用的 embedding HTTP 服务

### 3.3 安装方式

只跑本地轻量模式：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

启用二期完整依赖：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[infra]
```

如果还需要测试依赖：

```bash
pip install -e .[dev,infra]
```

## 4. 目录说明

- `app/main.py`：FastAPI 入口
- `app/api/`：内部 HTTP 接口
- `app/connectors/`：文件源、API 源、PostgreSQL 数据源连接器
- `app/repositories/`：`inmemory` / `postgres` 仓储实现
- `app/services/`：同步、索引、检索、问答、embedding 等核心逻辑
- `scripts/`：通过内部 API 触发同步的脚本
- `migrations/`：数据库初始化脚本
- `docker/`：基础设施编排
- `tests/`：测试代码

## 5. 配置说明

### 5.1 初始化配置文件

```bash
cp .env.example .env
```

### 5.2 核心环境变量

| 变量名 | 说明 | 默认值 / 建议 |
| --- | --- | --- |
| `APP_NAME` | 应用名 | `knowledge-indexer` |
| `APP_ENV` | 运行环境 | `local` |
| `INTERNAL_API_TOKEN` | `/internal/*` 路由鉴权 Token；为空则不鉴权 | 空 |
| `DEFAULT_CHUNK_SIZE` | 文本切分大小 | `600` |
| `DEFAULT_CHUNK_OVERLAP` | 文本切分重叠大小 | `80` |
| `SEARCH_SCORE_THRESHOLD` | 检索最低得分阈值 | `0.12` |
| `MIN_EVIDENCE_COUNT` | 问答最少证据数 | `1` |
| `RETRIEVAL_CANDIDATE_MULTIPLIER` | 向量召回候选倍数 | `4` |
| `API_CONNECTOR_TIMEOUT_SECONDS` | API 数据源拉取超时 | `10` |

### 5.3 仓储与数据库配置

| 变量名 | 说明 | 默认值 / 建议 |
| --- | --- | --- |
| `REPOSITORY_BACKEND` | 仓储后端，支持 `inmemory` / `postgres` | `inmemory` |
| `DATABASE_URL` | PostgreSQL 连接串 | 二期建议必配 |

说明：

- `REPOSITORY_BACKEND=inmemory` 适合快速验证，服务重启后数据会丢失
- `REPOSITORY_BACKEND=postgres` 时，需要先执行数据库初始化脚本

### 5.4 同步任务配置

| 变量名 | 说明 | 默认值 / 建议 |
| --- | --- | --- |
| `SYNC_RUN_INLINE` | `true` 时在请求线程内执行同步 | `true` |
| `SYNC_WORKER_ENABLED` | `false` 时不启动后台 worker | `true` |
| `SYNC_WORKER_POLL_TIMEOUT_SECONDS` | worker 拉取队列超时 | `1.0` |
| `SYNC_LOCK_TTL_SECONDS` | 同一数据源的互斥锁 TTL | `1800` |
| `REDIS_URL` | Redis 连接串；未配置时退化为内存队列 | 空 |

推荐组合：

- 本地开发：`SYNC_RUN_INLINE=true`
- 联调 / 预发 / 生产：`SYNC_RUN_INLINE=false`、`SYNC_WORKER_ENABLED=true`、`REDIS_URL` 已配置

### 5.5 Embedding 配置

| 变量名 | 说明 | 默认值 / 建议 |
| --- | --- | --- |
| `EMBEDDING_PROVIDER` | 支持 `hash` / `http` / `remote` | `hash` |
| `EMBEDDING_DIMENSION` | `hash` provider 向量维度 | `64` |
| `EMBEDDING_API_URL` | 远程 embedding 服务地址 | 空 |
| `EMBEDDING_MODEL` | 可选模型名 | 空 |
| `EMBEDDING_API_KEY` | 可选访问凭证 | 空 |
| `EMBEDDING_TIMEOUT_SECONDS` | embedding 请求超时 | `10.0` |

说明：

- `hash` 仅适合开发或应急回退，不代表生产效果
- `http` / `remote` 会向 `EMBEDDING_API_URL` 发起 HTTP 请求，并兼容多种常见返回格式

### 5.6 MinIO 配置

| 变量名 | 说明 | 默认值 / 建议 |
| --- | --- | --- |
| `MINIO_ENDPOINT` | MinIO 地址，支持 `host:port` 或完整 URL | 空 |
| `MINIO_ACCESS_KEY` | MinIO Access Key | 空 |
| `MINIO_SECRET_KEY` | MinIO Secret Key | 空 |
| `MINIO_BUCKET` | 归档 bucket 名称 | 空 |

说明：

- 不配置 `MINIO_*` 时，归档能力会自动关闭
- bucket 需要提前创建；服务不会自动建 bucket

## 6. 启动方式

### 6.1 轻量本地模式

适合单机调试、快速联调。

建议配置：

```env
REPOSITORY_BACKEND=inmemory
SYNC_RUN_INLINE=true
EMBEDDING_PROVIDER=hash
```

启动：

```bash
uvicorn app.main:app --reload
```

### 6.2 PostgreSQL 持久化模式

先初始化数据库：

```bash
psql "$DATABASE_URL" -f migrations/001_init_postgres.sql
```

再配置：

```env
REPOSITORY_BACKEND=postgres
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/knowledge_indexer
SYNC_RUN_INLINE=true
EMBEDDING_PROVIDER=hash
```

这个模式已经能让数据源、任务、文档、chunk 持久化到 PostgreSQL。

### 6.3 异步队列模式

建议配置：

```env
REPOSITORY_BACKEND=postgres
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/knowledge_indexer
REDIS_URL=redis://localhost:6379/0
SYNC_RUN_INLINE=false
SYNC_WORKER_ENABLED=true
```

行为说明：

- 触发同步后，接口会立即返回 `job_id`
- worker 后台从 Redis 队列取任务并执行
- 同一 `source_id` 同时只允许一个活跃任务
- worker 重启时会把未完成的 `RUNNING` 任务恢复为 `FAILED`

### 6.4 Docker Compose 启动

项目提供 `docker/docker-compose.yml`，可用于拉起：

- `knowledge-indexer`
- `postgres`
- `redis`
- `minio`

启动命令：

```bash
docker compose -f docker/docker-compose.yml up --build
```

说明：

- Compose 文件当前通过 `../.env.example` 注入默认环境变量
- 如果你需要自定义配置，请先同步更新 `.env.example` 或调整 compose 配置

## 7. 数据初始化

### 7.1 PostgreSQL 初始化

数据库需要启用 `pgvector` 扩展。初始化脚本会创建：

- `kb_sources`
- `kb_sync_jobs`
- `kb_sync_checkpoints`
- `kb_documents`
- `kb_chunks`

执行方式：

```bash
psql "$DATABASE_URL" -f migrations/001_init_postgres.sql
```

### 7.2 MinIO 初始化

需要提前创建 bucket，例如 `knowledge-indexer`。可以通过 MinIO Console 或 `mc` 客户端完成。

### 7.3 启动前自检

建议至少验证：

- PostgreSQL 可以连接，且已执行初始化脚本
- Redis 可用
- MinIO bucket 已存在
- embedding 服务地址可访问

## 8. 鉴权与统一响应

### 8.1 鉴权说明

所有 `/internal/*` 路由都支持通过请求头 `X-Internal-Token` 做内部鉴权。

- 当 `INTERNAL_API_TOKEN` 为空时：不做鉴权
- 当 `INTERNAL_API_TOKEN` 已配置时：必须传正确的 `X-Internal-Token`

`/health` 不要求鉴权。

### 8.2 统一响应结构

接口成功时统一返回：

```json
{
  "code": 0,
  "message": "ok",
  "data": {},
  "request_id": "req_xxxxxxxxxxxx"
}
```

说明：

- `request_id` 会从请求头 `X-Request-Id` 透传；如果未传，服务端会自动生成
- 响应头也会携带同一个 `X-Request-Id`

## 9. 健康检查

请求示例：

```bash
curl http://127.0.0.1:8000/health
```

返回体包含：

- `app`
- `database`
- `redis`
- `minio`
- `embedding`
- `pipeline_engine`

每个依赖节点都包含：

- `status`
- `detail`
- `layers.configuration`
- `layers.connectivity`
- `layers.capability`

示例判断：

- `database.status=reachable`：PostgreSQL 已配置且连通
- `redis.status=disabled`：未启用 Redis，当前退化到内存队列或 inline 模式
- `embedding.status=development`：仍在使用 `hash` provider

## 10. 数据源管理

### 10.1 支持的数据源类型

- `file`
- `api`
- `postgres`

### 10.2 创建文件源

```bash
curl -X POST 'http://127.0.0.1:8000/internal/sources' \
  -H 'Content-Type: application/json' \
  -H 'X-Internal-Token: your-token' \
  -d '{
    "name": "本地文档目录",
    "type": "file",
    "config": {
      "root_path": "./sample_docs",
      "file_patterns": ["**/*.md", "**/*.txt"]
    },
    "sync_mode": "incremental",
    "enabled": true
  }'
```

### 10.3 创建 API 源

```bash
curl -X POST 'http://127.0.0.1:8000/internal/sources' \
  -H 'Content-Type: application/json' \
  -H 'X-Internal-Token: your-token' \
  -d '{
    "name": "知识接口",
    "type": "api",
    "config": {
      "base_url": "http://127.0.0.1:9000/mock/knowledge",
      "params": {
        "scene": "faq"
      }
    },
    "sync_mode": "incremental",
    "enabled": true
  }'
```

API 返回可以是：

1. 文档数组
2. 带 `items` 字段的对象

增量同步时，系统会自动附加 `checkpoint` 查询参数。

### 10.4 创建 PostgreSQL 源

`postgres` 数据源是二期重点能力，要求至少配置：

- `connection_dsn`
- `table`
- `primary_key`
- `content_column`
- `updated_at_column`（在 `incremental` 模式下）

示例：

```bash
curl -X POST 'http://127.0.0.1:8000/internal/sources' \
  -H 'Content-Type: application/json' \
  -H 'X-Internal-Token: your-token' \
  -d '{
    "name": "PG 知识表",
    "type": "postgres",
    "config": {
      "connection_dsn": "postgresql://demo:secret@127.0.0.1:5432/knowledge",
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
      "metadata_columns": {
        "biz_line": "biz_line",
        "owner": "owner_name"
      },
      "where_clause": "status = $$ONLINE$$",
      "batch_size": 200
    },
    "sync_mode": "incremental",
    "enabled": true
  }'
```

说明：

- `connection_dsn` 在接口响应中会自动脱敏
- `deleted_flag_column` 命中后会把文档标记为 `DELETED`
- `acl_columns` 支持 `users` / `roles` / `departments` / `tags`
- `metadata_columns` 会映射到统一文档 `metadata`
- `where_clause` 只适合放静态过滤条件

### 10.5 查询数据源详情

```bash
curl 'http://127.0.0.1:8000/internal/sources/src_xxx' \
  -H 'X-Internal-Token: your-token'
```

返回包含：

- `source`
- `latest_job`

## 11. 同步任务

### 11.1 同步模式

- `full`：全量拉取并重建数据源文档
- `incremental`：从 checkpoint 增量推进
- `rebuild`：重建索引，用于重新分块 / 重新生成向量

### 11.2 触发同步

全量：

```bash
curl -X POST 'http://127.0.0.1:8000/internal/sources/src_xxx/sync' \
  -H 'Content-Type: application/json' \
  -H 'X-Internal-Token: your-token' \
  -d '{"mode": "full", "operator": "manual"}'
```

增量：

```bash
curl -X POST 'http://127.0.0.1:8000/internal/sources/src_xxx/sync' \
  -H 'Content-Type: application/json' \
  -H 'X-Internal-Token: your-token' \
  -d '{"mode": "incremental", "operator": "manual"}'
```

重建：

```bash
curl -X POST 'http://127.0.0.1:8000/internal/sources/src_xxx/sync' \
  -H 'Content-Type: application/json' \
  -H 'X-Internal-Token: your-token' \
  -d '{
    "mode": "rebuild",
    "operator": "manual",
    "options": {"force_rebuild": true}
  }'
```

### 11.3 任务状态

当前状态机支持：

- `PENDING`
- `RUNNING`
- `SUCCEEDED`
- `FAILED`
- `CANCELLED`

其中返回详情还会包含：

- `processed_count`
- `failed_count`
- `error_summary`
- `failure_stage`
- `snapshot_path`
- `checkpoint_before`
- `checkpoint_after`
- `started_at`
- `finished_at`

`failure_stage` 可能值包括：

- `queue`
- `pull`
- `normalize`
- `embed`
- `persist`
- `worker`

### 11.4 查询任务

```bash
curl 'http://127.0.0.1:8000/internal/jobs/job_xxx' \
  -H 'X-Internal-Token: your-token'
```

### 11.5 二期联调回归建议

对 `postgres` 数据源建议至少完成以下回归：

1. 创建数据源
2. 执行一次 `full` 同步
3. 修改源表一条记录的正文和 `updated_at`
4. 执行一次 `incremental` 同步
5. 将一条记录标记为删除，再执行一次 `incremental`
6. 查看 `checkpoint_after` 是否持续推进
7. 检查被删除记录是否不再参与检索

## 12. 检索接口

### 12.1 请求示例

```bash
curl -X POST 'http://127.0.0.1:8000/internal/search' \
  -H 'Content-Type: application/json' \
  -H 'X-Internal-Token: your-token' \
  -d '{
    "query": "如何申请请假",
    "top_k": 5,
    "filters": {
      "source_ids": [],
      "doc_types": ["md", "faq"],
      "metadata": {"category": "hr"}
    },
    "acl_context": {
      "user_id": "u1001",
      "roles": ["employee"],
      "departments": ["hr"],
      "tags": []
    }
  }'
```

### 12.2 过滤顺序

当前链路大致为：

1. 根据 `source_ids` / `doc_types` / `metadata` 做粗过滤
2. 执行向量召回
3. 对文档状态做过滤
4. 执行 ACL 判定
5. 按分数阈值过滤并返回 Top-K

说明：rerank 仍保留扩展点，但默认未启用。

### 12.3 返回字段

每条命中结果包含：

- `chunk_id`
- `document_id`
- `score`
- `content`
- `source.source_id`
- `source.source_type`
- `document.title`
- `document.external_id`
- `citation.doc_title`
- `citation.chunk_index`

## 13. 问答接口

### 13.1 请求示例

```bash
curl -X POST 'http://127.0.0.1:8000/internal/ask' \
  -H 'Content-Type: application/json' \
  -H 'X-Internal-Token: your-token' \
  -d '{
    "question": "请假流程是什么",
    "top_k": 5,
    "filters": {
      "source_ids": [],
      "doc_types": [],
      "metadata": {}
    },
    "acl_context": {
      "user_id": "u1001",
      "roles": ["employee"],
      "departments": [],
      "tags": []
    }
  }'
```

### 13.2 返回说明

返回字段：

- `answer`
- `citations`
- `evidence_status`
- `reason`

当前问答逻辑是检索结果拼装：

- 命中数量少于 `MIN_EVIDENCE_COUNT` 时，返回 `INSUFFICIENT`
- 第一条结果分数低于 `SEARCH_SCORE_THRESHOLD` 时，返回 `INSUFFICIENT`
- 否则把前几条证据片段拼成回答

## 14. ACL 过滤说明

文档 ACL 支持以下类型：

- `user`
- `role`
- `department`
- `tag`

支持以下 effect：

- `allow`
- `deny`

推荐集成方式：

1. Java 后端完成登录态与权限解析
2. Java 把 `user_id`、`roles`、`departments`、`tags` 透传给 `knowledge-indexer`
3. `knowledge-indexer` 在检索阶段执行 ACL 过滤
4. Java 后端再包装结果返回前端

## 15. Java 调用示例

下面示例使用 Java 11+ 自带的 `HttpClient`，演示检索调用与任务轮询。

### 15.1 发起检索

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

HttpClient client = HttpClient.newHttpClient();
String body = """
    {
      "query": "如何申请请假",
      "top_k": 5,
      "filters": {
        "source_ids": [],
        "doc_types": ["faq"],
        "metadata": {"category": "hr"}
      },
      "acl_context": {
        "user_id": "u1001",
        "roles": ["employee"],
        "departments": ["hr"],
        "tags": []
      }
    }
    """;

HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create("http://127.0.0.1:8000/internal/search"))
    .header("Content-Type", "application/json")
    .header("X-Internal-Token", "your-token")
    .POST(HttpRequest.BodyPublishers.ofString(body))
    .build();

HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
System.out.println(response.body());
```

### 15.2 触发同步并轮询任务

```java
String syncBody = """
    {
      "mode": "full",
      "operator": "java-backend"
    }
    """;

HttpRequest triggerRequest = HttpRequest.newBuilder()
    .uri(URI.create("http://127.0.0.1:8000/internal/sources/src_xxx/sync"))
    .header("Content-Type", "application/json")
    .header("X-Internal-Token", "your-token")
    .POST(HttpRequest.BodyPublishers.ofString(syncBody))
    .build();

HttpResponse<String> triggerResponse = client.send(triggerRequest, HttpResponse.BodyHandlers.ofString());
System.out.println(triggerResponse.body());

// 从返回 JSON 中取出 data.job_id 后轮询 /internal/jobs/{job_id}
```

联调建议：

- Java 不要自行缓存知识文档权限结果，应实时透传 ACL 上下文
- 如果使用异步模式，必须轮询 `job_id`，不要假设触发接口返回即表示同步完成
- 对 `request_id` 做日志透传，方便跨服务排查

## 16. 自带脚本

通过内部 API 触发同步：

```bash
python scripts/run_full_sync.py src_xxx --base-url http://127.0.0.1:8000 --token your-token
python scripts/run_incremental_sync.py src_xxx --base-url http://127.0.0.1:8000 --token your-token
python scripts/rebuild_index.py src_xxx --base-url http://127.0.0.1:8000 --token your-token
```

## 17. 一期迁移到二期

### 17.1 接口兼容性

- 内部路径保持不变
- 成功响应结构保持不变
- Java 侧主要新增关注点是任务轮询、ACL 透传和健康检查层级

### 17.2 推荐迁移步骤

1. 升级服务代码，但先保持 `REPOSITORY_BACKEND=inmemory`
2. 在联调环境准备 PostgreSQL、Redis、MinIO、embedding 服务
3. 执行 `migrations/001_init_postgres.sql`
4. 切换 `REPOSITORY_BACKEND=postgres`，验证持久化
5. 切换 `SYNC_RUN_INLINE=false` 与 `REDIS_URL`，验证异步任务
6. 切换 `MINIO_*`，验证归档与 `/health`
7. 切换 `EMBEDDING_PROVIDER=http`，验证真实向量效果

### 17.3 验收检查项

迁移后建议至少确认：

- 创建数据源后服务重启，数据仍存在
- 同步任务可以从 `PENDING` 正常流转到 `SUCCEEDED` / `FAILED`
- `/health` 中 PostgreSQL、Redis、MinIO、embedding 状态符合预期
- 检索命中数量与 ACL 过滤结果符合预期

### 17.4 回滚注意事项

- 优先通过配置回滚，不建议先改接口调用路径
- 如需快速回退到一期式运行，可设置：

```env
REPOSITORY_BACKEND=inmemory
SYNC_RUN_INLINE=true
EMBEDDING_PROVIDER=hash
```

- 并移除或忽略：`REDIS_URL`、`MINIO_*`
- PostgreSQL 中历史数据可以保留，不会阻止服务以 `inmemory` 模式启动
- 如果二期联调失败，回滚后需要重新做一次全量同步来恢复内存态索引

## 18. 常见问题

### 18.1 为什么 `/health` 显示 `database.disabled`？

因为当前 `REPOSITORY_BACKEND` 不是 `postgres`，服务仍在使用内存仓储。

### 18.2 为什么任务一直停留在 `PENDING`？

常见原因：

- `SYNC_RUN_INLINE=false`，但 `SYNC_WORKER_ENABLED=false`
- `REDIS_URL` 配置错误，worker 实际没有从 Redis 正常消费
- worker 尚未启动或异常退出

### 18.3 为什么创建 PostgreSQL 数据源失败？

通常是：

- `connection_dsn` 不合法或数据库不可达
- 表名 / 列名映射配置错误
- 增量模式缺少 `updated_at_column`

### 18.4 为什么检索效果变差？

通常是：

- 仍在使用 `EMBEDDING_PROVIDER=hash`
- embedding 远程服务未生效或返回异常向量
- `SEARCH_SCORE_THRESHOLD` 过高

### 18.5 为什么 MinIO 配好了但仍不可用？

常见原因：

- bucket 不存在
- 当前环境未安装 `.[infra]` 依赖
- `MINIO_ENDPOINT` 配置格式错误

## 19. 相关入口

- 项目说明：`README.md`
- 配置示例：`.env.example`
- 数据库初始化：`migrations/001_init_postgres.sql`
- 迁移说明：`migrations/README.md`
- 触发脚本：`scripts/run_full_sync.py`、`scripts/run_incremental_sync.py`、`scripts/rebuild_index.py`

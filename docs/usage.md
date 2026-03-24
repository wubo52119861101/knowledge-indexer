# knowledge-indexer 使用说明（参考文档）

本文档是 `knowledge-indexer` 的接口与配置参考文档，面向接入开发和维护者。

如果你想按真实操作路径快速跑通项目，请优先阅读 `docs/use-cases.md`；如果你要核对接口字段、环境变量、同步模式和限制说明，再查阅本文档。

## 文档定位

| 文档 | 角色 | 主要职责 |
| --- | --- | --- |
| `README.md` | 项目入口 | 提供项目定位、快速启动入口与文档地图 |
| `docs/use-cases.md` | 使用手册 | 提供按场景组织的操作案例 |
| `docs/usage.md` | 参考文档 | 提供接口、字段、配置与限制的详细说明 |

## 建议阅读路径

1. 先通过 `README.md` 了解项目定位与当前实现范围；
2. 再通过 `docs/use-cases.md` 跑通启动、同步、检索、问答等主流程；
3. 最后按需回到本文档查阅字段定义、接口示例和边界说明。

## 1. 项目说明

`knowledge-indexer` 是企业知识库一期的索引与检索底座，当前职责包括：

- 管理内部数据源
- 执行同步任务与索引构建
- 提供内部检索接口 `/internal/search`
- 提供内部问答接口 `/internal/ask`
- 提供任务查询接口 `/internal/jobs/{id}`
- 提供健康检查接口 `/health`

当前版本以“先跑通链路”为目标，默认使用内存仓储、文本切分与确定性哈希向量实现，便于本地验证和接口联调。

## 2. 当前能力边界

当前已经实现：

- `file` 数据源创建与同步
- `api` 数据源创建与同步
- `postgres` 数据源类型占位
- 文本清洗、切 chunk、向量生成、检索、ACL 过滤
- 证据不足时的问答兜底
- 任务状态记录

当前未正式实现：

- PostgreSQL 持久化仓储
- pgvector 真正向量索引
- Redis 后台任务队列
- MinIO 原文归档
- CocoIndex 正式 Flow 编排
- `postgres` 数据源同步逻辑

说明：当前服务重启后，已创建的数据源、任务和索引内容会丢失，因为仓储默认基于内存实现。

## 3. 环境要求

- Python `3.11` 或 `3.12`
- 建议使用虚拟环境 `venv`
- 本地联调可不依赖 PostgreSQL / Redis / MinIO
- 如需演示完整基础设施编排，可使用 `Docker Compose`

## 4. 目录说明

- `app/main.py`：FastAPI 入口
- `app/api/`：内部 HTTP 接口
- `app/connectors/`：文件源、API 源、数据库源连接器
- `app/services/`：索引、检索、问答、任务等核心逻辑
- `app/repositories/`：当前内存仓储实现
- `app/flows/`：面向 CocoIndex 的流程封装占位
- `scripts/`：触发全量/增量/重建索引的脚本
- `docker/`：本地依赖与容器启动配置
- `tests/`：单元测试

## 5. 本地启动

### 5.1 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

如果你只需要运行应用，不需要测试依赖，也可以安装：

```bash
pip install -e .
```

### 5.2 配置环境变量

复制示例配置：

```bash
cp .env.example .env
```

默认配置已可用于本地开发。重点参数如下：

| 变量名 | 说明 | 默认值 |
| --- | --- | --- |
| `APP_NAME` | 应用名 | `knowledge-indexer` |
| `APP_ENV` | 运行环境 | `local` |
| `INTERNAL_API_TOKEN` | 内部接口鉴权 Token；为空则不校验 | 空 |
| `DEFAULT_CHUNK_SIZE` | 默认分块大小 | `600` |
| `DEFAULT_CHUNK_OVERLAP` | 默认分块重叠 | `80` |
| `EMBEDDING_DIMENSION` | 哈希向量维度 | `64` |
| `SEARCH_SCORE_THRESHOLD` | 检索最低分阈值 | `0.12` |
| `MIN_EVIDENCE_COUNT` | 问答最少证据数 | `1` |
| `SYNC_RUN_INLINE` | 是否在触发同步时同步执行任务 | `true` |
| `DATABASE_URL` | PostgreSQL 连接串，占位 | `postgresql://postgres:postgres@localhost:5432/knowledge_indexer` |
| `REDIS_URL` | Redis 地址，占位 | `redis://localhost:6379/0` |
| `MINIO_ENDPOINT` | MinIO 地址，占位 | `localhost:9000` |
| `API_CONNECTOR_TIMEOUT_SECONDS` | API 数据源拉取超时秒数 | `10` |

### 5.3 启动服务

```bash
uvicorn app.main:app --reload
```

默认监听地址：`http://127.0.0.1:8000`

启动后可访问：

- 根路径：`GET /`
- 健康检查：`GET /health`
- OpenAPI 文档：`GET /docs`

## 6. Docker Compose 启动

项目提供了 `docker/docker-compose.yml`，可用于拉起：

- `knowledge-indexer`
- `postgres`
- `redis`
- `minio`

启动方式：

```bash
docker compose -f docker/docker-compose.yml up --build
```

说明：

- 当前应用虽然可随容器一起启动，但主业务逻辑仍使用内存仓储。
- `postgres`、`redis`、`minio` 目前主要用于一期架构预埋和后续扩展。

## 7. 鉴权说明

所有 `/internal/*` 路由都支持通过请求头 `X-Internal-Token` 做内部鉴权。

- 当 `INTERNAL_API_TOKEN` 为空时：不做鉴权
- 当 `INTERNAL_API_TOKEN` 已配置时：必须传正确的 `X-Internal-Token`

示例：

```bash
curl -H 'X-Internal-Token: your-token' http://127.0.0.1:8000/health
```

说明：`/health` 不要求鉴权；`/internal/*` 要求鉴权。

## 8. 响应结构

接口成功时统一返回：

```json
{
  "code": 0,
  "message": "ok",
  "data": {},
  "request_id": "req_xxxxxxxxxxxx"
}
```

其中：

- `code`：固定为 `0` 表示成功
- `message`：接口提示信息
- `data`：业务数据体
- `request_id`：服务端生成或透传的请求标识

如果请求头传入 `X-Request-Id`，响应头中会透传同一个值；否则服务会自动生成。

## 9. 健康检查

请求示例：

```bash
curl http://127.0.0.1:8000/health
```

返回内容会包含：

- 应用状态
- PostgreSQL 配置状态
- Redis 配置状态
- MinIO 配置状态
- 模型实现状态

注意：这里的 `database`、`redis`、`minio` 是“配置级健康检查”，表示参数是否已配置，不代表实际连接可用。

## 10. 数据源管理

### 10.1 支持的数据源类型

当前支持以下 `type`：

- `file`
- `api`
- `postgres`

说明：

- `file` 和 `api` 已可用于创建与同步
- `postgres` 当前仅为接口占位，同步时会返回未实现错误

### 10.2 创建文件源

`file` 数据源要求 `config.root_path` 存在。

示例请求：

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

字段说明：

- `root_path`：本地文件根目录
- `file_patterns`：扫描模式，默认是 `**/*.md` 和 `**/*.txt`

文件源会读取匹配文件内容，生成：

- `external_doc_id`：文件路径
- `title`：文件名去后缀
- `doc_type`：文件后缀
- `metadata.path`：文件路径
- `metadata.updated_at`：文件修改时间

### 10.3 创建 API 源

`api` 数据源要求 `config.base_url` 已配置。

示例请求：

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

接口返回值要求为以下两种格式之一：

1. 直接返回数组：

```json
[
  {
    "external_doc_id": "faq-001",
    "title": "请假制度",
    "content": "请假需提前在系统提交审批。",
    "doc_type": "faq",
    "updated_at": "2026-03-23T10:00:00Z",
    "metadata": {
      "category": "hr"
    },
    "acl": [
      {
        "type": "role",
        "value": "employee",
        "effect": "allow"
      }
    ]
  }
]
```

2. 返回对象，且对象中包含 `items`：

```json
{
  "items": [
    {
      "external_doc_id": "faq-001",
      "title": "请假制度",
      "content": "请假需提前在系统提交审批。"
    }
  ]
}
```

增量同步时，系统会自动向 API 附加 `checkpoint` 查询参数。

### 10.4 创建 Postgres 源

可以创建 `type=postgres` 的数据源，但当前仅用于预留二期能力。

- 创建接口可通过
- 触发同步时会返回 `501 Not Implemented`

## 11. 查看数据源详情

请求示例：

```bash
curl 'http://127.0.0.1:8000/internal/sources/src_xxx' \
  -H 'X-Internal-Token: your-token'
```

返回内容包含：

- `source`：数据源详情
- `latest_job`：该数据源最近一次任务

## 12. 触发同步任务

### 12.1 支持的同步模式

- `full`：全量同步
- `incremental`：增量同步
- `rebuild`：重建索引

### 12.2 触发全量同步

```bash
curl -X POST 'http://127.0.0.1:8000/internal/sources/src_xxx/sync' \
  -H 'Content-Type: application/json' \
  -H 'X-Internal-Token: your-token' \
  -d '{
    "mode": "full",
    "operator": "manual"
  }'
```

### 12.3 触发增量同步

```bash
curl -X POST 'http://127.0.0.1:8000/internal/sources/src_xxx/sync' \
  -H 'Content-Type: application/json' \
  -H 'X-Internal-Token: your-token' \
  -d '{
    "mode": "incremental",
    "operator": "manual"
  }'
```

### 12.4 触发重建索引

```bash
curl -X POST 'http://127.0.0.1:8000/internal/sources/src_xxx/sync' \
  -H 'Content-Type: application/json' \
  -H 'X-Internal-Token: your-token' \
  -d '{
    "mode": "rebuild",
    "operator": "manual",
    "options": {
      "force_rebuild": true
    }
  }'
```

### 12.5 同步执行方式

当前由环境变量 `SYNC_RUN_INLINE` 控制：

- `true`：接口收到请求后直接执行同步，适合本地调试
- `false`：接口只创建任务，不会自动执行后台流程

当前版本未接入后台任务队列，因此如果设置为 `false`，任务只会停留在创建状态，适合作为后续接入异步任务框架的占位模式。

## 13. 查询任务状态

请求示例：

```bash
curl 'http://127.0.0.1:8000/internal/jobs/job_xxx' \
  -H 'X-Internal-Token: your-token'
```

关键字段：

- `status`：`PENDING` / `RUNNING` / `SUCCEEDED` / `FAILED`
- `processed_count`：成功处理文档数
- `failed_count`：失败文档数
- `error_summary`：错误摘要
- `started_at` / `finished_at`：任务执行时间

## 14. 检索接口

### 14.1 请求示例

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
      "metadata": {
        "category": "hr"
      }
    },
    "acl_context": {
      "user_id": "u1001",
      "roles": ["employee"],
      "departments": ["hr"],
      "tags": []
    }
  }'
```

### 14.2 字段说明

- `query`：检索问题
- `top_k`：返回前 N 条，范围 `1-20`
- `filters.source_ids`：按数据源过滤
- `filters.doc_types`：按文档类型过滤
- `filters.metadata`：按文档元数据键值过滤
- `acl_context`：检索时用于权限过滤的上下文

### 14.3 返回说明

每条检索结果包含：

- `chunk_id`：片段 ID
- `document_id`：文档 ID
- `score`：检索分数
- `content`：片段内容
- `source`：来源数据源信息
- `document`：文档标题与外部 ID
- `citation`：引用信息

## 15. 问答接口

### 15.1 请求示例

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

### 15.2 返回说明

问答接口返回：

- `answer`：拼装后的回答文本
- `citations`：引用片段列表
- `evidence_status`：`SUFFICIENT` 或 `INSUFFICIENT`
- `reason`：证据不足时的原因

当前问答逻辑不是大模型生成，而是基于命中文本片段拼接结果：

- 若命中数量少于 `MIN_EVIDENCE_COUNT`，返回证据不足
- 若第一条结果分数低于 `SEARCH_SCORE_THRESHOLD`，返回证据不足
- 否则拼装前几条检索结果作为回答

## 16. ACL 权限过滤说明

文档可以带 ACL 信息，支持以下维度：

- `user`
- `role`
- `department`
- `tag`

效果类型支持：

- `allow`
- `deny`

检索时通过 `acl_context` 参与过滤。典型集成方式为：

1. Java 后端完成登录态与权限解析
2. Java 将用户角色、部门、标签等信息传给 `knowledge-indexer`
3. `knowledge-indexer` 在检索阶段做 ACL 过滤
4. 返回可见结果与引用给 Java 后端

## 17. 自带脚本

项目提供了 3 个命令行脚本，用于通过内部 API 触发任务。

### 17.1 全量同步

```bash
python scripts/run_full_sync.py src_xxx --base-url http://127.0.0.1:8000 --token your-token
```

### 17.2 增量同步

```bash
python scripts/run_incremental_sync.py src_xxx --base-url http://127.0.0.1:8000 --token your-token
```

### 17.3 重建索引

```bash
python scripts/rebuild_index.py src_xxx --base-url http://127.0.0.1:8000 --token your-token
```

## 18. 推荐联调流程

建议按以下顺序联调：

1. 启动服务
2. 调用 `/health` 确认服务正常
3. 创建一个 `file` 或 `api` 数据源
4. 触发一次 `full` 同步
5. 查询任务状态，确认 `SUCCEEDED`
6. 调用 `/internal/search` 验证检索结果
7. 调用 `/internal/ask` 验证问答兜底与引用输出

## 19. 常见问题

### 19.1 为什么重启服务后索引数据没了？

因为当前默认使用内存仓储，数据不会持久化到数据库。

### 19.2 为什么配置了 PostgreSQL / Redis / MinIO 也没有真正使用？

因为一期骨架先预留了配置与编排入口，真实持久化、队列和对象存储能力将在后续阶段接入。

### 19.3 为什么 `postgres` 数据源不能同步？

因为 `PostgresConnector` 当前仍是二期占位实现，同步时会抛出未实现错误。

### 19.4 为什么问答返回“当前证据不足”？

通常有两类原因：

- 检索命中文档数量不足
- 最高分结果低于阈值 `SEARCH_SCORE_THRESHOLD`

### 19.5 为什么内部接口返回 401？

通常是：

- 服务已配置 `INTERNAL_API_TOKEN`
- 请求没有传 `X-Internal-Token`
- 或者传入的 Token 与服务端配置不一致

## 20. 后续演进建议

建议二期按以下方向演进：

- 将仓储替换为 PostgreSQL + pgvector
- 接入 Redis 任务队列，实现真正异步同步
- 接入 MinIO 保存原始文件、失败样本与快照
- 用 CocoIndex Flow 替换当前轻量索引流程
- 实现 `postgres` 数据源增量同步
- 引入 rerank 与真实 embedding 模型

## 21. 相关入口

- 项目说明：`README.md`
- 应用入口：`app/main.py`
- 容器编排：`docker/docker-compose.yml`
- 环境变量示例：`.env.example`
- 触发脚本：`scripts/run_full_sync.py`、`scripts/run_incremental_sync.py`、`scripts/rebuild_index.py`


# knowledge-indexer

`knowledge-indexer` 是企业知识库一期的索引与检索底座，职责聚焦在数据接入、知识处理、索引构建和内部检索/问答接口；对外业务接口、用户体系、权限体系仍由现有 Java 后端负责。

## 当前实现范围
- FastAPI 内部接口：`/internal/sources`、`/internal/jobs/{id}`、`/internal/search`、`/internal/ask`、`/health`
- 一期骨架能力：文件源 / API 源接入、同步任务、文本清洗切分、确定性哈希向量、ACL 过滤、证据不足兜底
- 默认使用内存仓储，便于本地快速验证；后续可无缝替换为 PostgreSQL + pgvector + Redis + MinIO + CocoIndex

## 快速启动
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
uvicorn app.main:app --reload
```

完整使用说明见 `docs/usage.md`。

## 环境变量
复制 `.env.example` 为 `.env` 后按需修改：
- `INTERNAL_API_TOKEN`：内部接口鉴权 Token，留空则关闭校验
- `SYNC_RUN_INLINE`：是否在触发同步时直接执行索引流程
- `DATABASE_URL` / `REDIS_URL` / `MINIO_*`：二期基础设施接入参数

## 架构说明
- `app/api/`：内部 HTTP 接口
- `app/connectors/`：文件源、API 源、数据库源连接器抽象
- `app/services/`：索引、检索、问答、任务等核心业务逻辑
- `app/repositories/`：一期内存仓储实现，预留持久化替换点
- `app/flows/`：面向 CocoIndex 的流程封装占位
- `docker/`：本地依赖编排与数据库初始化脚本

## 注意事项
- 目前的 `HashEmbeddingService` 仅用于开发期跑通链路，不代表生产向量效果。
- `PostgresConnector` 已支持真实 PostgreSQL 数据源拉取；CocoIndex Flow 仍保留为后续增强入口。

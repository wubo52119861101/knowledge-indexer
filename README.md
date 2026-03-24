# knowledge-indexer

`knowledge-indexer` 是企业知识库一期的索引与检索底座，职责聚焦在数据接入、知识处理、索引构建和内部检索/问答接口；对外业务接口、用户体系、权限体系仍由现有 Java 后端负责。

## 文档导航

为避免“项目入口说明”和“详细联调说明”混在一起，当前文档按三层职责划分：

| 文档 | 角色 | 主要职责 |
| --- | --- | --- |
| `README.md` | 所有读者 | 说明项目定位、实现范围、快速启动入口与文档地图 |
| `docs/use-cases.md` | 首次接触项目的研发、测试、联调同学 | 提供场景化使用手册，强调“按步骤操作后应看到什么结果” |
| `docs/usage.md` | 接入开发、维护者 | 提供接口、配置、字段与限制的参考说明 |

建议阅读顺序：先看 `README.md` 建立全局认知，再看 `docs/use-cases.md` 跑通案例，最后按需查阅 `docs/usage.md` 做字段和接口核对。

常用入口：

- 首次启动与 10 分钟上手：[`docs/use-cases.md`](docs/use-cases.md#manual-quickstart)
- 数据源接入、同步任务与一期边界：[`docs/use-cases.md`](docs/use-cases.md#manual-sync)
- 环境变量、接口字段与 FAQ：[`docs/usage.md`](docs/usage.md#reference-quick-nav)

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

场景化使用手册见 [`docs/use-cases.md`](docs/use-cases.md#manual-quickstart)。

如果你要按业务场景联调，优先阅读 [`docs/use-cases.md`](docs/use-cases.md#manual-sync)；如果你要核对请求字段、环境变量和限制说明，再查 [`docs/usage.md`](docs/usage.md#reference-quick-nav)。

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
- `PostgresConnector` 和真正的 CocoIndex Flow 已预留接口，后续可在不改 API 合同的情况下替换实现。

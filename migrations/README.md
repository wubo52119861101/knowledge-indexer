# Migrations

二期起补充 PostgreSQL + pgvector 的初始化脚本：

- `001_init_postgres.sql`：创建 `kb_sources`、`kb_sync_jobs`、`kb_sync_checkpoints`、`kb_documents`、`kb_chunks` 以及相关索引。

当前仓库仍以初始化 SQL 为主，后续如接入 Alembic，可基于该脚本继续拆分版本迁移。

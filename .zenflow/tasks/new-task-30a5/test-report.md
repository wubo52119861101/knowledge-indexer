# 测试报告

## 1. 执行信息

- 执行时间：2026-03-24
- 执行环境：`Python 3.13.5`、`pytest 9.0.2`
- 执行命令：`python3 -m pytest -q`
- 执行结果：`31 passed, 1 skipped in 0.22s`

## 2. 测试用例清单

### 2.1 正常流程

- `tests/test_postgres_repositories.py`
  - `test_postgres_source_repository_crud_and_touch_sync`：验证数据源仓储 CRUD 与同步时间更新。
  - `test_postgres_job_repository_add_save_and_latest`：验证任务仓储新增、保存与最近任务查询。
  - `test_postgres_checkpoint_repository_upsert`：验证 checkpoint upsert。
  - `test_postgres_document_repository_upsert_and_mark_deleted`：验证文档 upsert 与删除标记。
  - `test_postgres_chunk_repository_replace_for_document`：验证 chunk 替换写入。
  - `test_postgres_chunk_repository_search_candidates`：验证检索候选召回。
  - `test_service_container_switches_to_postgres_backend`：验证容器按配置切换 PostgreSQL 仓储。

- `tests/test_postgres_connector.py`
  - `test_postgres_connector_normalize_maps_acl_metadata_and_checkpoint`：验证字段标准化、ACL / metadata / checkpoint 映射。
  - `test_postgres_connector_incremental_pull_uses_composite_checkpoint`：验证增量同步游标推进。
  - `test_source_service_validates_postgres_source_on_create`：验证创建数据源时的连接校验流程。

- `tests/test_indexing_service.py`
  - `test_successful_job_archives_raw_snapshot`：验证成功任务原文快照归档。
  - `test_sync_logs_include_structured_fields`：验证结构化日志字段输出。

- `tests/test_retrieval_service.py`
  - `test_acl_filter_only_returns_allowed_document`：验证 ACL 过滤。
  - `test_search_applies_coarse_filters_before_returning_results`：验证 source/doc_type/metadata 粗过滤。
  - `test_search_supports_optional_rerank_hook`：验证 rerank hook 生效。

- `tests/test_qa_service.py`
  - `test_qa_service_returns_evidence_driven_answer_when_hits_are_enough`：验证证据充分时返回回答与引用。

- `tests/test_document_processor.py`
  - `test_split_text_generates_multiple_chunks`：验证文本切分为多个 chunk。

- `tests/test_sync_orchestrator.py`
  - `test_trigger_sync_enqueues_and_processes_job`：验证创建任务、入队、执行与状态流转。

- `tests/test_t7_regression.py`
  - `test_t7_end_to_end_sync_retrieval_and_qa_flow`：验证端到端主链路：创建数据源 → 触发同步 → 完成索引 → 检索 → 问答。

### 2.2 异常场景

- `tests/test_indexing_service.py`
  - `test_incremental_failure_does_not_advance_checkpoint`：验证增量失败不推进 checkpoint。
  - `test_full_sync_marks_missing_documents_deleted_and_clears_chunks`：验证全量同步时缺失文档标记删除并清理 chunk。
  - `test_incremental_deleted_record_marks_document_deleted_and_clears_chunks`：验证增量删除记录处理。
  - `test_failed_job_archives_failure_samples`：验证失败样本归档。

- `tests/test_postgres_connector.py`
  - `test_postgres_connector_test_connection_rejects_missing_columns`：验证字段缺失时拒绝连接。
  - `test_source_service_wraps_postgres_validation_error`：验证数据源校验异常包装。

- `tests/test_retrieval_service.py`
  - `test_search_filters_low_score_results`：验证低分结果过滤。
  - `test_search_skips_deleted_documents`：验证已删除文档不参与检索。

- `tests/test_qa_service.py`
  - `test_qa_service_returns_insufficient_when_score_is_low`：验证证据不足时返回降级答复。

- `tests/test_sync_orchestrator.py`
  - `test_trigger_sync_rejects_duplicate_active_job`：验证重复触发互斥。
  - `test_process_next_job_marks_worker_failure`：验证 worker 异常时任务失败。
  - `test_recover_running_jobs_marks_them_failed`：验证异常退出后的运行中任务恢复失败态。

### 2.3 跳过项

- `tests/test_health.py`
  - 跳过原因：当前环境缺少 `fastapi`，`pytest.importorskip("fastapi")` 生效。
  - 影响范围：`/health` HTTP 层的分层健康检查响应未在本轮执行。

## 3. 执行结果

### 3.1 汇总

- 已执行并通过：31
- 跳过：1
- 失败：0

### 3.2 结论

- 本轮测试覆盖了二期核心主链路：仓储、同步任务状态机、Postgres 数据源、文档处理、检索、问答、归档与结构化日志。
- 端到端回归用例已覆盖“创建数据源 → 触发同步 → 检索 → 问答”的关键业务闭环。
- 当前代码在现有测试环境下回归通过，无新增失败项。

## 4. 未覆盖风险点说明

- `tests/test_health.py` 未执行，`/health` 的 FastAPI 路由与 `TestClient` HTTP 层行为仍待在安装 `fastapi` 的环境下补跑。
- 当前回归以单元测试和基于内存 / fake state 的集成为主，未连接真实 `PostgreSQL`、`Redis`、`MinIO`、真实 embedding provider 做联调验证。
- 端到端回归覆盖的是服务内部主链路，未覆盖实际 HTTP API 接口的请求鉴权、序列化/反序列化与部署环境配置差异。
- 未包含并发压力、长文本大批量同步、真实 pgvector 相似度性能等非功能性验证。

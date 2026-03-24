# 测试报告

## 1. 测试环境

- 仓库：`knowledge-indexer`
- Python：`3.13.5`
- pytest：`9.0.2`
- 执行目录：`/Users/wubo/.zenflow/worktrees/die-dai-you-hua-yi-qi-codex-0ebd`

## 2. 执行命令与结果

### 2.1 针对性回归

执行命令：

```bash
pytest -q tests/test_shared_capabilities.py tests/test_qa_service.py tests/test_rerank_service.py tests/test_internal_qa_api.py tests/test_internal_jobs_api.py tests/test_health_api.py tests/test_indexing_service.py
```

执行结果：

- `15 passed, 3 skipped in 0.33s`

覆盖重点：

- 共享配置与 `pipeline_engine` 解析
- 问答生成、证据不足兜底、LLM 降级
- rerank 正常/异常降级
- 任务取消与后台执行终止
- 健康检查与内部问答/任务 API

### 2.2 全量测试

执行命令：

```bash
pytest -q -rs
```

执行结果：

- `22 passed, 3 skipped in 0.22s`

跳过项：

- `tests/test_health_api.py`：缺少 `fastapi`
- `tests/test_internal_jobs_api.py`：缺少 `fastapi`
- `tests/test_internal_qa_api.py`：缺少 `fastapi`

## 3. 测试用例清单

### 3.1 正常流程

- `tests/test_document_processor.py::test_split_text_generates_multiple_chunks`
- `tests/test_indexing_service.py::test_full_sync_marks_missing_documents_deleted_and_clears_chunks`
- `tests/test_qa_service.py::test_qa_service_returns_generated_answer_with_reranked_citations`
- `tests/test_qa_service.py::test_qa_service_search_returns_rerank_metadata`
- `tests/test_rerank_service.py::test_rerank_service_reorders_items_when_provider_returns_ranked_ids`
- `tests/test_retrieval_service.py::test_acl_filter_only_returns_allowed_document`
- `tests/test_retrieval_service.py::test_search_filters_low_score_results`
- `tests/test_retrieval_service.py::test_search_skips_deleted_documents`
- `tests/test_shared_capabilities.py::test_settings_resolved_job_runner_mode_uses_sync_run_inline_compatibility`
- `tests/test_shared_capabilities.py::test_job_service_create_job_accepts_pipeline_engine`
- `tests/test_shared_capabilities.py::test_pipeline_engine_service_resolves_request_and_health_from_configuration`
- `tests/test_shared_capabilities.py::test_trigger_sync_records_builtin_flow_as_job_pipeline_engine`

### 3.2 异常与边界场景

- `tests/test_indexing_service.py::test_incremental_failure_does_not_advance_checkpoint`
- `tests/test_indexing_service.py::test_background_runner_cancels_running_job_without_checkpoint_or_touch_sync`
- `tests/test_job_service.py::test_request_cancel_marks_pending_job_cancelled`
- `tests/test_job_service.py::test_request_cancel_marks_running_job_cancelling_idempotently`
- `tests/test_job_service.py::test_request_cancel_completed_job_raises_conflict`
- `tests/test_qa_service.py::test_qa_service_returns_insufficient_when_score_is_low`
- `tests/test_qa_service.py::test_qa_service_falls_back_when_llm_is_disabled`
- `tests/test_qa_service.py::test_qa_service_falls_back_when_llm_call_fails`
- `tests/test_rerank_service.py::test_rerank_service_falls_back_to_original_order_when_provider_fails`
- `tests/test_rerank_service.py::test_rerank_service_falls_back_to_original_order_when_response_is_invalid`

### 3.3 因环境缺失被跳过

- `tests/test_health_api.py::test_health_endpoint_returns_runtime_capabilities`
- `tests/test_internal_jobs_api.py::test_cancel_job_endpoint_returns_cancelled_payload`
- `tests/test_internal_qa_api.py::test_ask_endpoint_returns_generated_answer_and_capabilities`

## 4. 结论

- 已验证本次迭代新增的核心单测链路可执行，问答生成/降级、rerank 降级、任务取消、`pipeline_engine` 暴露等关键能力在当前环境下通过。
- 全量可执行测试全部通过，未发现新增失败用例。

## 5. 未覆盖风险点

- 当前环境未安装 `fastapi`，3 个 API 层测试被跳过；HTTP 路由的最终联调结果仍需在完整依赖环境中补跑确认。
- 未执行集成级验证，例如真实 LLM / rerank provider / 外部 pipeline engine 接入后的端到端行为。
- 未覆盖并发取消、长耗时索引任务中途取消后的资源释放与恢复场景。
- 未覆盖生产配置差异，例如 Redis / Postgres / MinIO 等基础设施联动。

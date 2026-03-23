# 测试报告

## 1. 测试执行信息
- 执行命令：`pytest -q`
- 测试框架：`pytest 9.0.2`
- 执行时间：2026-03-23
- 执行结果：`3 passed in 0.11s`

## 2. 测试用例清单

### 2.1 正常流程
1. `tests/test_document_processor.py::test_split_text_generates_multiple_chunks`
   - 验证长文本在配置 `chunk_size=20`、`chunk_overlap=5` 时能够被切分为多个 chunk。
   - 断言 chunk 列表长度不少于 2、所有 chunk 非空、首尾 chunk 不相同。

2. `tests/test_retrieval_service.py::test_acl_filter_only_returns_allowed_document`
   - 构造公开文档与带角色 ACL 的私有文档。
   - 验证匿名检索结果不会返回私有文档，具备 `cs` 角色时可以检索到对应文档。

### 2.2 异常 / 边界场景
1. `tests/test_qa_service.py::test_qa_service_returns_insufficient_when_score_is_low`
   - 构造与问题语义不相关的文档内容。
   - 验证检索分数低于阈值时，问答服务返回 `INSUFFICIENT`，并给出“检索分数低于阈值”的兜底原因。

## 3. 执行结果
- 全量测试已执行完成。
- 当前仓库内测试共 3 条，全部通过。
- 本次验证覆盖了文本切分、ACL 检索过滤、问答证据不足兜底三个关键路径。

## 4. 未覆盖风险点
- `FastAPI` 路由层尚未做接口级测试，未验证 `/internal/search`、`/internal/ask`、`/internal/sources/*`、`/internal/jobs/*` 的请求编解码与状态码行为。
- `CocoIndex flow`、数据库连接、`Redis`、`MinIO` 相关基础设施尚未做集成测试，未验证真实依赖下的同步链路。
- 增量同步、任务失败重试、日志记录等运行时场景暂无自动化测试覆盖。
- 当前测试主要基于内存仓储实现，尚未覆盖持久化仓储的一致性与性能行为。

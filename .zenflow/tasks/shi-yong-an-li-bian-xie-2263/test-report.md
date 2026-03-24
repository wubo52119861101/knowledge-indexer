# 测试报告

## 1. 测试范围

本次仅验证“使用案例 / 使用手册”交付物在当前仓库中的可用性与一致性，重点覆盖：

- 已有自动化测试是否通过；
- 文档入口文件与依赖文件是否存在；
- `README.md` 到 `docs/use-cases.md`、`docs/usage.md` 的锚点跳转是否有效；
- 文档中声明的核心接口、鉴权方式与环境变量是否与代码实现一致。

## 2. 测试用例清单

### 2.1 正常流程

| 编号 | 测试项 | 命令 / 方法 | 预期 |
| --- | --- | --- | --- |
| TC-01 | 单元测试全量执行 | `pytest tests -q` | 全部通过 |
| TC-02 | 测试集收集 | `pytest tests --collect-only -q` | 可收集到现有测试用例 |
| TC-03 | 文档资源存在性校验 | `test -f .env.example`、`test -f docs/usage.md`、`test -f docs/use-cases.md` | 文件均存在 |
| TC-04 | README 文档锚点校验 | 提取 `README.md` 中的文档链接并检查目标锚点 | 所有锚点均存在 |
| TC-05 | 核心接口路径一致性校验 | 检查 `app/api/*.py` 路由定义与文档描述 | 路径一致 |
| TC-06 | 环境变量一致性校验 | 检查 `app/core/config.py` 与文档中的环境变量说明 | 配置项一致 |

### 2.2 异常 / 边界场景

| 编号 | 测试项 | 方法 | 结果判定 |
| --- | --- | --- | --- |
| TC-07 | 低分检索结果过滤 | 复用 `tests/test_retrieval_service.py::test_search_filters_low_score_results` | 通过说明文档中的分数阈值行为有测试覆盖 |
| TC-08 | 已删除文档不参与检索 | 复用 `tests/test_retrieval_service.py::test_search_skips_deleted_documents` | 通过说明文档中的删除态过滤有测试覆盖 |
| TC-09 | ACL 过滤只返回可见文档 | 复用 `tests/test_retrieval_service.py::test_acl_filter_only_returns_allowed_document` | 通过说明文档中的 ACL 描述与实现一致 |
| TC-10 | 证据不足时问答兜底 | 复用 `tests/test_qa_service.py::test_qa_service_returns_insufficient_when_score_is_low` | 通过说明文档中的“证据不足”场景有测试覆盖 |

## 3. 执行结果

### 3.1 自动化测试

执行命令：

```bash
pytest tests -q
```

执行结果：

```text
.......                                                                  [100%]
7 passed in 0.14s
```

补充收集结果：

```text
tests/test_document_processor.py::test_split_text_generates_multiple_chunks
tests/test_indexing_service.py::test_incremental_failure_does_not_advance_checkpoint
tests/test_indexing_service.py::test_full_sync_marks_missing_documents_deleted_and_clears_chunks
tests/test_qa_service.py::test_qa_service_returns_insufficient_when_score_is_low
tests/test_retrieval_service.py::test_acl_filter_only_returns_allowed_document
tests/test_retrieval_service.py::test_search_filters_low_score_results
tests/test_retrieval_service.py::test_search_skips_deleted_documents
```

结论：当前已有 7 个自动化测试全部通过，覆盖了文档中最关键的检索、问答兜底、ACL 过滤、分片处理与索引任务核心逻辑。

### 3.2 文档资源与入口检查

执行结果：

- `.env.example` 存在；
- `docs/usage.md` 存在；
- `docs/use-cases.md` 存在；
- `README.md` 中引用的 `docs/usage.md#reference-quick-nav`、`docs/use-cases.md#manual-quickstart`、`docs/use-cases.md#manual-sync` 均能在目标文档中找到对应锚点。

结论：文档入口链路完整，README 中的阅读路径可以正常跳转。

### 3.3 文档与代码一致性检查

静态核对结果如下：

- 文档声明的核心接口 `/internal/sources`、`/internal/jobs/{id}`、`/internal/search`、`/internal/ask`、`/health` 均能在 `app/api/` 路由定义中找到对应实现；
- 文档声明的鉴权头 `X-Internal-Token` 与 `verify_internal_token` 依赖一致；
- 文档中说明的 `INTERNAL_API_TOKEN`、`SYNC_RUN_INLINE`、`DATABASE_URL`、`REDIS_URL`、`MINIO_*` 均在 `app/core/config.py` 中有对应配置项；
- `README.md` 中关于当前实现范围与文档入口的描述，与 `docs/use-cases.md` / `docs/usage.md` 的职责分层一致。

结论：本次交付的使用手册与当前代码实现不存在明显冲突，核心路径、关键配置和入口说明一致。

## 4. 未覆盖的风险点

1. **未执行 HTTP 级联调冒烟**
   - 当前命令行环境缺少运行 `app.main` 所需的 `fastapi` 依赖，因而未直接重放文档中的 `curl` 示例；
   - 本次改为使用“已有自动化测试 + 静态路由 / 配置核对”的方式完成验证。

2. **未验证 Markdown 在外部平台的渲染表现**
   - 例如不同代码托管平台、知识库平台对锚点、表格、代码块的渲染差异；
   - 当前仅验证仓库内文档链接与锚点本身存在。

3. **未覆盖真实基础设施联调**
   - `DATABASE_URL`、`REDIS_URL`、`MINIO_*` 相关内容仍以占位说明为主；
   - 本次未启动 Docker 依赖，也未验证真实外部服务可达性。

4. **未覆盖人工可读性走查**
   - 本次验证重点是正确性和一致性；
   - 若需要进一步保证“像使用手册一样顺手”，仍建议由目标读者做一次通读体验。

## 5. 总结

本次“测试验证”步骤已完成：

- 自动化测试 `7/7` 通过；
- 文档入口文件、锚点跳转、接口路径与关键环境变量均完成校验；
- 当前可认为使用手册交付物与项目实现保持一致，可进入任务收尾。

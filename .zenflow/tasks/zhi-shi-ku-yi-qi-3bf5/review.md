## Code Review

**Verdict**: REQUEST CHANGES
**Confidence**: HIGH

### Summary
本次提交已经把 `knowledge-indexer` 的 FastAPI 骨架、索引链路和基础测试搭起来了，但当前实现里还有几处会直接影响一期可用性的正确性问题：容器镜像无法按当前打包配置稳定启动、增量同步在部分记录失败时会跳过失败数据、全量/重建同步不会清理已删除文档、搜索接口在无命中时仍会返回低相关结果。

### Findings

| Priority | 严重等级 | Issue | Location |
|----------|----------|-------|----------|
| P1 | 🔴 必须修复 | Docker 镜像使用 `pip install .` 安装时，只声明了 `app` 根包，`app.api`/`app.services` 等子包不会被打进分发包，容器启动后会在导入 `app.main` 时失败。 | `pyproject.toml:34`, `docker/Dockerfile:6` |
| P1 | 🔴 必须修复 | `run_job` 会吞掉单条记录异常并继续推进 checkpoint；只要后面还有成功记录，失败记录就可能被永久跳过，无法在下一次增量同步中重试。 | `app/services/indexing_service.py:54`, `app/services/indexing_service.py:82`, `app/services/indexing_service.py:86` |
| P1 | 🔴 必须修复 | 全量/重建同步只会 upsert 当前扫到的文档，没有对“源端已删除”的文档做失效/清理，导致陈旧知识会长期留在检索结果中。 | `app/services/indexing_service.py:45`, `app/services/indexing_service.py:59`, `app/repositories/document_repo.py:12` |
| P1 | 🔴 必须修复 | `/internal/search` 没有任何最小分数过滤，库里只要存在 chunk，就会返回 `top_k` 条结果；这与“无命中时返回空结果/明确提示”的一期要求不符。 | `app/services/retrieval_service.py:47`, `app/services/retrieval_service.py:63` |
| P2 | 🟡 建议优化 | 测试只覆盖了切分、ACL 和问答阈值，没有覆盖 `IndexingService` 的失败重试、checkpoint、全量删除回收等核心分支，以上问题目前很难被自动化测试拦住。 | `tests/test_document_processor.py:1`, `tests/test_retrieval_service.py:1`, `tests/test_qa_service.py:1` |

### Details

#### [P1] Docker 打包缺少子包，镜像启动会失败
**File:** `pyproject.toml:34`

`setuptools` 这里显式写成了 `packages = ["app"]`，只会把根包声明进分发元数据；而镜像构建里执行的是 `pip install --no-cache-dir .`，不是开发态的 editable install。这样做出来的 wheel / install 结果里不会包含 `app.api`、`app.core`、`app.services` 等子包，`uvicorn app.main:app` 在导入 `from app.api.health import router` 等语句时就会报 `ModuleNotFoundError`。

**Suggested fix:**
```toml
[tool.setuptools.packages.find]
include = ["app*"]
```

或者显式列出所有子包，但更推荐使用 `find` 自动发现，避免后续新增模块时再次漏包。

#### [P1] 部分记录失败时仍推进 checkpoint，会造成增量数据丢失
**File:** `app/services/indexing_service.py:54`

当前循环里任意单条记录异常都会被 `except Exception:` 吞掉，只做 `failed_count += 1`。但 `latest_checkpoint` 仍会在后续成功记录上继续前进，并在循环结束后无条件保存。这样一来，只要“失败记录后面还有成功记录”，checkpoint 就会越过失败数据；下一次增量拉取通常只取“大于 checkpoint”的数据，失败记录就再也拿不回来了。

**Suggested fix:**
```python
failed_records = []
max_checkpoint = checkpoint.checkpoint_value if checkpoint else None

for raw_record in raw_records:
    try:
        payload = connector.normalize(source, raw_record)
        ...
        max_checkpoint = max_checkpoint_value(max_checkpoint, payload.metadata.get("updated_at"))
    except Exception as exc:
        failed_records.append((raw_record, str(exc)))

if failed_records:
    return self.job_service.mark_failed(
        job,
        error_summary=f"{len(failed_records)} records failed",
        failed_count=len(failed_records),
    )

if max_checkpoint is not None:
    self.checkpoint_repo.save(source.id, "default", str(max_checkpoint))
```

关键点是：**不要在存在失败记录时推进全局 checkpoint**；同时把失败记录或失败摘要落下来，给后续重试留入口。

#### [P1] 全量/重建同步不会回收源端已删除文档
**File:** `app/services/indexing_service.py:45`

`full/rebuild` 分支当前只会对本次扫描到的记录做 `upsert`，但不会对“这次没有再出现的旧文档”做任何处理。举例来说，文件源里某个 Markdown 已经被删除，本次全量扫描不会再读到它；但仓储里旧 `Document` 和旧 `Chunk` 仍然存在，后续 `/internal/search` 依然能检索到这份已删除知识，索引状态和真实源数据不一致。

**Suggested fix:**
```python
seen_external_ids: set[str] = set()

for raw_record in raw_records:
    payload = connector.normalize(source, raw_record)
    seen_external_ids.add(payload.external_doc_id)
    ...

if job.mode in {SyncMode.FULL, SyncMode.REBUILD}:
    removed_docs = self.document_repo.mark_missing_as_deleted(source.id, seen_external_ids)
    for document in removed_docs:
        self.chunk_repo.replace_for_document(document.id, [])
```

即使一期仍是内存仓储，也应该把“全量结果 = 当前源数据快照”这个语义补完整；否则重建索引没有实际意义。

#### [P1] 搜索接口在无命中场景下仍会返回低相关内容
**File:** `app/services/retrieval_service.py:47`

当前实现对所有 chunk 计算完相似度后，直接按分数排序返回前 `top_k` 条，没有任何最小分数阈值。只要知识库里存在 chunk，搜索接口就几乎总会返回一些“最不像也得返回”的结果。这和需求里“查询无命中时，应返回空结果或明确提示，而不是返回无关内容”是冲突的。

**Suggested fix:**
```python
min_score = self.settings.search_score_threshold

...
score = cosine_similarity(query_embedding, chunk.embedding)
if score < min_score:
    continue
scored_items.append(...)
```

如果不想把 `Settings` 注入 `RetrievalService`，至少也要在 service 层或 API 层引入一个默认阈值，并补一个“无命中返回空数组”的测试。

### Recommendation
先修复以上 4 个 P1 问题，再进入测试验证步骤；其中建议优先处理打包配置和增量 checkpoint 逻辑，这两项会直接影响服务是否能部署以及同步结果是否可靠。

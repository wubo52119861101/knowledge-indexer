## Code Review

**Verdict**: REQUEST CHANGES
**Confidence**: HIGH

### Summary
本次迭代完成了问答生成链路、任务取消、后台执行器和 `pipeline_engine` 结构化出参，整体拆分清晰，取消状态机与降级路径也补了较完整的单测。未发现明显的 SQL 注入、越权或敏感信息直接泄露风险，但当前实现里有 2 个必须修复的问题：`pipeline_engine` 会被配置值“伪装”为 external，以及新的 LLM/rerank 出站 HTTP 调用会在 FastAPI 的异步请求路径里阻塞事件循环。

### Findings

| Priority | Issue | Location |
|----------|-------|----------|
| P1 / 🔴 | `/health`、`/internal/ask`、`/internal/search` 的 `pipeline_engine` 仅根据配置返回；只要设置 `PIPELINE_ENGINE_TYPE=external`，即使实际仍走内置 `QaService` / `RetrievalService`，接口也会宣称自己使用了 external，引入“真实执行来源”语义错误。 | app/services/pipeline_engine_service.py:18 |
| P1 / 🔴 | `AnswerGenerator` 和 `RerankService` 在异步 HTTP 路由内同步执行 `httpx.Client.post(...)`；LLM/rerank 一旦变慢或超时，会直接阻塞事件循环，拖慢同 worker 的其他请求。 | app/services/answer_generator.py:46 |
| P2 / 🟡 | 新增测试把 `pipeline_engine` 语义固化成“按配置返回 external”，会把上面的错误行为长期保留下来，后续修复时也更容易被误判为回归。 | tests/test_shared_capabilities.py:41 |

### Details

#### [P1] `pipeline_engine` 不是“真实执行来源”
**File:** `app/services/pipeline_engine_service.py:18`

`resolve_for_request()` / `resolve_for_health()` 只检查 `PIPELINE_ENGINE_TYPE` 配置，就直接返回 `external`。但当前 ask/search 真实执行链路仍是内置的 `RetrievalService` + `QaService`，并没有任何 external executor/adaptor 参与；也就是说，只改环境变量，不改执行分支，接口出参就会“变身”为 external。这和需求里“准确反映当前实际使用的执行引擎”是相反的，会误导接入方做错误的联调判断。

**Suggested fix:**
```python
# 不要由配置直接决定 request/health 的执行来源；
# 由真正的执行分支把 source 传给 resolver。
def resolve_for_request(self, scene: str, executed_by: Literal["builtin", "external"], name: str) -> PipelineEngineInfo:
    return PipelineEngineInfo(
        type=PipelineEngineType.EXTERNAL if executed_by == "external" else PipelineEngineType.BUILTIN,
        name=name,
        scene=scene,
    )
```

在真正接入 external 编排之前，`/health`、`/internal/ask`、`/internal/search` 应继续返回 builtin；同时把 `tests/test_shared_capabilities.py` 的断言改成基于“实际执行分支”而不是“配置值”。

#### [P1] 同步 HTTP 客户端阻塞异步请求路径
**File:** `app/services/answer_generator.py:46`

`internal_ask` / `internal_search` 是 `async def` 路由，但 `QaService` 内部会同步调用 `AnswerGenerator.generate()` / `RerankService.rerank()`，而这两个方法又使用了阻塞式 `httpx.Client`。这样每次 LLM/rerank 出站请求都会占住事件循环直到对端返回或超时（默认 8s / 3s），在压测或对端抖动时会明显拉低吞吐并放大尾延迟。

**Suggested fix:**
```python
async def generate(...):
    async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
        response = await client.post(...)

async def rerank(...):
    async with httpx.AsyncClient(timeout=self.settings.rerank_timeout_seconds) as client:
        response = await client.post(...)
```

把 `QaService.ask/search` 和对应路由一并改成异步；如果短期不想改接口签名，至少把这两段阻塞 I/O 包进线程池，避免直接卡住事件循环。

### Recommendation
先修复 `pipeline_engine` 的真实语义和 LLM/rerank 的异步 I/O 问题，再更新对应测试。完成这两项后，我认为这批改动就可以进入下一轮测试验证。

## Code Review

**Verdict**: REQUEST CHANGES
**Confidence**: HIGH

### Summary

本次改动完成了 `README.md`、`docs/use-cases.md`、`docs/usage.md` 的文档分层，也补充了较完整的启动、同步、FAQ 和参考说明。
但当前交付仍有 2 个会直接影响使用手册可用性的 P1 问题：一个是鉴权示例调用了错误的 HTTP 方法，复制即失败；另一个是主使用手册缺少承诺的“检索 / 问答 / ACL 联调”三类场景化案例，导致核心主流程在主手册里断档。

### Findings

| Priority | Severity | Dimension | Issue | Location |
|----------|----------|-----------|-------|----------|
| P1 | 🔴 必须修复 | 正确性 | 鉴权示例对 `/internal/search` 使用了 `GET`，而该路由实际只支持 `POST`，用户按文档执行会直接得到 `405 Method Not Allowed`。 | `docs/usage.md:166`, `app/api/internal_search.py:13` |
| P1 | 🔴 必须修复 | 正确性 | 主使用手册明确承诺包含“检索验证 / 问答验证 / ACL 联调”3 个典型案例，但正文在同步章节后直接进入 FAQ，导致主手册缺少这 3 条核心主流程。 | `docs/use-cases.md:43`, `docs/use-cases.md:630`, `.zenflow/tasks/shi-yong-an-li-bian-xie-2263/spec.md:49` |
| P2 | 🟡 建议优化 | 可维护性 | 交付给最终读者的 `docs/use-cases.md` 仍保留“统一案例模板 / 编写规则 / 后续章节占位”等作者态内容，和“主使用手册”的定位冲突，也会增加读者理解噪音。 | `docs/use-cases.md:70`, `docs/use-cases.md:96`, `docs/use-cases.md:113` |

### Details

#### [P1] 鉴权示例使用了错误的 HTTP 方法
**File:** `docs/usage.md:166`

当前“鉴权说明”章节给出的唯一示例是：

```bash
curl -H 'X-Internal-Token: your-token' http://127.0.0.1:8000/internal/search
```

但 `/internal/search` 在实现里是 `POST /internal/search`，且需要请求体。也就是说，用户按这段命令验证鉴权时，会先撞上方法错误，而不是验证到鉴权逻辑本身。这会让“如何确认 Token 生效”这一步变成误导。

**Suggested fix:**
```markdown
示例 1：继续使用 `/internal/search`，但改成真实可执行的 `POST` 请求；

```bash
curl -X POST 'http://127.0.0.1:8000/internal/search' \
  -H 'Content-Type: application/json' \
  -H 'X-Internal-Token: your-token' \
  -d '{"query":"test"}'
```

或示例 2：改用受保护的 `GET` 路由，例如 `/internal/jobs/{job_id}` / `/internal/sources/{source_id}`。
```

#### [P1] 主使用手册缺少承诺的检索 / 问答 / ACL 场景案例
**File:** `docs/use-cases.md:43`

文档在“手册信息架构”里明确写了 6 个典型使用案例，其中案例 4~6 分别是“执行检索验证 / 执行问答验证 / 带 ACL 上下文完成联调”；技术方案也把 `docs/use-cases.md` 定义为主使用手册。

但当前正文在“7. 数据源接入与同步案例”结束后，直接跳到了“8. 异常边界、限制与 FAQ”，并没有把这 3 个场景化案例真正写进主手册。结果是：

- `README.md` 把 `docs/use-cases.md` 作为场景化入口；
- 读者在主手册里只能完成“启动 + 同步”；
- 真正的“检索 / 问答 / ACL”内容只能去 `docs/usage.md` 查参考说明，破坏了“主手册跑主流程、参考文档查字段”的职责分层。

这不是单纯的排版问题，而是交付范围和主路径文档结构没有闭环。

**Suggested fix:**
```markdown
在 `docs/use-cases.md` 的同步章节之后、FAQ 之前补齐 3 个场景化章节，并保持与前文一致的“场景目标 / 适用角色 / 前置条件 / 操作步骤 / 预期结果 / 注意事项”结构：

1. 执行检索验证
2. 执行问答验证（命中充分 + 证据不足）
3. 带 ACL 上下文联调

字段级解释继续链接到 `docs/usage.md`，但主流程必须在主手册里可顺着读完。
```

### Recommendation

先修复上面两个 P1 问题，再进入下一步测试验证会更稳妥；P2 可以作为本轮顺手清理项一并处理。
本次评审未发现新增的安全或性能风险，但文档改动目前缺少自动校验，后续建议至少补一个 Markdown 链接/示例巡检流程，避免类似方法错误再次进入主分支。

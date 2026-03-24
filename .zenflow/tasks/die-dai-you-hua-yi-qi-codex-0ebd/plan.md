# 需求开发

## Configuration
- **Artifacts Path**: {@artifacts_path} → `.zenflow/tasks/{task_id}`

---

## Workflow Steps

### [x] Step: 需求分析
<!-- chat-id: 9d7a7ccc-d532-470a-90a7-bf8d6fb264fa -->
仔细阅读需求描述，分析业务背景、目标用户、核心功能点和边界条件。
输出到 `{@artifacts_path}/requirements.md`，包含：
- 需求背景与目标
- 功能清单（主流程 + 边界场景）
- 验收标准
- 疑问点（如有）

### [x] Step: 技术方案
<!-- chat-id: 120c0906-45bb-4499-94cf-1194ff3d04c1 -->
基于需求分析，编写详细技术方案。
输出到 `{@artifacts_path}/spec.md`，包含：
- 整体架构设计
- 接口 / 数据结构定义
- 核心逻辑说明
- 依赖与风险点
- 工作量估算

### [x] Step: 任务拆分
<!-- chat-id: b8b1e183-5254-41a3-8e14-d7f6a8d3b502 -->
基于技术方案，将开发工作拆解为可执行的子任务。
输出到 `{@artifacts_path}/tasks.md`，包含：
- 子任务清单（每个任务明确：名称 / 负责模块 / 预估工作量 / 依赖关系）
- 任务优先级排序
- 并行 vs 串行执行建议
- 每个子任务的完成标准（DoD）

**重要**：任务拆分完成后，必须将拆分出的子任务按优先级顺序写入当前 `plan.md`，插入在本步骤与"Code Review"步骤之间。格式为：
```
### [ ] Step: {子任务编号} {子任务名称}
{子任务描述，包含关键实现要点}
```
这样 To-do 面板会自动展示所有待执行的子任务。

### [x] Step: T1 共享基础能力与配置扩展
<!-- chat-id: 5f3d925a-e5b4-46dc-9db3-51674a4b17f9 -->
统一扩展 `Settings`、`PipelineEngineInfo`、`JobStatus/IndexJob` 与 `ServiceContainer` 注入点，建立 LLM、rerank、pipeline engine、job runner 的默认配置和共享数据结构，保证兼容现有接口与 `SYNC_RUN_INLINE`。

### [ ] Step: T2 问答链路编排与生成能力
在 `qa_service` 中落地“检索 → 证据判定 → 可选 rerank → 生成/兜底”，新增 `answer_generator`、`rerank_service`，并扩展 `/internal/ask`、`/internal/search` 响应字段。

### [ ] Step: T3 任务取消接口与执行器治理
新增 `/internal/jobs/{job_id}/cancel`，实现 `PENDING/RUNNING` 的取消状态流转、后台执行模式和 `IndexingService` 检查点终止能力，保证幂等与兼容。

### [ ] Step: T4 pipeline_engine 对外可观测化
新增 `pipeline_engine` 解析服务，统一 `/health`、`/internal/ask`、`/internal/search`、`/internal/jobs/{id}` 的真实执行来源返回，并记录到任务对象。

### [ ] Step: T5 文档与实现侧单测补齐
补齐问答降级、rerank 降级、取消任务、健康检查等关键单测与文档说明，为后续 Code Review 和测试验证提供输入。

### [ ] Step: Code Review
<!-- agent: codex-gpt-5-2-codex -->
对编码实现进行代码审查，检查以下维度并输出到 `{@artifacts_path}/review.md`：
- 正确性：逻辑是否符合需求和技术方案
- 安全性：有无 SQL 注入、越权、敏感信息泄露等风险
- 性能：有无明显的性能瓶颈或资源浪费
- 可维护性：命名、结构、注释是否清晰
- 测试覆盖：关键路径是否有测试

如有问题，标注严重等级（🔴 必须修复 / 🟡 建议优化 / 🔵 可选）

### [ ] Step: 测试验证
编写并执行测试，输出测试报告到 `{@artifacts_path}/test-report.md`，包含：
- 测试用例清单（正常流程 + 异常场景）
- 执行结果
- 未覆盖的风险点说明

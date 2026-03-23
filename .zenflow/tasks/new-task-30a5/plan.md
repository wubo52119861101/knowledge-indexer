# 需求开发

## Configuration
- **Artifacts Path**: {@artifacts_path} → `.zenflow/tasks/{task_id}`

---

## Workflow Steps

### [x] Step: 需求分析
<!-- chat-id: bb0b12b1-094d-4c34-9ca3-446e401e65ee -->
仔细阅读需求描述，分析业务背景、目标用户、核心功能点和边界条件。
输出到 `{@artifacts_path}/requirements.md`，包含：
- 需求背景与目标
- 功能清单（主流程 + 边界场景）
- 验收标准
- 疑问点（如有）

### [x] Step: 技术方案
<!-- chat-id: 830d6e29-2358-44b6-a48e-1afb3eb2d8eb -->
基于需求分析，编写详细技术方案。
输出到 `{@artifacts_path}/spec.md`，包含：
- 整体架构设计
- 接口 / 数据结构定义
- 核心逻辑说明
- 依赖与风险点
- 工作量估算

### [x] Step: 任务拆分
<!-- chat-id: 9bb875c7-c61e-41b3-9a7c-7598d7e10ebc -->
基于技术方案，将开发工作拆解为可执行的子任务。
输出到 `{@artifacts_path}/tasks.md`，包含：
- 子任务清单（每个任务明确：名称 / 负责模块 / 预估工作量 / 依赖关系）
- 任务优先级排序
- 并行 vs 串行执行建议
- 每个子任务的完成标准（DoD）

### [ ] Step: Code Review
<!-- chat-id: e5524b57-3a8b-4439-9c00-754d668b0b03 -->
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

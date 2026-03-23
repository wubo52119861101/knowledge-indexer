# 需求开发

## Configuration
- **Artifacts Path**: {@artifacts_path} → `.zenflow/tasks/{task_id}`

---

## Workflow Steps

### [x] Step: 需求分析
<!-- chat-id: 41f15516-fc5a-4581-a434-8fb47ce72d79 -->
仔细阅读需求描述，分析业务背景、目标用户、核心功能点和边界条件。
输出到 `{@artifacts_path}/requirements.md`，包含：
- 需求背景与目标
- 功能清单（主流程 + 边界场景）
- 验收标准
- 疑问点（如有）

### [x] Step: 技术方案
<!-- chat-id: 565868f0-a8b1-4469-b988-a10f6506a1cc -->
基于需求分析，编写详细技术方案。
输出到 `{@artifacts_path}/spec.md`，包含：
- 整体架构设计
- 接口 / 数据结构定义
- 核心逻辑说明
- 依赖与风险点
- 工作量估算

### [x] Step: 编码实现
<!-- chat-id: 55060d31-78ed-427b-a0b8-63f9d100ebc7 -->
<!-- agent: codex-gpt-5-2-codex -->
按照技术方案进行编码实现：
- 严格遵循项目已有代码风格
- 关键逻辑添加必要注释
- 同步编写单元测试（如适用）
- 实现完成后输出变更文件列表到 `{@artifacts_path}/changes.md`

### [x] Step: Code Review
<!-- chat-id: 53b63963-6a58-48ce-849e-cfaf76f8aa90 -->
<!-- agent: codex-gpt-5-2-codex -->
对编码实现进行代码审查，检查以下维度并输出到 `{@artifacts_path}/review.md`：
- 正确性：逻辑是否符合需求和技术方案
- 安全性：有无 SQL 注入、越权、敏感信息泄露等风险
- 性能：有无明显的性能瓶颈或资源浪费
- 可维护性：命名、结构、注释是否清晰
- 测试覆盖：关键路径是否有测试

如有问题，标注严重等级（🔴 必须修复 / 🟡 建议优化 / 🔵 可选）

### [x] Step: 测试验证
<!-- chat-id: 0ad34242-941b-4143-9ac7-6aa36d6e5ab9 -->
编写并执行测试，输出测试报告到 `{@artifacts_path}/test-report.md`，包含：
- 测试用例清单（正常流程 + 异常场景）
- 执行结果
- 未覆盖的风险点说明

### [x] Step: 补充项目使用文档
基于当前代码实现补充项目使用文档，覆盖以下内容：
- 本地启动方式
- Docker Compose 启动方式
- 环境变量说明
- 内部接口调用示例
- 数据源配置与同步脚本使用方式
- 当前实现边界与注意事项

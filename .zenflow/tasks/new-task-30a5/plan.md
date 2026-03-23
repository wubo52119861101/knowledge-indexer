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

### [x] Step: T1 持久化仓储底座落地
<!-- chat-id: 1eef350e-6db9-4927-aca9-6c5054503653 -->
将当前内存仓储替换为 PostgreSQL + pgvector 实现：
- 补齐表结构（kb_sources / kb_sync_jobs / kb_sync_checkpoints / kb_documents / kb_chunks）、索引和初始化脚本
- 实现 SourceRepository、JobRepository、CheckpointRepository、DocumentRepository、ChunkRepository 的 PostgreSQL 版本
- 改造 `app/core/container.py`，支持按配置切换 inmemory / postgres 仓储
- 基础 CRUD 与 upsert 行为有单元测试覆盖

### [ ] Step: T2 异步同步任务与状态机实现
引入 Redis 队列 / worker、任务状态流转、互斥控制：
- 实现 SyncOrchestrator，支持创建任务 -> 入队 -> worker 执行 -> 持久化状态
- 任务状态覆盖 PENDING / RUNNING / SUCCEEDED / FAILED / CANCELLED
- 支持查询任务进度、处理数量、失败摘要、失败阶段
- 对重复触发、任务失败、worker 异常退出有处理逻辑

### [ ] Step: T3 postgres 数据源接入生产化
完善 PostgresConnector，使其从占位变为正式可用：
- 连接信息校验、字段映射校验和敏感配置脱敏
- 支持全量与增量同步，增量游标通过 checkpoint 持续推进
- 支持删除标记、ACL 字段、metadata 字段映射到统一文档结构
- 至少有一份联调样例可用于回归

### [ ] Step: T4 检索与问答链路增强
接入真实 embedding，改造检索链路：
- 向量从 HashEmbeddingService 迁移到真实 embedding provider
- 数据读取从内存遍历迁移为 PostgreSQL + pgvector 检索
- 过滤顺序调整为 source/doc_type 粗过滤 -> 向量召回 -> ACL 过滤 -> rerank（可选） -> top_k
- 检索 / 问答关键路径有单测或集成测试

### [ ] Step: T5 MinIO 归档与可观测增强
增加归档、健康检查、结构化日志：
- 同步任务支持原文快照和失败样本归档到 MinIO
- `/health` 输出数据库、Redis、MinIO、embedding、pipeline engine 的状态分层信息
- 同步任务日志具备 job_id、source_id、mode、status、duration_ms 等结构化字段

### [ ] Step: T6 联调文档与迁移说明补齐
补齐配置说明、迁移步骤、接入示例：
- docs/usage.md 与 README.md 覆盖二期新增配置、接口变化、运行方式
- 提供 Java 调用方可参考的接入 / 联调示例
- 明确一期迁移到二期的环境依赖、数据初始化、回滚注意事项

### [ ] Step: T7 测试与回归验证
覆盖主流程与异常场景的测试：
- 单测覆盖 Repository、同步任务、connector、检索 / 问答等核心模块
- 至少完成一次端到端验证：创建数据源 -> 触发同步 -> 查询任务 -> 检索 / 问答
- 未覆盖风险点有显式记录

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

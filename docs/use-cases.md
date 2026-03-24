# knowledge-indexer 使用案例手册

<a id="manual-quickstart"></a>

本文档是 `knowledge-indexer` 的场景化使用手册，面向首次接触项目的研发、测试和联调同学。

阅读目标不是“记住全部接口字段”，而是按真实使用路径理解：
- 这个项目适合解决什么问题；
- 在什么前提下可以开始联调；
- 每一步应该如何操作；
- 操作成功后应该看到什么结果；
- 当前版本有哪些边界与限制。

## 1. 文档定位

### 1.1 适合谁看
- 首次接触 `knowledge-indexer` 的研发同学；
- 需要跑通索引、检索、问答链路的测试与联调同学；
- 需要快速判断项目能力边界的项目干系人。

### 1.2 这份文档解决什么问题
- 用案例方式替代纯接口堆砌，降低首次上手成本；
- 把“前置条件 → 操作步骤 → 预期结果 → 注意事项”串成完整路径；
- 将常见误解与一期限制前置说明，减少联调偏差。

### 1.3 与其他文档的分工

| 文档 | 角色 | 主要职责 |
| --- | --- | --- |
| `README.md` | 项目入口 | 说明项目定位、快速启动入口、文档地图 |
| `docs/use-cases.md` | 使用手册 | 提供场景化案例与标准操作路径 |
| `docs/usage.md` | 参考文档 | 提供接口、字段、配置和限制的详细说明 |

建议阅读顺序：`README.md` → `docs/use-cases.md` → `docs/usage.md`。

## 2. 手册信息架构

本手册后续章节按“先建立认知，再跑通主流程，最后补足边界”的顺序组织。

### 2.1 项目概览与快速上手
说明项目定位、目标用户、当前能力边界、环境准备、启动方式和基础验证路径。

### 2.2 典型使用案例
围绕以下主流程案例展开：
1. 本地启动并确认服务可用；
2. 创建文件数据源并完成全量同步；
3. 创建 API 数据源并完成增量同步；
4. 执行检索验证；
5. 执行问答验证；
6. 带 ACL 上下文完成联调验证。

### 2.3 标准操作流程
将跨案例都会重复出现的共性步骤沉淀为统一流程：
- 创建数据源；
- 触发同步；
- 查询任务状态；
- 发起检索；
- 发起问答；
- 核对 ACL 过滤结果。

### 2.4 异常边界与 FAQ
按“现象 → 原因 → 结论 / 建议”的写法整理：
- 鉴权失败；
- `SYNC_RUN_INLINE=false` 的任务行为；
- 服务重启后数据丢失；
- `postgres` 数据源仅占位；
- 健康检查仅代表配置级状态；
- 问答证据不足兜底。

## 3. 统一案例模板

后续所有案例统一按以下模板编写，避免章节风格和信息粒度不一致。

```markdown
## 案例 X：{案例标题}

### 场景目标
说明本案例要完成的验证目标。

### 适用角色
说明谁最需要看这个案例，例如接入开发、测试、联调同学。

### 前置条件
列出运行环境、鉴权信息、准备数据或前置接口状态。

### 操作步骤
按顺序给出命令、接口、关键参数和执行动作。

### 预期结果
描述成功时应看到的 HTTP 状态、关键返回字段和结果判断标准。

### 常见问题 / 注意事项
补充容易踩坑的点、一期限制或和预期不一致时的排查建议。
```

## 4. 编写规则

### 4.1 内容边界
- 只描述当前仓库已实现能力；
- 不把 `postgres` 真同步、持久化仓储、后台队列等预留能力写成已可用；
- 成功路径和失败路径都要以当前代码行为为准。

### 4.2 表达规则
- 优先写“怎么做”和“看到什么算成功”；
- 每个案例至少给出一个成功判断字段；
- 对限制项使用明确措辞，例如“当前未实现”“仅占位”“仅用于本地验证”。

### 4.3 与参考文档的衔接规则
- 在案例中只保留必要字段解释，避免重复粘贴完整字段表；
- 详细请求体、返回结构、环境变量说明统一链接到 `docs/usage.md`；
- `README.md` 只保留入口信息，不承载完整案例正文。

## 5. 后续章节占位

以下章节为后续子任务直接填充的目标位置：
- `T02`：项目概览与快速上手；
- `T03`：数据源接入与同步案例；
- `T04`：检索、问答与 ACL 联调案例；
- `T05`：异常边界、限制与 FAQ；
- `T06`：整体一致性校验与入口联动。

## 6. 项目概览与快速上手

本章面向第一次接触 `knowledge-indexer` 的同学，目标不是一次性掌握全部接口细节，而是在 10 分钟内建立下面三件事的清晰认知：
- 这个项目负责什么，不负责什么；
- 本地最少需要准备什么环境；
- 服务启动后，先看哪些接口可以判断链路已跑通。

### 6.1 先建立正确预期

#### 6.1.1 这个项目解决什么问题

`knowledge-indexer` 是企业知识库一期的索引与检索底座，负责把外部知识内容接入、切分、索引，并通过内部接口提供检索和问答能力。

可以把它理解为“知识处理引擎”，而不是一个完整的业务系统。当前服务已经覆盖：
- 数据源管理：创建 `file`、`api`、`postgres` 类型的数据源；
- 同步任务：触发全量或增量同步，生成任务记录；
- 检索能力：通过 `/internal/search` 返回命中的知识片段；
- 问答能力：通过 `/internal/ask` 基于检索结果生成回答；
- 健康检查：通过 `/health` 查看应用与依赖配置状态。

#### 6.1.2 这个项目不负责什么

首次联调时最容易出现的误解，是把 `knowledge-indexer` 当成“带前台页面的知识库系统”或“已经接好完整基础设施的生产服务”。当前版本并不是这样。

请先记住以下边界：
- 它只提供内部 HTTP 接口，不提供管理后台或用户界面；
- 用户身份、统一鉴权和业务权限上下文由外部 Java 后端传入；
- 默认仓储是内存实现，服务重启后数据会丢失；
- 当前问答是基于检索结果的轻量拼接，不是正式的大模型问答系统；
- `postgres` 数据源类型当前仅作为能力占位，不能完成真实同步。

#### 6.1.3 谁最适合先看这一章

这一章优先推荐以下角色阅读：
- 接入开发：需要快速判断服务提供了哪些内部接口；
- 测试同学：需要先把本地服务跑起来，再验证主流程；
- 联调同学：需要知道哪些返回算“服务已正常启动”；
- 项目干系人：需要快速确认一期能力边界，而不是直接深入代码。

### 6.2 环境准备

#### 6.2.1 最低运行要求

本地快速体验只需要下面这些条件：
- Python `3.11` 或 `3.12`；
- 可用的虚拟环境工具，例如 `venv`；
- 命令行工具 `curl`，便于直接验证 HTTP 接口；
- 可选：`Docker` 与 `Docker Compose`，用于后续基础设施演示，但不是本章必需条件。

如果你的目标只是“先确认服务能启动、接口能返回”，本章不要求你先准备 PostgreSQL、Redis 或 MinIO。

#### 6.2.2 建议的环境变量策略

项目根目录已经提供 `.env.example`。第一次启动建议直接复制一份默认配置，再按需要微调：

```bash
cp .env.example .env
```

首次体验时重点关注这两个变量：

| 变量 | 建议 | 原因 |
| --- | --- | --- |
| `INTERNAL_API_TOKEN` | 可先留空 | 留空时 `/internal/*` 不校验 `X-Internal-Token`，方便先跑通链路 |
| `SYNC_RUN_INLINE` | 保持默认 `true` | 后续触发同步时会直接执行，不需要额外后台任务消费者 |

如果你把 `INTERNAL_API_TOKEN` 改成非空值，后续访问 `/internal/*` 时就必须显式携带 `X-Internal-Token` 请求头；但 `/health` 和 `/` 依然可以直接访问。

### 6.3 快速上手：本地启动并确认服务可用

这一节遵循统一案例模板，用最短路径把服务跑起来，并确认“服务可访问、配置已加载、基础接口正常响应”。

#### 场景目标

完成一次本地启动，并通过根路径 `/` 和健康检查 `/health` 验证应用已可响应请求。

#### 适用角色

- 第一次拉起项目的研发同学；
- 需要准备联调环境的测试同学；
- 想先判断项目是否能正常运行的维护者。

#### 前置条件

- 已在本机获取项目代码；
- 当前工作目录位于仓库根目录；
- 本机 Python 版本满足 `>=3.11`；
- 尚未安装依赖也没有关系，本节会从零开始。

#### 操作步骤

1. 创建虚拟环境并激活：

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

2. 安装项目依赖：

   ```bash
   pip install -e .[dev]
   ```

   如果你只想运行服务、不执行测试，也可以使用 `pip install -e .`。

3. 复制环境变量模板：

   ```bash
   cp .env.example .env
   ```

   第一次体验建议保持 `INTERNAL_API_TOKEN=` 为空，这样后续访问内部接口时不需要额外带鉴权头。

4. 启动 FastAPI 服务：

   ```bash
   uvicorn app.main:app --reload
   ```

   默认会监听 `http://127.0.0.1:8000`。

5. 在另一个终端验证根路径：

   ```bash
   curl http://127.0.0.1:8000/
   ```

   预期返回类似：

   ```json
   {
     "name": "knowledge-indexer",
     "message": "knowledge-indexer is running"
   }
   ```

6. 再验证健康检查接口：

   ```bash
   curl http://127.0.0.1:8000/health
   ```

   预期返回为统一响应结构，其中 `code=0` 代表接口成功；`data.app.status=ok` 代表应用本身已启动；`data.model.detail` 会提示当前使用的是开发期占位实现 `HashEmbeddingService`。

#### 预期结果

完成以上步骤后，可以按下面标准判断“快速上手成功”：
- `uvicorn` 进程启动后无导入错误或配置加载错误；
- 访问 `http://127.0.0.1:8000/` 能拿到 `knowledge-indexer is running`；
- 访问 `http://127.0.0.1:8000/health` 返回 `code: 0`；
- `health.data.app.env` 能反映当前 `.env` 中的 `APP_ENV` 配置；
- 即使数据库、Redis、MinIO 未真实可用，应用本身仍可以在本地启动并返回健康检查结果。

#### 常见问题 / 注意事项

- 如果 `python -m venv .venv` 失败，通常是本机 Python 版本不符合要求或系统未安装 `venv` 组件；
- 如果 `pip install -e .[dev]` 失败，先确认是否在仓库根目录执行，并检查 Python 版本；
- `/health` 更偏“应用与配置状态检查”，不是“所有依赖都能真实读写”的强保证；
- 当 `INTERNAL_API_TOKEN` 留空时，后续 `docs/use-cases.md` 中的内部接口案例可以直接调用；
- 当 `INTERNAL_API_TOKEN` 配置为非空时，后续所有 `/internal/*` 请求都要带 `X-Internal-Token`，否则会返回 `401 invalid internal token`。

### 6.4 跑通后的下一步建议

如果你已经完成本章，说明项目入口和本地启动路径已经打通。接下来建议按下面顺序继续阅读：
- 想继续验证“数据是怎么进来的”，看后续数据源接入与同步案例；
- 想先核对接口字段、请求体和环境变量，查阅 `docs/usage.md`；
- 想快速理解完整链路，优先关注“创建数据源 → 触发同步 → 查询任务 → 检索 / 问答”这条主路径。

<a id="manual-sync"></a>

## 7. 数据源接入与同步案例

本章聚焦“知识是怎么进入系统的”。你只要顺着下面 4 个案例操作，就能理解一期版本最核心的接入链路：
- 先创建数据源，让系统知道内容从哪里来；
- 再触发同步任务，把原始内容加工为可检索的文档和切片；
- 最后查询任务结果，判断本次同步到底有没有真正执行成功。

开始前先记住两个容易混淆的事实：
- 创建数据源只会保存配置，不会自动开始索引；
- `/internal/sources/{source_id}/sync` 一定会先创建任务，但任务是否立刻执行，取决于 `SYNC_RUN_INLINE`。

### 7.1 案例一：创建文件数据源并执行全量同步

#### 场景目标

通过一个本地目录完成“文件接入 → 全量同步 → 任务确认”整条路径，建立对 `file` 数据源的直观认知。

#### 适用角色

- 本地验证索引链路的研发同学；
- 需要准备回归样例文档的测试同学；
- 想先避开外部依赖、快速跑通同步流程的联调同学。

#### 前置条件

- 已按第 6 章完成服务启动；
- 知道当前服务地址，例如 `http://127.0.0.1:8000`；
- 如果 `.env` 中配置了 `INTERNAL_API_TOKEN`，后续请求需携带 `X-Internal-Token`；
- 当前示例假设 `SYNC_RUN_INLINE=true`，这样同步请求发出后会直接在当前进程内执行。

#### 操作步骤

1. 准备一个本地示例目录。为了不污染仓库，建议直接用 `/tmp`：

   ```bash
   export DOC_ROOT=/tmp/knowledge-indexer-demo-docs
   mkdir -p "$DOC_ROOT/policies"

   cat > "$DOC_ROOT/policies/leave.md" <<'EOF'
   请假制度

   员工请假需提前在系统中提交申请，并由直属主管审批。
   EOF

   cat > "$DOC_ROOT/security.txt" <<'EOF'
   办公安全要求：离开工位前请锁屏，敏感资料不要明文外发。
   EOF
   ```

2. 创建 `file` 数据源：

   ```bash
   curl -X POST 'http://127.0.0.1:8000/internal/sources' \
     -H 'Content-Type: application/json' \
     -H 'X-Internal-Token: your-token' \
     -d '{
       "name": "本地示例文档目录",
       "type": "file",
       "config": {
         "root_path": "/tmp/knowledge-indexer-demo-docs",
         "file_patterns": ["**/*.md", "**/*.txt"]
       },
       "sync_mode": "incremental",
       "enabled": true
     }'
   ```

   如果你的 `INTERNAL_API_TOKEN` 为空，可以删除 `X-Internal-Token` 请求头。

3. 从响应中记录 `data.id`，后文记为 `SOURCE_ID`。成功响应会类似：

   ```json
   {
     "code": 0,
     "message": "ok",
     "data": {
       "id": "src_1234567890ab",
       "name": "本地示例文档目录",
       "type": "file",
       "sync_mode": "incremental",
       "enabled": true,
       "last_sync_at": null
     }
   }
   ```

4. 触发一次全量同步：

   ```bash
   curl -X POST 'http://127.0.0.1:8000/internal/sources/SOURCE_ID/sync' \
     -H 'Content-Type: application/json' \
     -H 'X-Internal-Token: your-token' \
     -d '{
       "mode": "full",
       "operator": "manual"
     }'
   ```

5. 从响应中记录 `data.job_id`，后文记为 `JOB_ID`。如果当前是默认的 `SYNC_RUN_INLINE=true`，这里通常会直接看到：

   ```json
   {
     "code": 0,
     "message": "ok",
     "data": {
       "job_id": "job_1234567890ab",
       "status": "SUCCEEDED",
       "queued_at": "2026-03-24T10:30:00Z"
     }
   }
   ```

6. 再查询一次任务详情，确认不是“任务创建成功但实际没跑”：

   ```bash
   curl 'http://127.0.0.1:8000/internal/jobs/JOB_ID' \
     -H 'X-Internal-Token: your-token'
   ```

#### 预期结果

- 创建数据源成功时，响应中的 `data.type=file`，`data.id` 为后续所有操作的主键；
- 触发全量同步后，若目录下有 2 个文件，任务详情中通常应看到 `status=SUCCEEDED` 且 `processed_count=2`；
- 任务详情中的 `triggered_by` 会映射为你在同步请求里传入的 `operator`；
- 查询 `GET /internal/sources/SOURCE_ID` 时，返回中的 `latest_job` 应能看到最近一次同步任务摘要。

#### 常见问题 / 注意事项

- `file` 数据源只在创建时校验 `config.root_path` 是否存在，不会帮你自动创建目录；
- 全量同步会把当前扫描结果视为最新快照，如果后续删除了目录中的某些文件，再次执行 `full` 时，这些缺失文档会被标记为删除；
- 如果你传了不存在的 `root_path`，创建接口会返回 `400`，错误信息为 `file source requires config.root_path`；
- 如果响应中的 `status` 不是 `SUCCEEDED`，以 `/internal/jobs/{job_id}` 查到的 `error_summary` 为准做排查。

### 7.2 案例二：创建 API 数据源并执行增量同步

#### 场景目标

理解 `api` 数据源如何接入外部知识接口，以及增量同步为什么依赖 `updated_at` 和 `checkpoint`。

#### 适用角色

- 对接外部知识平台、内容中心或 FAQ 服务的研发同学；
- 需要验证增量拉取协议的联调同学；
- 需要确认 ACL 元数据是否能透传进入文档索引的测试同学。

#### 前置条件

- 已有一个可访问的 HTTP 接口，例如 `http://127.0.0.1:9000/mock/knowledge`；
- 该接口返回格式必须满足下面两种之一：直接返回数组，或返回对象且对象中包含 `items` 数组；
- 如果你要验证真正的增量行为，返回项里应提供可比较的新旧值，例如 `updated_at`。

推荐的返回样例如下：

```json
{
  "items": [
    {
      "external_doc_id": "faq-001",
      "title": "请假制度",
      "content": "请假需提前在系统提交审批。",
      "doc_type": "faq",
      "updated_at": "2026-03-24T09:00:00Z",
      "metadata": {
        "category": "hr"
      },
      "acl": [
        {
          "type": "role",
          "value": "employee",
          "effect": "allow"
        }
      ]
    }
  ]
}
```

#### 操作步骤

1. 创建 `api` 数据源：

   ```bash
   curl -X POST 'http://127.0.0.1:8000/internal/sources' \
     -H 'Content-Type: application/json' \
     -H 'X-Internal-Token: your-token' \
     -d '{
       "name": "知识接口",
       "type": "api",
       "config": {
         "base_url": "http://127.0.0.1:9000/mock/knowledge",
         "params": {
           "scene": "faq"
         }
       },
       "sync_mode": "incremental",
       "enabled": true
     }'
   ```

2. 记录返回中的 `data.id`，后文记为 `API_SOURCE_ID`。

3. 先执行第一次增量同步：

   ```bash
   curl -X POST 'http://127.0.0.1:8000/internal/sources/API_SOURCE_ID/sync' \
     -H 'Content-Type: application/json' \
     -H 'X-Internal-Token: your-token' \
     -d '{
       "mode": "incremental",
       "operator": "manual"
     }'
   ```

4. 记录返回中的 `job_id`，再调用 `/internal/jobs/{job_id}` 查看结果。

5. 如果你的 mock 接口支持打印请求参数，再执行第二次增量同步，观察它是否收到自动附加的 `checkpoint` 查询参数。

#### 预期结果

- 创建成功时，返回中的 `data.type=api`，`config.base_url` 会按原值保存；
- 第一次增量同步在没有历史检查点时，会直接按当前接口返回的数据处理；
- 成功任务会把本次处理记录中最大的 `updated_at` 保存为检查点；
- 第二次增量同步时，系统会自动向 `base_url` 附加 `checkpoint` 参数，用于让上游只返回新增或变更的数据；
- 如果返回项里包含 `acl`，这些权限条目会写入文档 ACL，供后续检索/问答过滤使用。

#### 常见问题 / 注意事项

- `api` 数据源创建时只强制要求 `config.base_url`，并不会在创建阶段校验远端接口真的可用；
- 如果接口返回的既不是数组，也不是带 `items` 的对象，同步任务会失败，`error_summary` 中会出现 `API source response must be a list or an object with 'items'`；
- `updated_at` 最好使用可比较的时间戳或 ISO 时间字符串，否则你很难判断增量边界是否符合预期；
- 当前检查点保存在内存仓储中，服务重启后会丢失，所以本地验证增量行为时不要在两次同步之间重启应用。

### 7.3 案例三：查看任务结果并理解 `SYNC_RUN_INLINE`

#### 场景目标

明确“同步请求返回了，不等于同步已经执行完成”，避免把当前版本的占位模式误判为系统故障。

#### 适用角色

- 联调任务状态接口的研发与测试同学；
- 需要区分“已执行完成”和“仅创建任务”的项目同学。

#### 前置条件

- 已至少创建过一个可用的数据源；
- 知道当前 `.env` 中 `SYNC_RUN_INLINE` 的值；
- 如果你要验证两种模式的差异，修改 `.env` 后需要重启 `uvicorn` 进程。

#### 操作步骤

1. 保持 `SYNC_RUN_INLINE=true`，触发任意一次文件源或 API 源同步。
2. 观察 `/internal/sources/{source_id}/sync` 的直接返回值，再查询 `/internal/jobs/{job_id}`。
3. 将 `.env` 中的 `SYNC_RUN_INLINE` 改为 `false`，重启服务。
4. 用同一个数据源再触发一次同步，并再次查询任务详情。

#### 预期结果

- 当 `SYNC_RUN_INLINE=true` 时，同步接口返回的 `data.status` 往往已经是最终态，例如 `SUCCEEDED` 或 `FAILED`；
- 当 `SYNC_RUN_INLINE=false` 时，同步接口仍会返回 `code=0`，但 `data.status` 只会是 `PENDING`；
- 在 `SYNC_RUN_INLINE=false` 的情况下，当前版本不会自动消费后台任务，所以 `/internal/jobs/{job_id}` 中通常会持续看到：
  - `status=PENDING`
  - `started_at=null`
  - `finished_at=null`
- 对当前一期版本来说，任务结果是否可信，应该以 `GET /internal/jobs/{job_id}` 返回的字段为准，而不是只看触发接口是否返回 `200`。

#### 常见问题 / 注意事项

- `PENDING` 不一定代表卡住，也可能只是你主动启用了“仅创建任务、不内联执行”的占位模式；
- 当前版本还没有接入真正的队列消费者，所以把 `SYNC_RUN_INLINE` 设为 `false` 后，不会有人替你把任务从 `PENDING` 推进到 `RUNNING`；
- 如果你只是本地联调，建议保持默认值 `true`，否则很容易误以为同步链路失效。

### 7.4 案例四：创建 `postgres` 数据源并识别一期占位边界

#### 场景目标

帮助你正确理解 `postgres` 类型当前“可创建、不可用作真实同步”的状态，避免把二期预留能力当成一期缺陷。

#### 适用角色

- 在评估数据库直连接入方案的研发同学；
- 需要判断验收边界的测试与项目同学。

#### 前置条件

- 服务已经启动；
- 你只需要验证接口合同，不需要真的准备 PostgreSQL 表结构或测试库。

#### 操作步骤

1. 创建一个 `postgres` 数据源。当前实现不会在创建阶段校验数据库连通性，所以下面的占位配置就可以通过：

   ```bash
   curl -X POST 'http://127.0.0.1:8000/internal/sources' \
     -H 'Content-Type: application/json' \
     -H 'X-Internal-Token: your-token' \
     -d '{
       "name": "订单库占位源",
       "type": "postgres",
       "config": {
         "dsn": "postgresql://postgres:postgres@localhost:5432/demo",
         "table": "knowledge_items"
       },
       "sync_mode": "incremental",
       "enabled": true
     }'
   ```

2. 记录返回中的 `data.id`，后文记为 `PG_SOURCE_ID`。

3. 在默认的 `SYNC_RUN_INLINE=true` 模式下触发一次同步：

   ```bash
   curl -X POST 'http://127.0.0.1:8000/internal/sources/PG_SOURCE_ID/sync' \
     -H 'Content-Type: application/json' \
     -H 'X-Internal-Token: your-token' \
     -d '{
       "mode": "incremental",
       "operator": "manual"
     }'
   ```

4. 再查询任务详情，关注 `status` 和 `error_summary`。

#### 预期结果

- 创建阶段会成功返回 `code=0`，说明当前接口合同允许先把 `postgres` 数据源注册进系统；
- 在 `SYNC_RUN_INLINE=true` 时，同步请求会创建任务并立即执行，最终任务状态通常是 `FAILED`；
- 查询 `/internal/jobs/{job_id}` 时，`error_summary` 应包含 `PostgresConnector will be implemented in phase 2`，这表示你触发到了预留实现，而不是配置写错；
- 如果你把 `SYNC_RUN_INLINE` 改成 `false` 再触发，同步接口只会返回 `PENDING`，但这不代表 `postgres` 已经可用，只是任务尚未执行而已。

#### 常见问题 / 注意事项

- 当前代码没有把 `postgres` 同步失败映射成 `501`，而是把任务记为 `FAILED` 并把原因写入 `error_summary`；
- 因为 `postgres` 连接器还没实现，所以这里的失败应视为“一期已知边界”，不应与文件源、API 源的真正缺陷混为一谈；
- 如果你在验收中要描述这个能力，建议明确写成“支持创建占位数据源，不支持真实数据库同步”。

## 8. 异常边界、限制与 FAQ

本章不再重复主流程步骤，而是集中回答联调阶段最容易混淆的几个问题。

阅读方法建议如下：
- 先看“现象”，确认自己遇到的是不是同一类问题；
- 再看“原因”，判断它属于配置问题、一期限制，还是疑似真实缺陷；
- 最后按“结论 / 建议”决定下一步是改配置、补数据、调整预期，还是提缺陷单。

### 8.1 先学会区分“一期限制”和“真实缺陷”

为了避免把正常边界误报成 Bug，建议先按下面的标准做第一轮判断。

| 类型 | 典型表现 | 应如何理解 |
| --- | --- | --- |
| 一期已知限制 | 文档已明确写成“未实现”“仅占位”“仅用于本地验证” | 属于当前版本设计范围，不按缺陷处理 |
| 配置或使用问题 | 鉴权头缺失、路径写错、源被禁用、测试数据不符合格式 | 先修正输入和环境，再重复验证 |
| 疑似真实缺陷 | `file` / `api` 主流程按文档操作后仍异常失败，且行为与代码声明不一致 | 应记录请求参数、任务结果和报错信息，按缺陷处理 |

可以直接按下面几个例子理解：
- 创建 `postgres` 数据源成功，但同步失败：属于一期限制；
- `SYNC_RUN_INLINE=false` 后任务长期停在 `PENDING`：属于一期限制；
- 服务重启后历史数据消失：属于一期限制；
- `file` 数据源路径存在、鉴权正确，但同步仍 `FAILED`：更像真实问题，应继续排查；
- `/internal/search` 明明已有数据却稳定返回空结果：如果过滤条件和 ACL 都确认无误，应按疑似缺陷处理。

### 8.2 FAQ：为什么 `/internal/*` 接口返回 `401 invalid internal token`？

**现象**

- 调用 `/internal/sources`、`/internal/search`、`/internal/ask`、`/internal/jobs/{job_id}` 等接口时，返回 `401`；
- 响应详情通常是 `invalid internal token`；
- 但访问 `/health` 或根路径 `/` 却是正常的。

**原因**

- 当环境变量 `INTERNAL_API_TOKEN` 已配置时，所有 `/internal/*` 路由都会校验请求头 `X-Internal-Token`；
- 请求头缺失，或者值与服务端配置不一致，都会直接被拒绝；
- `/health` 和 `/` 不走这套鉴权逻辑，所以它们正常不代表内部接口一定可调通。

**结论 / 建议**

- 先确认 `.env` 是否真的配置了 `INTERNAL_API_TOKEN`；
- 如果已配置，请在所有 `/internal/*` 请求中补齐正确的 `X-Internal-Token`；
- 如果只是本地单机调试，也可以临时把 `INTERNAL_API_TOKEN` 留空，此时内部接口不会校验 Token；
- 判断服务是否“只是不通鉴权”时，不要只看 `/health`，要直接请求一个 `/internal/*` 接口验证。

### 8.3 FAQ：为什么同步接口返回成功，但任务一直停在 `PENDING`？

**现象**

- 调用 `/internal/sources/{source_id}/sync` 后接口返回 `code=0`；
- 但 `data.status` 是 `PENDING`；
- 再查 `/internal/jobs/{job_id}`，任务状态仍长时间保持 `PENDING`。

**原因**

- 当前版本只有在 `SYNC_RUN_INLINE=true` 时，才会在当前进程里直接执行同步任务；
- 如果把 `SYNC_RUN_INLINE` 改成 `false`，接口仍会先创建任务记录，但项目里还没有真正的后台任务消费者去继续执行它；
- 所以看到 `PENDING` 并不表示任务“稍后一定会自动开始”，而是“当前没人执行它”。

**结论 / 建议**

- 本地联调、演示和验收阶段建议保持 `SYNC_RUN_INLINE=true`；
- 如果你必须验证 `false` 模式，请把预期改成“只验证入队，不验证执行完成”；
- 不要把 `PENDING` 误判成调度 Bug，除非项目后续已经补上独立队列消费者。

### 8.4 FAQ：为什么服务重启后，之前创建的数据源、任务和检索结果都没了？

**现象**

- 服务运行时创建过数据源，也完成过同步；
- 但一旦重启应用，再查数据源、任务或检索结果时就像“恢复出厂设置”；
- 某些情况下还会看到之前记下来的 `source_id`、`job_id` 再查询时返回 `404`。

**原因**

- 当前 `Source`、`Job`、`Document`、`Chunk`、`Checkpoint` 都保存在内存仓储中；
- 这些仓储会随着进程生命周期存在，服务一旦重启，内存状态就会被整体清空；
- 这也是为什么一期文档反复强调“当前仅用于本地验证，不具备持久化能力”。

**结论 / 建议**

- 这属于当前版本的正常边界，不是数据异常丢失缺陷；
- 在同一轮验证里，尽量不要在“创建数据源 → 同步 → 检索 / 问答”链路中间重启服务；
- 如果必须重启，请准备好重新创建数据源并重新同步；
- 任何依赖历史 `source_id`、`job_id` 的联调脚本，都要接受“服务重启后需重新初始化”的事实。

### 8.5 FAQ：为什么 `/health` 显示正常，但数据库、Redis、MinIO 其实并不能用？

**现象**

- `GET /health` 返回 `code=0`，应用状态是 `ok`；
- `database`、`redis`、`minio` 甚至可能显示 `configured`；
- 但你并没有看到真实的数据库持久化、队列消费或对象存储读写能力。

**原因**

- 当前健康检查只做“配置级判断”，本质上是在确认相关环境变量是否已填写；
- 例如 `DATABASE_URL` 已配置时，接口会返回“已配置 PostgreSQL 连接串，待接入正式持久化仓储”；
- 这并不是在测试真实网络连通性，也不是在验证这些依赖已经参与业务主链路。

**结论 / 建议**

- 把 `/health` 视为“启动态与配置态检查”，不要当成“依赖已可用”的最终证明；
- 若你要判断是否已接入持久化、队列或对象存储，应以真实业务行为为准，而不是只看健康检查；
- 对一期项目来说，只要应用可启动、接口可调用，且健康检查正确反映配置状态，就算符合当前预期。

### 8.6 FAQ：为什么 `postgres` 数据源能创建，却不能像文件源那样正常同步？

**现象**

- 创建 `type=postgres` 的数据源时接口返回成功；
- 触发同步后，如果 `SYNC_RUN_INLINE=true`，任务通常会直接进入 `FAILED`；
- 任务详情里的 `error_summary` 会说明 `PostgresConnector will be implemented in phase 2`；
- 如果 `SYNC_RUN_INLINE=false`，你可能只会先看到 `PENDING`，但这并不代表它已经支持真实同步。

**原因**

- `postgres` 类型目前只保留了接口和流程占位，连接器的 `test_connection`、`pull_full`、`pull_incremental`、`normalize` 都还未实现；
- 也就是说，当前代码支持“声明这种数据源类型”，但不支持“完成真正的数据拉取和索引构建”。

**结论 / 建议**

- 这属于一期明确限制，应在手册、验收和联调说明中写成“支持占位创建，不支持真实同步”；
- 不要把 `postgres` 同步失败与 `file`、`api` 的异常失败混为一谈；
- 若业务确实需要数据库数据接入，应把它视为二期实现项，而不是当前 Bug 修复项。

### 8.7 FAQ：为什么问答接口返回“当前证据不足，暂时无法给出可靠答案。”？

**现象**

- 调用 `/internal/ask` 成功，但 `answer` 是“当前证据不足，暂时无法给出可靠答案。”；
- 返回里的 `evidence_status` 是 `INSUFFICIENT`；
- `citations` 可能为空，或者命中数量很少。

**原因**

- 当前问答能力依赖检索结果；
- 当命中数量小于 `MIN_EVIDENCE_COUNT`，或者最高分低于 `SEARCH_SCORE_THRESHOLD` 时，服务会走证据不足兜底；
- 另外，如果 ACL 上下文不匹配，文档会在检索阶段就被过滤掉，最终也会表现为“证据不足”。

**结论 / 建议**

- 先用同样的问题走一次 `/internal/search`，确认是否真的能检索到内容；
- 如果搜索结果为空，优先检查同步是否成功、过滤条件是否过严、ACL 上下文是否匹配；
- 如果只是本地调试，也可以结合场景适当调整 `MIN_EVIDENCE_COUNT` 和 `SEARCH_SCORE_THRESHOLD`，但要清楚这属于调参，不代表线上推荐值；
- 不要把“证据不足兜底”直接当成问答接口故障，它更多是在告诉你“当前可引用证据不够”。

### 8.8 FAQ：为什么查任务或同步时报 `404` / `400`，这是系统异常吗？

**现象**

- 查询 `/internal/jobs/{job_id}` 时返回 `404 job not found`；
- 查询 `/internal/sources/{source_id}` 时返回 `404 source not found`；
- 触发同步时返回 `400`，内容类似 `source xxx is disabled`。

**原因**

- `404` 往往说明传入的 `source_id` 或 `job_id` 本身不存在，或者对应数据已经因服务重启而丢失；
- `400 source ... is disabled` 说明该数据源当前处于禁用状态，系统按设计拒绝执行同步；
- 这类返回通常是输入状态不满足要求，而不是服务内部崩溃。

**结论 / 建议**

- 先核对当前使用的 `source_id`、`job_id` 是否来自本次进程生命周期内的新响应；
- 如果数据源被禁用，先重新创建为 `enabled=true`，或在准备请求时确认不要复用旧的禁用资源；
- 只有在 ID 明确有效、资源状态正常的前提下仍持续报错，才更值得作为缺陷继续追查。

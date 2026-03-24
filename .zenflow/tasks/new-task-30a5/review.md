## Code Review

**Verdict**: REQUEST CHANGES
**Confidence**: HIGH

### Summary
本次分支补齐了知识库二期的大量基础能力，包括 PostgreSQL/pgvector 仓储、异步同步编排、MinIO 归档、健康检查和回归测试，整体方向与 `spec.md` 基本一致。
但当前实现里仍有 2 个必须修复的并发/部署级问题：Redis 锁释放不是原子操作，且 Redis 初始化失败时会静默降级到进程内队列；这两个问题都会直接破坏“单数据源单活任务”的核心约束。

### Findings

| Priority | Issue | Location |
|----------|-------|----------|
| P1 / 🔴 | Redis 锁释放采用 `GET` + `DELETE` 两步操作，不具备原子性；锁过期并被新任务抢占后，旧任务仍可能删掉新锁，导致同一数据源出现并发同步。 | `app/services/sync_queue.py:122` |
| P1 / 🔴 | 在已配置 `REDIS_URL` 的情况下，如果 Redis 初始化失败，代码会静默回退到 `InMemorySyncQueue`；多实例部署时会丢失跨实例队列与锁语义，导致任务重复执行或进程重启后任务丢失。 | `app/services/sync_queue.py:138` |
| P2 / 🟡 | 作业对象只有一个 `snapshot_path` 字段；失败时写入失败样本路径会覆盖前面保存的原始快照路径，排障时无法同时拿到 raw snapshot 与 failed samples。 | `app/services/indexing_service.py:68` |
| P2 / 🟡 | 健康检查对远程 embedding 服务发起的是 `GET`，而真实向量生成走的是 `POST`；只支持 `POST` 的 provider 会被误报为不可用。 | `app/services/embedding_service.py:63` |

### Details

#### [P1 / 🔴] Redis 分布式锁释放不是原子操作
**File:** `app/services/sync_queue.py:122`

`release_source_lock()` 先 `GET` 再 `DELETE`。如果旧锁正好在 `GET` 之后过期，而另一个 worker 立即成功 `SET NX` 获得了新锁，那么当前代码仍会执行 `DELETE`，把新 owner 的锁一起删掉。

这会直接破坏 `SyncOrchestrator.trigger_sync()` 依赖的“同一 source 同时只能有一个 active job”约束，属于典型的分布式锁误删问题。

**Suggested fix:**
```python
RELEASE_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""

def release_source_lock(self, source_id: str, owner: str) -> None:
    self._client.eval(RELEASE_LOCK_SCRIPT, 1, self._lock_key(source_id), owner)
```

#### [P1 / 🔴] Redis 不可用时静默回退到进程内队列
**File:** `app/services/sync_queue.py:138`

当 `REDIS_URL` 已配置时，系统语义已经切换到“依赖 Redis 提供跨实例队列与锁”。此时 `build_sync_queue()` 捕获异常后直接回退到 `InMemorySyncQueue`，单机测试看起来还能工作，但在线上多副本场景中，每个进程都会维护自己的本地队列和锁：

- A 实例创建的任务，B 实例看不到；
- source lock 只在本进程生效，无法阻止跨实例重复触发；
- 进程重启会直接丢掉未消费任务。

这不是普通降级，而是把“可用但语义改变”伪装成“正常运行”，风险很高。

**Suggested fix:**
```python
def build_sync_queue(settings: Settings) -> SyncQueue:
    if not settings.redis_url:
        return InMemorySyncQueue(lock_ttl_seconds=settings.sync_lock_ttl_seconds)

    client = create_redis_client(settings)
    return RedisSyncQueue(
        client,
        queue_name=f"{settings.app_name}:sync-jobs",
        lock_ttl_seconds=settings.sync_lock_ttl_seconds,
    )
```

如果确实需要回退，建议新增显式开关，例如 `ALLOW_INMEMORY_QUEUE_FALLBACK=true`，默认关闭并在 `/health` 中明确暴露。

### Recommendation
优先修复 `app/services/sync_queue.py` 中的两个 Redis 语义问题，再考虑合并；其余两项可作为后续优化，但建议在进入联调前一并补齐，以免影响排障与健康检查可信度。

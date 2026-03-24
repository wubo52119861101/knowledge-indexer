from __future__ import annotations

from dataclasses import dataclass, field
import json

from app.core.database import from_pgvector
from app.core.config import Settings
from app.core.container import ServiceContainer
from app.core.utils import cosine_similarity
from app.models.chunk import Chunk
from app.models.common import DocumentStatus, EmbeddingStatus, JobStatus, SourceType, SyncMode, generate_id, utcnow
from app.models.document import Document
from app.models.job import IndexJob
from app.models.source import Source
from app.repositories.checkpoint_repo import PostgresCheckpointRepository
from app.repositories.chunk_repo import PostgresChunkRepository
from app.repositories.document_repo import PostgresDocumentRepository
from app.repositories.job_repo import PostgresJobRepository
from app.repositories.source_repo import PostgresSourceRepository
from app.schemas.retrieval import SearchFilters


@dataclass
class FakePostgresState:
    sources: dict[str, dict] = field(default_factory=dict)
    jobs: dict[str, dict] = field(default_factory=dict)
    checkpoints: dict[tuple[str, str], dict] = field(default_factory=dict)
    documents: dict[str, dict] = field(default_factory=dict)
    document_keys: dict[tuple[str, str], str] = field(default_factory=dict)
    chunks: dict[str, dict] = field(default_factory=dict)
    document_chunk_ids: dict[str, list[str]] = field(default_factory=dict)

    def execute(self, query: str, params: tuple) -> dict | list[dict] | None:
        normalized = " ".join(query.split()).lower()

        if normalized.startswith("insert into kb_sources"):
            row = {
                "id": params[0],
                "name": params[1],
                "type": params[2],
                "config_json": params[3],
                "config_masked_json": params[4],
                "sync_mode": params[5],
                "enabled": params[6],
                "last_sync_at": params[7],
                "created_at": params[8],
                "updated_at": params[9],
            }
            self.sources[row["id"]] = row
            return None

        if "from kb_sources where id = %s" in normalized:
            return self.sources.get(params[0])

        if "from kb_sources order by created_at asc" in normalized:
            return sorted(self.sources.values(), key=lambda item: item["created_at"])

        if normalized.startswith("update kb_sources set last_sync_at"):
            row = self.sources[params[2]]
            row["last_sync_at"] = params[0]
            row["updated_at"] = params[1]
            return None

        if normalized.startswith("insert into kb_sync_jobs"):
            row = {
                "id": params[0],
                "source_id": params[1],
                "mode": params[2],
                "status": params[3],
                "triggered_by": params[4],
                "processed_count": params[5],
                "failed_count": params[6],
                "error_summary": params[7],
                "failure_stage": params[8],
                "snapshot_path": params[9],
                "checkpoint_before": params[10],
                "checkpoint_after": params[11],
                "started_at": params[12],
                "finished_at": params[13],
                "created_at": params[14],
            }
            self.jobs[row["id"]] = row
            return None

        if "from kb_sync_jobs where id = %s" in normalized:
            return self.jobs.get(params[0])

        if "from kb_sync_jobs where source_id = %s and status in (%s, %s) order by created_at desc limit 1" in normalized:
            rows = [
                row
                for row in self.jobs.values()
                if row["source_id"] == params[0] and row["status"] in {params[1], params[2]}
            ]
            rows.sort(key=lambda item: item["created_at"], reverse=True)
            return rows[0] if rows else None

        if "from kb_sync_jobs where source_id = %s order by created_at desc limit 1" in normalized:
            rows = [row for row in self.jobs.values() if row["source_id"] == params[0]]
            rows.sort(key=lambda item: item["created_at"], reverse=True)
            return rows[0] if rows else None

        if "from kb_sync_jobs where status = %s order by created_at asc" in normalized:
            rows = [row for row in self.jobs.values() if row["status"] == params[0]]
            rows.sort(key=lambda item: item["created_at"])
            return rows

        if normalized.startswith("update kb_sync_jobs set status"):
            row = self.jobs[params[10]]
            row["status"] = params[0]
            row["processed_count"] = params[1]
            row["failed_count"] = params[2]
            row["error_summary"] = params[3]
            row["failure_stage"] = params[4]
            row["snapshot_path"] = params[5]
            row["checkpoint_before"] = params[6]
            row["checkpoint_after"] = params[7]
            row["started_at"] = params[8]
            row["finished_at"] = params[9]
            return None

        if "from kb_sync_checkpoints where source_id = %s and checkpoint_key = %s" in normalized:
            return self.checkpoints.get((params[0], params[1]))

        if normalized.startswith("insert into kb_sync_checkpoints"):
            key = (params[1], params[2])
            current = self.checkpoints.get(key)
            row = {
                "id": current["id"] if current else params[0],
                "source_id": params[1],
                "checkpoint_key": params[2],
                "checkpoint_value": params[3],
                "updated_at": params[4],
            }
            self.checkpoints[key] = row
            return row

        if normalized.startswith("insert into kb_documents"):
            key = (params[1], params[2])
            existing_id = self.document_keys.get(key)
            if existing_id is not None:
                row = self.documents[existing_id]
                row.update(
                    {
                        "title": params[3],
                        "content_text": params[4],
                        "content_hash": params[5],
                        "doc_type": params[6],
                        "metadata_json": params[7],
                        "acl_json": params[8],
                        "status": params[9],
                        "version": row["version"] + 1,
                        "updated_at": params[12],
                    }
                )
                return row
            row = {
                "id": params[0],
                "source_id": params[1],
                "external_doc_id": params[2],
                "title": params[3],
                "content_text": params[4],
                "content_hash": params[5],
                "doc_type": params[6],
                "metadata_json": params[7],
                "acl_json": params[8],
                "status": params[9],
                "version": params[10],
                "created_at": params[11],
                "updated_at": params[12],
            }
            self.documents[row["id"]] = row
            self.document_keys[key] = row["id"]
            return row

        if "from kb_documents where id = %s" in normalized:
            return self.documents.get(params[0])

        if "from kb_documents where source_id = %s order by created_at asc" in normalized:
            rows = [row for row in self.documents.values() if row["source_id"] == params[0]]
            return sorted(rows, key=lambda item: item["created_at"])

        if "from kb_documents order by created_at asc" in normalized:
            return sorted(self.documents.values(), key=lambda item: item["created_at"])

        if normalized.startswith("update kb_documents set status"):
            row = self.documents[params[2]]
            row["status"] = params[0]
            row["updated_at"] = params[1]
            return row

        if normalized.startswith("delete from kb_chunks where document_id = %s"):
            document_id = params[0]
            for chunk_id in self.document_chunk_ids.get(document_id, []):
                self.chunks.pop(chunk_id, None)
            self.document_chunk_ids[document_id] = []
            return None

        if normalized.startswith("insert into kb_chunks"):
            row = {
                "id": params[0],
                "document_id": params[1],
                "chunk_index": params[2],
                "content": params[3],
                "summary": params[4],
                "token_count": params[5],
                "metadata_json": params[6],
                "embedding": params[7],
                "embedding_status": params[8],
                "created_at": params[9],
                "updated_at": params[10],
            }
            self.chunks[row["id"]] = row
            self.document_chunk_ids.setdefault(row["document_id"], []).append(row["id"])
            self.document_chunk_ids[row["document_id"]].sort(key=lambda chunk_id: self.chunks[chunk_id]["chunk_index"])
            return None

        if "from kb_chunks where document_id = %s order by chunk_index asc" in normalized:
            rows = [self.chunks[chunk_id] for chunk_id in self.document_chunk_ids.get(params[0], [])]
            return rows

        if "from kb_chunks order by created_at asc, chunk_index asc" in normalized:
            return sorted(self.chunks.values(), key=lambda item: (item["created_at"], item["chunk_index"]))

        if "from kb_chunks" in normalized and "1 - (embedding <=> %s::vector) as score" in normalized:
            query_embedding = from_pgvector(params[0])
            limit = int(params[-1])
            rows = [row for row in self.chunks.values() if row["embedding_status"] == EmbeddingStatus.DONE.value]

            cursor = 2
            if "metadata_json ->> 'source_id' in (" in normalized:
                source_count = normalized.count("metadata_json ->> 'source_id'")
                source_ids = list(params[cursor : cursor + source_count])
                cursor += source_count
                rows = [row for row in rows if row["metadata_json"].get("source_id") in source_ids]

            if "metadata_json ->> 'doc_type' in (" in normalized:
                doc_type_count = normalized.count("metadata_json ->> 'doc_type'")
                doc_types = list(params[cursor : cursor + doc_type_count])
                cursor += doc_type_count
                rows = [row for row in rows if row["metadata_json"].get("doc_type") in doc_types]

            if "metadata_json @> %s::jsonb" in normalized:
                metadata_filter = params[cursor]
                cursor += 1
                expected_pairs = json.loads(metadata_filter) if isinstance(metadata_filter, str) else {}
                rows = [
                    row
                    for row in rows
                    if all(row["metadata_json"].get(key) == value for key, value in expected_pairs.items())
                ]

            scored_rows = []
            for row in rows:
                score = cosine_similarity(query_embedding, from_pgvector(row["embedding"]))
                scored_rows.append({**row, "score": score})

            scored_rows.sort(key=lambda item: item["score"], reverse=True)
            return scored_rows[:limit]

        raise AssertionError(f"unexpected query: {normalized}")


class FakeCursor:
    def __init__(self, state: FakePostgresState) -> None:
        self._state = state
        self._result: dict | list[dict] | None = None
        self.description = None

    def execute(self, query: str, params: tuple | None = None) -> None:
        self._result = self._state.execute(query, tuple(params or ()))

    def fetchone(self):
        if isinstance(self._result, list):
            return self._result[0] if self._result else None
        return self._result

    def fetchall(self):
        if self._result is None:
            return []
        if isinstance(self._result, list):
            return self._result
        return [self._result]

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class FakeConnection:
    def __init__(self, state: FakePostgresState) -> None:
        self._state = state
        self.committed = False
        self.rolled_back = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self._state)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        return None

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class FakeConnectionFactory:
    def __init__(self) -> None:
        self.state = FakePostgresState()

    def __call__(self) -> FakeConnection:
        return FakeConnection(self.state)


def test_postgres_source_repository_crud_and_touch_sync() -> None:
    factory = FakeConnectionFactory()
    repo = PostgresSourceRepository(factory)
    source = Source(
        id="src_1",
        name="订单库",
        type=SourceType.POSTGRES,
        config={"connection_dsn": "postgresql://user:secret@host:5432/db", "schema": "public"},
        sync_mode=SyncMode.INCREMENTAL,
    )

    repo.add(source)
    fetched = repo.get(source.id)
    repo.touch_sync(source.id)

    assert fetched is not None
    assert fetched.name == "订单库"
    assert len(repo.list_all()) == 1
    assert factory.state.sources[source.id]["config_masked_json"]["connection_dsn"] == "******"
    assert repo.get(source.id).last_sync_at is not None


def test_postgres_job_repository_add_save_and_latest() -> None:
    factory = FakeConnectionFactory()
    repo = PostgresJobRepository(factory)
    older_job = IndexJob(
        id="job_old",
        source_id="src_1",
        mode=SyncMode.FULL,
        status=JobStatus.PENDING,
        triggered_by="tester",
        created_at=utcnow(),
    )
    newer_job = IndexJob(
        id="job_new",
        source_id="src_1",
        mode=SyncMode.INCREMENTAL,
        status=JobStatus.PENDING,
        triggered_by="tester",
        created_at=utcnow(),
    )

    repo.add(older_job)
    repo.add(newer_job)
    newer_job.status = JobStatus.SUCCEEDED
    newer_job.processed_count = 8
    repo.save(newer_job)

    latest = repo.latest_for_source("src_1")
    assert latest is not None
    assert latest.id == "job_new"
    assert repo.get("job_new").status is JobStatus.SUCCEEDED
    assert repo.get("job_new").processed_count == 8


def test_postgres_checkpoint_repository_upsert() -> None:
    factory = FakeConnectionFactory()
    repo = PostgresCheckpointRepository(factory)

    first = repo.save("src_1", "default", "10")
    second = repo.save("src_1", "default", "20")

    assert first.id == second.id
    assert repo.get("src_1", "default").checkpoint_value == "20"


def test_postgres_document_repository_upsert_and_mark_deleted() -> None:
    factory = FakeConnectionFactory()
    repo = PostgresDocumentRepository(factory)
    document = Document(
        id=generate_id("doc"),
        source_id="src_1",
        external_doc_id="ext-1",
        title="退款规则",
        content_text="七天内可退",
        content_hash="hash-1",
        doc_type="faq",
        metadata={"lang": "zh"},
    )

    first = repo.upsert(document)
    updated = repo.upsert(
        Document(
            id=generate_id("doc"),
            source_id="src_1",
            external_doc_id="ext-1",
            title="退款规则（新）",
            content_text="七天内可退，逾期不支持",
            content_hash="hash-2",
            doc_type="faq",
            metadata={"lang": "zh", "version": 2},
        )
    )
    deleted = repo.mark_missing_as_deleted("src_1", {"another-doc"})

    assert first.version == 1
    assert updated.id == first.id
    assert updated.version == 2
    assert repo.get(first.id).title == "退款规则（新）"
    assert deleted[0].status is DocumentStatus.DELETED


def test_postgres_chunk_repository_replace_for_document() -> None:
    factory = FakeConnectionFactory()
    repo = PostgresChunkRepository(factory)
    document_id = "doc_1"

    first_chunks = [
        Chunk(
            id="chk_1",
            document_id=document_id,
            chunk_index=0,
            content="第一段",
            summary="摘要1",
            token_count=3,
            metadata={"source_id": "src_1"},
            embedding=[0.1, 0.2],
            embedding_status=EmbeddingStatus.DONE,
        ),
        Chunk(
            id="chk_2",
            document_id=document_id,
            chunk_index=1,
            content="第二段",
            summary="摘要2",
            token_count=3,
            metadata={"source_id": "src_1"},
            embedding=[0.3, 0.4],
            embedding_status=EmbeddingStatus.DONE,
        ),
    ]
    repo.replace_for_document(document_id, first_chunks)
    repo.replace_for_document(
        document_id,
        [
            Chunk(
                id="chk_3",
                document_id=document_id,
                chunk_index=0,
                content="新内容",
                summary="新摘要",
                token_count=3,
                metadata={"source_id": "src_1"},
                embedding=[0.9, 0.8],
                embedding_status=EmbeddingStatus.DONE,
            )
        ],
    )

    chunks = repo.list_by_document(document_id)
    assert [chunk.id for chunk in chunks] == ["chk_3"]
    assert chunks[0].embedding == [0.9, 0.8]
    assert len(repo.list_all()) == 1


def test_postgres_chunk_repository_search_candidates() -> None:
    factory = FakeConnectionFactory()
    repo = PostgresChunkRepository(factory)
    repo.replace_for_document(
        "doc_1",
        [
            Chunk(
                id="chk_1",
                document_id="doc_1",
                chunk_index=0,
                content="退款七天内可申请",
                summary=None,
                token_count=4,
                metadata={"source_id": "src_1", "doc_type": "faq", "lang": "zh"},
                embedding=[1.0, 0.0],
                embedding_status=EmbeddingStatus.DONE,
            ),
            Chunk(
                id="chk_2",
                document_id="doc_2",
                chunk_index=0,
                content="英文说明",
                summary=None,
                token_count=2,
                metadata={"source_id": "src_2", "doc_type": "manual", "lang": "en"},
                embedding=[0.0, 1.0],
                embedding_status=EmbeddingStatus.DONE,
            ),
        ],
    )

    candidates = repo.search_candidates(
        query_embedding=[1.0, 0.0],
        filters=SearchFilters(source_ids=["src_1"], doc_types=["faq"], metadata={"lang": "zh"}),
        limit=5,
    )

    assert [item.chunk.id for item in candidates] == ["chk_1"]
    assert candidates[0].score > 0.99


def test_service_container_switches_to_postgres_backend() -> None:
    settings = Settings(
        app_env="test",
        repository_backend="postgres",
        database_url="postgresql://postgres:postgres@localhost:5432/knowledge_indexer",
    )

    container = ServiceContainer(settings)

    assert isinstance(container.source_repo, PostgresSourceRepository)
    assert isinstance(container.document_repo, PostgresDocumentRepository)
    assert isinstance(container.chunk_repo, PostgresChunkRepository)
    assert isinstance(container.job_repo, PostgresJobRepository)
    assert isinstance(container.checkpoint_repo, PostgresCheckpointRepository)

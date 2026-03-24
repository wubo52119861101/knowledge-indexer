from app.models.chunk import Chunk
from app.models.common import AclEffect, AclType, DocumentStatus, EmbeddingStatus, SourceType, SyncMode, generate_id
from app.models.document import Document, DocumentAcl
from app.models.source import Source
from app.repositories.chunk_repo import InMemoryChunkRepository
from app.repositories.document_repo import InMemoryDocumentRepository
from app.repositories.source_repo import InMemorySourceRepository
from app.schemas.retrieval import AclContext, SearchFilters, SearchItem
from app.services.embedding_service import HashEmbeddingService
from app.services.retrieval_service import RetrievalService


class ReverseRerankService:
    def rerank(self, query: str, items: list[SearchItem]) -> list[SearchItem]:
        reordered = list(reversed(items))
        for index, item in enumerate(reordered):
            item.score = round(10 - index * 0.1, 4)
        return reordered


def test_acl_filter_only_returns_allowed_document() -> None:
    embedding_service = HashEmbeddingService(dimension=32)
    source_repo = InMemorySourceRepository()
    document_repo = InMemoryDocumentRepository()
    chunk_repo = InMemoryChunkRepository()

    public_source = source_repo.add(
        Source(
            id="src_public",
            name="public",
            type=SourceType.FILE,
            config={"root_path": "/tmp"},
            sync_mode=SyncMode.INCREMENTAL,
        )
    )

    public_document = document_repo.upsert(
        Document(
            id=generate_id("doc"),
            source_id=public_source.id,
            external_doc_id="doc-public",
            title="公开规则",
            content_text="退款需要在七天内发起。",
            content_hash="hash-1",
            doc_type="faq",
            metadata={"lang": "zh"},
        )
    )
    private_document = document_repo.upsert(
        Document(
            id=generate_id("doc"),
            source_id=public_source.id,
            external_doc_id="doc-private",
            title="客服专属",
            content_text="仅客服角色可见的退款脚本。",
            content_hash="hash-2",
            doc_type="faq",
            metadata={"lang": "zh"},
            acl_entries=[DocumentAcl(acl_type=AclType.ROLE, acl_value="cs", effect=AclEffect.ALLOW)],
        )
    )

    chunk_repo.replace_for_document(
        public_document.id,
        [
            Chunk(
                id=generate_id("chk"),
                document_id=public_document.id,
                chunk_index=0,
                content=public_document.content_text,
                summary=None,
                token_count=6,
                metadata={"source_id": public_document.source_id, "doc_type": public_document.doc_type, "lang": "zh"},
                embedding=embedding_service.embed(public_document.content_text),
                embedding_status=EmbeddingStatus.DONE,
            )
        ],
    )
    chunk_repo.replace_for_document(
        private_document.id,
        [
            Chunk(
                id=generate_id("chk"),
                document_id=private_document.id,
                chunk_index=0,
                content=private_document.content_text,
                summary=None,
                token_count=6,
                metadata={"source_id": private_document.source_id, "doc_type": private_document.doc_type, "lang": "zh"},
                embedding=embedding_service.embed(private_document.content_text),
                embedding_status=EmbeddingStatus.DONE,
            )
        ],
    )

    service = RetrievalService(
        source_repo=source_repo,
        document_repo=document_repo,
        chunk_repo=chunk_repo,
        embedding_service=embedding_service,
    )

    anonymous_results = service.search(
        query="退款规则",
        top_k=10,
        filters=SearchFilters(),
        acl_context=AclContext(),
    )
    cs_results = service.search(
        query="退款脚本",
        top_k=10,
        filters=SearchFilters(),
        acl_context=AclContext(roles=["cs"]),
    )

    assert all(item.document.title != "客服专属" for item in anonymous_results)
    assert any(item.document.title == "客服专属" for item in cs_results)


def test_search_filters_low_score_results() -> None:
    embedding_service = HashEmbeddingService(dimension=32)
    source_repo = InMemorySourceRepository()
    document_repo = InMemoryDocumentRepository()
    chunk_repo = InMemoryChunkRepository()

    source = source_repo.add(
        Source(
            id="src_public",
            name="public",
            type=SourceType.FILE,
            config={"root_path": "/tmp"},
            sync_mode=SyncMode.INCREMENTAL,
        )
    )
    document = document_repo.upsert(
        Document(
            id=generate_id("doc"),
            source_id=source.id,
            external_doc_id="doc-low-score",
            title="库存说明",
            content_text="仓库盘点流程和货架整理要求。",
            content_hash="hash-low",
            doc_type="manual",
            metadata={},
        )
    )
    chunk_repo.replace_for_document(
        document.id,
        [
            Chunk(
                id=generate_id("chk"),
                document_id=document.id,
                chunk_index=0,
                content=document.content_text,
                summary=None,
                token_count=8,
                metadata={"source_id": document.source_id, "doc_type": document.doc_type},
                embedding=embedding_service.embed(document.content_text),
                embedding_status=EmbeddingStatus.DONE,
            )
        ],
    )

    service = RetrievalService(
        source_repo=source_repo,
        document_repo=document_repo,
        chunk_repo=chunk_repo,
        embedding_service=embedding_service,
        min_score_threshold=0.9,
    )

    results = service.search(
        query="退款多久到账",
        top_k=5,
        filters=SearchFilters(),
        acl_context=AclContext(),
    )

    assert results == []


def test_search_skips_deleted_documents() -> None:
    embedding_service = HashEmbeddingService(dimension=32)
    source_repo = InMemorySourceRepository()
    document_repo = InMemoryDocumentRepository()
    chunk_repo = InMemoryChunkRepository()

    source = source_repo.add(
        Source(
            id="src_public",
            name="public",
            type=SourceType.FILE,
            config={"root_path": "/tmp"},
            sync_mode=SyncMode.INCREMENTAL,
        )
    )
    document = document_repo.upsert(
        Document(
            id=generate_id("doc"),
            source_id=source.id,
            external_doc_id="doc-deleted",
            title="过期规则",
            content_text="已经删除的旧规则。",
            content_hash="hash-deleted",
            doc_type="faq",
            metadata={},
            status=DocumentStatus.DELETED,
        )
    )
    chunk_repo.replace_for_document(
        document.id,
        [
            Chunk(
                id=generate_id("chk"),
                document_id=document.id,
                chunk_index=0,
                content=document.content_text,
                summary=None,
                token_count=4,
                metadata={"source_id": document.source_id, "doc_type": document.doc_type},
                embedding=embedding_service.embed(document.content_text),
                embedding_status=EmbeddingStatus.DONE,
            )
        ],
    )

    service = RetrievalService(
        source_repo=source_repo,
        document_repo=document_repo,
        chunk_repo=chunk_repo,
        embedding_service=embedding_service,
    )

    results = service.search(
        query="旧规则",
        top_k=5,
        filters=SearchFilters(),
        acl_context=AclContext(),
    )

    assert results == []


def test_search_applies_coarse_filters_before_returning_results() -> None:
    embedding_service = HashEmbeddingService(dimension=32)
    source_repo = InMemorySourceRepository()
    document_repo = InMemoryDocumentRepository()
    chunk_repo = InMemoryChunkRepository()

    source_repo.add(
        Source(
            id="src_zh",
            name="中文源",
            type=SourceType.FILE,
            config={"root_path": "/tmp"},
            sync_mode=SyncMode.INCREMENTAL,
        )
    )
    source_repo.add(
        Source(
            id="src_en",
            name="英文源",
            type=SourceType.FILE,
            config={"root_path": "/tmp"},
            sync_mode=SyncMode.INCREMENTAL,
        )
    )

    zh_document = document_repo.upsert(
        Document(
            id=generate_id("doc"),
            source_id="src_zh",
            external_doc_id="doc-zh",
            title="退款中文规则",
            content_text="退款需要在七天内发起申请。",
            content_hash="hash-zh",
            doc_type="faq",
            metadata={"lang": "zh"},
        )
    )
    en_document = document_repo.upsert(
        Document(
            id=generate_id("doc"),
            source_id="src_en",
            external_doc_id="doc-en",
            title="Refund guide",
            content_text="Refund requests must be submitted within seven days.",
            content_hash="hash-en",
            doc_type="manual",
            metadata={"lang": "en"},
        )
    )

    chunk_repo.replace_for_document(
        zh_document.id,
        [
            Chunk(
                id=generate_id("chk"),
                document_id=zh_document.id,
                chunk_index=0,
                content=zh_document.content_text,
                summary=None,
                token_count=8,
                metadata={"source_id": zh_document.source_id, "doc_type": zh_document.doc_type, "lang": "zh"},
                embedding=embedding_service.embed(zh_document.content_text),
                embedding_status=EmbeddingStatus.DONE,
            )
        ],
    )
    chunk_repo.replace_for_document(
        en_document.id,
        [
            Chunk(
                id=generate_id("chk"),
                document_id=en_document.id,
                chunk_index=0,
                content=en_document.content_text,
                summary=None,
                token_count=8,
                metadata={"source_id": en_document.source_id, "doc_type": en_document.doc_type, "lang": "en"},
                embedding=embedding_service.embed(en_document.content_text),
                embedding_status=EmbeddingStatus.DONE,
            )
        ],
    )

    service = RetrievalService(
        source_repo=source_repo,
        document_repo=document_repo,
        chunk_repo=chunk_repo,
        embedding_service=embedding_service,
    )

    results = service.search(
        query="退款申请",
        top_k=5,
        filters=SearchFilters(source_ids=["src_zh"], doc_types=["faq"], metadata={"lang": "zh"}),
        acl_context=AclContext(),
    )

    assert [item.document.external_id for item in results] == ["doc-zh"]


def test_search_supports_optional_rerank_hook() -> None:
    embedding_service = HashEmbeddingService(dimension=32)
    source_repo = InMemorySourceRepository()
    document_repo = InMemoryDocumentRepository()
    chunk_repo = InMemoryChunkRepository()
    source_repo.add(
        Source(
            id="src_1",
            name="demo",
            type=SourceType.FILE,
            config={"root_path": "/tmp"},
            sync_mode=SyncMode.INCREMENTAL,
        )
    )

    first_document = document_repo.upsert(
        Document(
            id=generate_id("doc"),
            source_id="src_1",
            external_doc_id="doc-1",
            title="第一条",
            content_text="退款规则第一条。",
            content_hash="hash-1",
            doc_type="faq",
            metadata={},
        )
    )
    second_document = document_repo.upsert(
        Document(
            id=generate_id("doc"),
            source_id="src_1",
            external_doc_id="doc-2",
            title="第二条",
            content_text="退款规则第二条。",
            content_hash="hash-2",
            doc_type="faq",
            metadata={},
        )
    )

    chunk_repo.replace_for_document(
        first_document.id,
        [
            Chunk(
                id=generate_id("chk"),
                document_id=first_document.id,
                chunk_index=0,
                content=first_document.content_text,
                summary=None,
                token_count=4,
                metadata={"source_id": first_document.source_id, "doc_type": first_document.doc_type},
                embedding=embedding_service.embed(first_document.content_text),
                embedding_status=EmbeddingStatus.DONE,
            )
        ],
    )
    chunk_repo.replace_for_document(
        second_document.id,
        [
            Chunk(
                id=generate_id("chk"),
                document_id=second_document.id,
                chunk_index=0,
                content=second_document.content_text,
                summary=None,
                token_count=4,
                metadata={"source_id": second_document.source_id, "doc_type": second_document.doc_type},
                embedding=embedding_service.embed(second_document.content_text),
                embedding_status=EmbeddingStatus.DONE,
            )
        ],
    )

    service = RetrievalService(
        source_repo=source_repo,
        document_repo=document_repo,
        chunk_repo=chunk_repo,
        embedding_service=embedding_service,
        rerank_service=ReverseRerankService(),
    )

    results = service.search(
        query="退款规则",
        top_k=2,
        filters=SearchFilters(),
        acl_context=AclContext(),
    )

    assert len(results) == 2
    assert results[0].score > results[1].score

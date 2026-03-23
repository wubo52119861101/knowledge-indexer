from app.models.chunk import Chunk
from app.models.common import AclEffect, AclType, DocumentStatus, EmbeddingStatus, SourceType, SyncMode, generate_id
from app.models.document import Document, DocumentAcl
from app.models.source import Source
from app.repositories.chunk_repo import InMemoryChunkRepository
from app.repositories.document_repo import InMemoryDocumentRepository
from app.repositories.source_repo import InMemorySourceRepository
from app.schemas.retrieval import AclContext, SearchFilters
from app.services.embedding_service import HashEmbeddingService
from app.services.retrieval_service import RetrievalService


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
            metadata={},
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
            metadata={},
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
                metadata={},
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
                metadata={},
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
                metadata={},
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
                metadata={},
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

from app.core.config import Settings
from app.models.chunk import Chunk
from app.models.common import EmbeddingStatus, SourceType, SyncMode, generate_id
from app.models.document import Document
from app.models.source import Source
from app.repositories.chunk_repo import InMemoryChunkRepository
from app.repositories.document_repo import InMemoryDocumentRepository
from app.repositories.source_repo import InMemorySourceRepository
from app.schemas.retrieval import AclContext, SearchFilters
from app.services.embedding_service import HashEmbeddingService
from app.services.qa_service import QaService
from app.services.retrieval_service import RetrievalService


def test_qa_service_returns_insufficient_when_score_is_low() -> None:
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
    document = document_repo.upsert(
        Document(
            id=generate_id("doc"),
            source_id="src_1",
            external_doc_id="doc-1",
            title="无关文档",
            content_text="库存盘点流程说明。",
            content_hash="hash-1",
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
                token_count=5,
                metadata={"source_id": document.source_id, "doc_type": document.doc_type},
                embedding=embedding_service.embed(document.content_text),
                embedding_status=EmbeddingStatus.DONE,
            )
        ],
    )

    retrieval_service = RetrievalService(
        source_repo=source_repo,
        document_repo=document_repo,
        chunk_repo=chunk_repo,
        embedding_service=embedding_service,
    )
    qa_service = QaService(
        settings=Settings(SEARCH_SCORE_THRESHOLD=0.9, MIN_EVIDENCE_COUNT=1),
        retrieval_service=retrieval_service,
    )

    answer = qa_service.ask(
        question="退款多久到账",
        top_k=5,
        filters=SearchFilters(),
        acl_context=AclContext(),
    )

    assert answer.evidence_status == "INSUFFICIENT"
    assert answer.reason == "检索分数低于阈值"


def test_qa_service_returns_evidence_driven_answer_when_hits_are_enough() -> None:
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
    document = document_repo.upsert(
        Document(
            id=generate_id("doc"),
            source_id="src_1",
            external_doc_id="doc-1",
            title="退款文档",
            content_text="退款需要在七天内发起申请。",
            content_hash="hash-1",
            doc_type="faq",
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
                token_count=7,
                metadata={"source_id": document.source_id, "doc_type": document.doc_type},
                embedding=embedding_service.embed(document.content_text),
                embedding_status=EmbeddingStatus.DONE,
            )
        ],
    )

    retrieval_service = RetrievalService(
        source_repo=source_repo,
        document_repo=document_repo,
        chunk_repo=chunk_repo,
        embedding_service=embedding_service,
        min_score_threshold=0.05,
    )
    qa_service = QaService(
        settings=Settings(SEARCH_SCORE_THRESHOLD=0.05, MIN_EVIDENCE_COUNT=1),
        retrieval_service=retrieval_service,
    )

    answer = qa_service.ask(
        question="退款需要在七天内发起申请。",
        top_k=3,
        filters=SearchFilters(),
        acl_context=AclContext(),
    )

    assert answer.evidence_status == "SUFFICIENT"
    assert "根据知识库检索结果" in answer.answer
    assert len(answer.citations) == 1
    assert answer.citations[0].document.title == "退款文档"

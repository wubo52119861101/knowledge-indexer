from app.services.document_processor import DocumentProcessor


def test_split_text_generates_multiple_chunks() -> None:
    processor = DocumentProcessor(chunk_size=20, chunk_overlap=5)
    text = "第一段内容很长很长。\n\n第二段内容也很长很长。\n\n第三段继续补充。"

    chunks = processor.split_text(text)

    assert len(chunks) >= 2
    assert all(chunks)
    assert chunks[0] != chunks[-1]

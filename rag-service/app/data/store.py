import os

from langchain_community.vectorstores import FAISS

from .embedder import get_embedder


VECTORSTORE_PDF = None
pdf_path = "faiss_db/pdf"


def load_pdf_store():
    global VECTORSTORE_PDF
    if os.path.exists(f"{pdf_path}/index.faiss") and os.path.exists(f"{pdf_path}/index.pkl"):
        VECTORSTORE_PDF = FAISS.load_local(
            pdf_path,
            embeddings=get_embedder(),
            allow_dangerous_deserialization=True,
        )
        print("✅ VECTORSTORE_PDF 로드 완료")
    else:
        print("❌ VECTORSTORE_PDF 벡터화된 파일이 없습니다.")
    return VECTORSTORE_PDF


def save_pdf_store(docs):
    global VECTORSTORE_PDF
    VECTORSTORE_PDF = FAISS.from_documents(docs, get_embedder())
    os.makedirs(pdf_path, exist_ok=True)
    VECTORSTORE_PDF.save_local(pdf_path)


def search_pdf_store(prompt: str, top_k: int = 5):
    return VECTORSTORE_PDF.similarity_search_with_score(prompt, k=top_k)

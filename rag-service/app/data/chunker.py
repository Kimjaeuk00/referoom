from langchain_text_splitters import RecursiveCharacterTextSplitter


def chunk_paper(paper_text: str, filename: str):
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    return splitter.create_documents(
        [paper_text], metadatas=[{"source": filename}]
    )

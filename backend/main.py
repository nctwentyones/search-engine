from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from langchain_community.llms import Ollama
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
import pandas as pd
import shutil
import os
import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CHROMA_PATH = "chroma_db"
os.makedirs("uploads", exist_ok=True)
os.makedirs(CHROMA_PATH, exist_ok=True)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

OLLAMA_BASE_URL = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")

embeddings = OllamaEmbeddings(model="nomic-embed-text", base_url=OLLAMA_BASE_URL, num_thread=4)
llm = Ollama(model="llama3.2", base_url=OLLAMA_BASE_URL)

vector_db = Chroma(persist_directory=CHROMA_PATH, embedding_function=embeddings)

def count_word_in_file(file_name: str, target_word: str):
    file_path = f"uploads/{file_name}"
    if not os.path.exists(file_path):
        return 0
    
    text = ""
    if file_name.endswith(".pdf"):
        loader = PyPDFLoader(file_path)
        docs = loader.load()
        text = " ".join([d.page_content for d in docs])
    elif file_name.endswith(".txt"):
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
    elif file_name.endswith(".xlsx"):
        df = pd.read_excel(file_path)
        text = " ".join(df.astype(str).values.flatten())
    
    count = len(re.findall(rf'\b{re.escape(target_word)}\b', text, re.IGNORECASE))
    return count

@app.get("/files")
async def list_files():
    allowed_extensions = {".pdf", ".txt", ".xlsx", ".docx"}
    all_files = os.listdir("uploads")
    filtered_files = [
        f for f in all_files 
        if os.path.isfile(os.path.join("uploads", f)) and 
           os.path.splitext(f)[1].lower() in allowed_extensions
    ]
    
    return {"files": filtered_files}

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    file_path = f"uploads/{file.filename}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    docs = []
    if file.filename.endswith(".pdf"):
        docs = PyPDFLoader(file_path).load()
    elif file.filename.endswith(".txt"):
        docs = TextLoader(file_path).load()
    elif file.filename.endswith(".xlsx"):
        df = pd.read_excel(file_path)
        docs = [Document(page_content=df.to_string(), metadata={"source": file.filename})]
    else:
        if os.path.exists(file_path):
            os.remove(file_path)
       
        raise HTTPException(
            status_code=415, 
            detail="Format tidak didukung. Gunakan PDF, TXT, atau Excel."
        )
    
    for doc in docs:
        doc.metadata["source"] = file.filename

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    splits = text_splitter.split_documents(docs)
    
    vector_db.add_documents(splits)
        
    return {"message": f"File {file.filename} berhasil diunggah dan dipelajari!"}

@app.post("/ask")
async def ask_ai(question: dict):
    tanya = question.get("query")
    if not tanya:
        raise HTTPException(status_code=400, detail="Query is required")

    tanya_lower = tanya.lower()

    
    # INTENT DETECTION (RULE-BASED, BUKAN LLM)

    if re.search(r"\b(hitung|jumlah|total|berapa kali)\b", tanya_lower):
        intent = "HITUNG"
    else:
        intent = "RAG"

    # LOGIC UNTUK HITUNG 
    if intent == "HITUNG":
        try:
            word_match = re.search(r"kata\s+['\"]?(\w+)['\"]?", tanya_lower)
            file_match = re.search(r"di\s+file\s+([^\s]+)", tanya_lower)

            if not word_match:
                return {"answer": "Format tidak dikenali. Gunakan contoh: 'Hitung kata AI di file laporan.pdf'", "sources": []}

            target_word = word_match.group(1)

            if file_match:
                files_to_scan = [file_match.group(1)]
            else:
                files_to_scan = [
                    f for f in os.listdir("uploads")
                    if os.path.isfile(f"uploads/{f}")
                ]

            total_count = 0
            detail_per_file = []

            for f_name in files_to_scan:
                if os.path.exists(f"uploads/{f_name}"):
                    c = count_word_in_file(f_name, target_word)
                    total_count += c
                    detail_per_file.append(f"{f_name}: {c}")

            return {
                "answer": f"Kata '{target_word}' muncul {total_count} kali.",
                "detail": detail_per_file,
                "sources": files_to_scan
            }

        except Exception as e:
            return {"answer": f"Terjadi kesalahan: {str(e)}", "sources": []}

    
    # LOGICNYA RAG (SEMANTIC SEARCH + LLM)
    try:
        docs_with_score = vector_db.similarity_search_with_relevance_scores(tanya, k=5)

        docs = [doc for doc, score in docs_with_score if score > 0.05]

        if not docs:
            return {"answer": "Informasi tidak ditemukan di dokumen.", "sources": []}

        konteks = "\n\n".join(
            [f"--- Sumber: {d.metadata.get('source')} ---\n{d.page_content}" for d in docs]
        )

        sumber_file = list(set([d.metadata.get("source", "Unknown") for d in docs]))

        rag_prompt = f"""
        Anda adalah asisten AI perusahaan yang profesional dan akurat.
        Gunakan HANYA data dokumen di bawah ini untuk menjawab pertanyaan.

        DATA DOKUMEN:
        {konteks}

        Pertanyaan: {tanya}

        Jawaban (sebutkan nama dokumen yang dirujuk):
        """

        response = llm.invoke(rag_prompt)

        return {"answer": response, "sources": sumber_file}

    except Exception as e:
        return {"answer": f"Error sistem: {str(e)}", "sources": []}
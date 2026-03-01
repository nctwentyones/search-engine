from fastapi import FastAPI, UploadFile, File
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
        return {"error": "Format tidak didukung. Gunakan PDF, TXT, atau Excel."}
    
    for doc in docs:
        doc.metadata["source"] = file.filename

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    splits = text_splitter.split_documents(docs)
    
    vector_db.add_documents(splits)
        
    return {"message": f"File {file.filename} berhasil diunggah dan dipelajari!"}

@app.post("/ask")
async def ask_ai(question: dict):
    tanya = question.get("query")
    try:
        docs_with_score = vector_db.similarity_search_with_relevance_scores(tanya, k=5)
        docs = [doc for doc, score in docs_with_score if score > 0.35]
    except Exception:
        return {"answer": "Database belum siap atau kosong. Silakan upload file dulu.", "sources": []}

    if not docs:
        return {"answer": "Saya tidak menemukan informasi terkait di dokumen yang ada.", "sources": []}
    
    konteks = "\n\n".join([f"--- Sumber: {d.metadata.get('source')} ---\n{d.page_content}" for d in docs])
    sumber_file = list(set([d.metadata.get("source", "Tidak diketahui") for d in docs]))
    
    prompt = (
        f"Anda adalah asisten AI perusahaan yang profesional.\n"
        f"Gunakan data di bawah ini untuk menjawab pertanyaan. Jika pertanyaan merujuk pada topik dokumen tertentu, "
        f"berikan jawaban hanya dari sumber yang paling relevan dan abaikan dokumen lain yang tidak nyambung.\n\n"
        f"DATA DOKUMEN:\n{konteks}\n\n"
        f"Pertanyaan: {tanya}\n"
        f"Jawaban (sebutkan nama dokumen yang dirujuk):"
    )
    response = llm.invoke(prompt)
    
    return {"answer": response, "sources": sumber_file}
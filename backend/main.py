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
        docs = vector_db.similarity_search(tanya, k=3)
    except Exception:
        return {"answer": "Database belum siap atau kosong. Silakan upload file dulu.", "sources": []}

    if not docs:
        return {"answer": "Saya tidak menemukan informasi terkait di dokumen yang ada.", "sources": []}
    
    konteks = "\n".join([d.page_content for d in docs])
    
    sumber_file = list(set([d.metadata.get("source", "Tidak diketahui") for d in docs]))
    
    prompt = f"Gunakan data berikut untuk menjawab pertanyaan.\n\nData Perusahaan:\n{konteks}\n\nPertanyaan: {tanya}\nJawaban:"
    response = llm.invoke(prompt)
    
    return {"answer": response, "sources": sumber_file}
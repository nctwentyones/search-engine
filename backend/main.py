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

# Buka akses untuk Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("uploads", exist_ok=True)
# INI PENTING: Membuat folder 'uploads' bisa diakses dari browser (seperti Google Drive)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Mengambil alamat Ollama dari environment variable yang kita set di docker-compose
OLLAMA_BASE_URL = os.getenv("OLLAMA_HOST", "http://ollama:11434")

embeddings = OllamaEmbeddings(model="llama3.2", base_url=OLLAMA_BASE_URL)
llm = Ollama(model="llama3.2", base_url=OLLAMA_BASE_URL)

vector_db = Chroma(persist_directory="uploads", embedding_function=embeddings)

@app.get("/files")
async def list_files():
    # Mengambil daftar file yang sudah diupload
    files = os.listdir("uploads")
    return {"files": files}

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
    
    # Tambahkan metadata nama file agar AI tahu sumbernya
    for doc in docs:
        doc.metadata["source"] = file.filename

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    splits = text_splitter.split_documents(docs)
    
    global vector_db
    if vector_db is None:
        vector_db = Chroma.from_documents(documents=splits, embedding=embeddings)
    else:
        vector_db.add_documents(splits)
        
    return {"message": f"File {file.filename} berhasil diunggah dan dipelajari!"}

@app.post("/ask")
async def ask_ai(question: dict):
    tanya = question.get("query")
    if vector_db is None:
        return {"answer": "Belum ada dokumen. Silakan upload file dulu.", "sources": []}
    
    # Cari 3 teks paling mirip
    docs = vector_db.similarity_search(tanya, k=3)
    konteks = "\n".join([d.page_content for d in docs])
    
    # Ambil nama file sumber (menghilangkan duplikat)
    sumber_file = list(set([d.metadata.get("source", "Tidak diketahui") for d in docs]))
    
    prompt = f"Gunakan data berikut untuk menjawab pertanyaan.\n\nData Perusahaan:\n{konteks}\n\nPertanyaan: {tanya}\nJawaban:"
    response = llm.invoke(prompt)
    
    return {"answer": response, "sources": sumber_file}
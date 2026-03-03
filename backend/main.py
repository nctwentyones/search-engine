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
    docs = []

    intent_prompt = (
        "TUGAS: Tentukan apakah user ingin MENGHITUNG JUMLAH KATA atau MEMBACA ISI/DISKUSI.\n\n"
        f"PERTANYAAN USER: '{tanya}'\n\n"
        "KLASIFIKASI:\n"
        "- Jawab 'HITUNG' jika user bertanya: 'berapa jumlah', 'hitung ada berapa', 'berapa kali muncul'.\n"
        "- Jawab 'RAG' jika user bertanya: 'apa isi', 'jelaskan', 'ringkas', 'siapa', 'kapan', atau pertanyaan diskusi lainnya.\n\n"
        "JAWABAN:"
    )
    is_counting_raw = llm.invoke(intent_prompt).strip().upper()
    is_counting = "HITUNG" in is_counting_raw

    if is_counting:
        extraction_prompt = (
            f"TUGAS: Ekstrak subjek dan file dari: '{tanya}'\n"
            "HANYA balas dengan format: subjek|file\n"
            "CONTOH: halo|halo1.txt\n"
            "Jangan beri penjelasan atau kode Python. Beri hasilnya saja."
            "peraturan penting"
            "1. Tentukan subjek kata yang dicari. Perhatikan jumlah hurufnya (misal: 'halo' vs 'hallo').\n"
            "2. Berikan hasil dalam format: subjek|file\n"
            "3. JANGAN mengulang jawaban dari percakapan sebelumnya jika subjeknya berbeda.\n"
            "HANYA balas dengan format: subjek|file"
        )
        extraction_result = llm.invoke(extraction_prompt).strip()
        
        try:
            clean_res = extraction_result.split("\n")[-1]
            
            if "|" in clean_res:
                target_word, target_file = clean_res.split("|")
                
                target_word = target_word.strip().replace('"', '').replace("'", "")
                target_file = target_file.strip().replace('"', '').replace("'", "").replace(" ", "")

                if target_word.lower() in ["subjek", "kata", "target"]:
                    raise ValueError("LLM gagal mengekstrak kata asli")
                
                if target_file.endswith("."): 
                    target_file = target_file[:-1]
                
                files_to_scan = os.listdir("uploads") if target_file.upper() == "ALL" else [target_file]

                total_count = 0
                detail_per_file = []
                for f_name in files_to_scan:
                    if os.path.exists(f"uploads/{f_name}"):
                        c = count_word_in_file(f_name, target_word)
                        total_count += c
                        detail_per_file.append(f"{f_name}: {c}")

                return {
                    "answer": f"Berdasarkan pencarian langsung di file, total kata '{target_word}' muncul sebanyak {total_count} kali.",
                    "detail": detail_per_file,
                    "sources": files_to_scan
                }
        except Exception as e:
            print(f"DEBUG ERROR: {e} | Raw Result: {extraction_result}")
            pass    
    try:
        docs_with_score = vector_db.similarity_search_with_relevance_scores(tanya, k=10)
        
        for doc, score in docs_with_score:
            print(f"File: {doc.metadata.get('source')} | Score: {score}")

        docs = [doc for doc, score in docs_with_score if score > 0.1]
    
        if not docs and docs_with_score:
            docs = [doc for doc, score in docs_with_score[:3]]
            
    except Exception as e:
        print(f"Error: {e}")
        return {"answer": "Database belum siap atau kosong. Silakan upload file dulu.", "sources": []}
    
    if not docs:
        return {"answer": "Saya tidak menemukan informasi terkait di dokumen yang ada.", "sources": []}
    
    konteks = "\n\n".join([f"--- Sumber: {d.metadata.get('source')} ---\n{d.page_content}" for d in docs])
    sumber_file = list(set([d.metadata.get("source", "Tidak diketahui") for d in docs]))
    
    prompt = (
        f"Anda adalah asisten AI perusahaan yang profesional.\n"
        f"Anda adalah sistem AI yang sangat teliti. gunakan data di bawah untuk menjawab.\n "
        f"TUGAS: Jika user meminta untuk menghitung kata atau mencari informasi spesifik,"
        f"periksa data dokumen dengan saksama.\n\n"
        f"Jika user meminta menghitung jumlah kata tertentu, hitunglah secara teliti hanya dari teks yang disediakan di atas.\n"
        f"Diberikan potongan teks dari dokumen '{sumber_file}' di bawah ini.\n"
        f"Tugas Anda: Jawab pertanyaan user. Jika pertanyaan menanyakan isi dokumen, berikan ringkasan berdasarkan potongan teks yang tersedia.\n\n"
        f"Jika ada informasi yang mendekati atau terkait, jelaskan dengan detail.\n\n"
        f"DATA DOKUMEN:\n{konteks}\n\n"
        f"Pertanyaan: {tanya}\n"
        f"Jawaban (sebutkan nama dokumen yang dirujuk):"
    )
    print(f"Konteks: {konteks}")
    response = llm.invoke(prompt)
    
    return {"answer": response, "sources": sumber_file, "konteks": konteks}
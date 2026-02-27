"use client"
import { useState, useEffect } from 'react'

export default function GeminiClone() {
  const [chat, setChat] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [files, setFiles] = useState([]);
  
  // State baru untuk progress upload
  const [isUploading, setIsUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState("");

  const fetchFiles = async () => {
    try {
      const res = await fetch("http://localhost:8000/files");
      const data = await res.json();
      if (data.files) {
        setFiles(data.files);
      }
    } catch (err) {
      console.error("Gagal mengambil daftar file");
    }
  };

  useEffect(() => {
    fetchFiles();
  }, []);

  const handleUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);
    
    // Mulai indikator loading upload
    setIsUploading(true);
    setUploadStatus(`Mengunggah ${file.name}...`);

    try {
      const res = await fetch("http://localhost:8000/upload", { 
        method: "POST", 
        body: formData 
      });
      
      if (res.ok) {
        setUploadStatus("AI sedang mempelajari dokumen...");
        // Beri jeda sedikit agar user bisa melihat status "mempelajari"
        setTimeout(async () => {
          await fetchFiles();
          setIsUploading(false);
          setUploadStatus("");
        }, 3000);
      } else {
        throw new Error("Gagal");
      }
    } catch (error) {
      alert("Gagal mengunggah file.");
      setIsUploading(false);
      setUploadStatus("");
    }
  };

  const sendQuery = async () => {
    if (!input.trim() || loading) return;
    
    const newChat = [...chat, { role: "user", text: input }];
    setChat(newChat);
    const userQuery = input;
    setInput("");
    setLoading(true);

    try {
      const res = await fetch("http://localhost:8000/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: userQuery }),
      });
      const data = await res.json();
      
      let answerText = data.answer;
      if (data.sources && data.sources.length > 0) {
        answerText += `\n\n(Sumber data: ${data.sources.join(", ")})`;
      }
      
      setChat([...newChat, { role: "ai", text: answerText }]);
    } catch (error) {
      setChat([...newChat, { role: "ai", text: "Maaf, gagal terhubung ke server AI." }]);
    }
    setLoading(false);
  }

  return (
    <div className="flex h-screen bg-[#131314] text-white font-sans text-sm md:text-base">
      {/* Sidebar - Ala Google Drive */}
      <div className="w-64 bg-[#1e1f20] p-4 flex flex-col gap-4 border-r border-gray-800">
        <h2 className="text-xl font-bold px-2 text-gray-200">Data Perusahaan</h2>
        
        <div className="flex flex-col gap-2">
          <label className={`relative overflow-hidden ${isUploading ? 'bg-gray-700' : 'bg-[#1a73e8] hover:bg-blue-600'} cursor-pointer text-center py-2.5 rounded-full text-sm font-semibold transition-all`}>
            {isUploading ? (
              <span className="flex items-center justify-center gap-2">
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                Proses...
              </span>
            ) : (
              "+ Upload File Baru"
            )}
            <input 
              type="file" 
              className="hidden" 
              onChange={handleUpload} 
              accept=".pdf,.txt,.xlsx" 
              disabled={isUploading}
            />
            {/* Progress Bar Animation */}
            {isUploading && (
              <div className="absolute bottom-0 left-0 h-1 bg-blue-400 animate-[loading_2s_ease-in-out_infinite]" style={{width: '100%'}}></div>
            )}
          </label>
          {uploadStatus && (
            <p className="text-[11px] text-blue-400 px-2 animate-pulse font-medium">{uploadStatus}</p>
          )}
        </div>
        
        <div className="mt-4 flex-1 overflow-y-auto">
          <h3 className="text-xs font-semibold text-gray-500 px-2 mb-2 uppercase tracking-wider">File Tersimpan</h3>
          <ul className="flex flex-col gap-1">
            {files.map((file, idx) => (
              <li key={idx}>
                <a 
                  href={`http://localhost:8000/uploads/${file}`} 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="block px-3 py-2 text-xs text-gray-300 hover:bg-gray-800 rounded-lg truncate"
                >
                  📄 {file}
                </a>
              </li>
            ))}
            {files.length === 0 && !isUploading && (
              <p className="text-xs text-gray-500 px-2 italic">Belum ada file.</p>
            )}
          </ul>
        </div>
      </div>
      
      {/* Area Chat Utama - Ala Gemini */}
      <div className="flex-1 flex flex-col relative">
        <div className="flex-1 overflow-y-auto p-6 md:p-10 pb-32">
          {chat.length === 0 ? (
             <div className="h-full flex flex-col items-center justify-center text-center">
                <span className="text-6xl mb-4 animate-bounce">✨</span>
                <h1 className="text-3xl md:text-4xl font-semibold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-purple-500">
                  Halo Dylan, mau cari data apa hari ini?
                </h1>
                <p className="text-gray-500 mt-3 text-sm">Upload file di samping untuk mulai bertanya pada AI.</p>
             </div>
          ) : (
            chat.map((msg, index) => (
              <div key={index} className={`mb-6 flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[85%] md:max-w-[75%] p-4 rounded-2xl whitespace-pre-wrap ${msg.role === "user" ? "bg-[#303134] text-gray-100 rounded-tr-none" : "bg-transparent text-gray-200"}`}>
                  {msg.role === "ai" && (
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-blue-400">✨</span>
                      <span className="font-bold text-sm text-blue-400 uppercase tracking-tight">AI Perusahaan</span>
                    </div>
                  )}
                  {msg.text}
                </div>
              </div>
            ))
          )}
          {loading && (
            <div className="text-gray-400 animate-pulse mt-4 flex items-center gap-3 px-4">
              <div className="w-2 h-2 bg-blue-400 rounded-full animate-ping"></div>
              <span className="text-sm italic">Sedang memproses jawaban...</span>
            </div>
          )}
        </div>

        {/* Input Bar */}
        <div className="absolute bottom-0 w-full p-4 md:p-6 bg-gradient-to-t from-[#131314] via-[#131314] to-transparent flex justify-center">
          <div className="w-full max-w-3xl bg-[#1e1f20] rounded-[28px] p-1.5 px-6 flex items-center shadow-2xl border border-gray-700 focus-within:border-gray-500 transition-all">
            <input 
              className="bg-transparent flex-1 outline-none py-3 text-gray-200 placeholder-gray-500" 
              placeholder="Tanya apapun tentang dokumen perusahaan..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && sendQuery()}
            />
            <button 
              onClick={sendQuery} 
              disabled={loading}
              className={`p-2 ml-2 ${loading ? 'opacity-50' : 'bg-blue-600 hover:bg-blue-700'} rounded-full transition-all text-white w-10 h-10 flex items-center justify-center shadow-lg`}
            >
              🚀
            </button>
          </div>
        </div>
      </div>

      <style jsx global>{`
        @keyframes loading {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(100%); }
        }
      `}</style>
    </div>
  )
}
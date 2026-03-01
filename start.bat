@echo off
echo ==========================================
echo    STARTING COMPANY AI PROJECT (NO NET)
echo ==========================================

echo [1/3] Menjalankan Ollama...
cd ollama
docker-compose up -d
cd ..

echo [2/3] Menjalankan Backend (FastAPI)...
cd backend
docker-compose up -d
cd ..

echo [3/3] Menjalankan Frontend (Next.js)...
cd frontend
docker-compose up -d
cd ..

echo ------------------------------------------
echo Backend  : http://localhost:8000
echo Frontend : http://localhost:3000
echo Ollama   : http://localhost:11434
echo ------------------------------------------
pause
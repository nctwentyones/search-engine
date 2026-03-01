@echo off
echo ==========================================
echo    STOPPING COMPANY AI PROJECT...
echo ==========================================

echo [1/3] Mematikan Frontend...
cd frontend
docker compose down
cd ..

echo [2/3] Mematikan Backend...
cd backend
docker compose down
cd ..

echo [3/3] Mematikan Ollama...
cd ollama
docker compose down
cd ..

echo ------------------------------------------
echo SEMUA LAYANAN TELAH BERHENTI.
echo ------------------------------------------
pause
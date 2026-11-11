@echo off
rem Hap robotin e kriptove si aplikacion ne shfletues (dopio-klik).
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Po pergatitet mjedisi per here te pare...
  py -3.12 -m venv .venv || goto :error
  .venv\Scripts\python -m pip install -r requirements.txt || goto :error
)
start "" cmd /c "timeout /t 5 >nul & start http://localhost:8510"
.venv\Scripts\python -m streamlit run crypto_app.py --server.port 8510 --server.headless true --browser.gatherUsageStats false
goto :eof
:error
echo Instalimi deshtoi. Kontrollo qe Python 3.12 eshte i instaluar.
pause

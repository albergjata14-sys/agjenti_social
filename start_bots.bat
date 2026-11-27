@echo off
rem Hap ekipin e 6 boteve (pamja 3D) ne shfletues. Roboti i kriptove nuk preket.
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist .venv-bots\Scripts\python.exe (
  echo Po pergatitet mjedisi i boteve per here te pare...
  py -3.12 -m venv .venv-bots || goto :error
  .venv-bots\Scripts\python -m pip install -r bots\requirements.txt || goto :error
)
start "" cmd /c "timeout /t 5 >nul & start http://localhost:8520"
.venv-bots\Scripts\python -m streamlit run bots_app.py --server.port 8520 --server.headless true --browser.gatherUsageStats false --theme.base dark
goto :eof
:error
echo Instalimi deshtoi. Kontrollo qe Python 3.12 eshte i instaluar.
pause

@echo off
rem Ekipi i robotit punon 24 ore, 7 dite. Nese ndalet nga nje gabim (p.sh. pa internet), riniset vete.
rem Per ta ndalur: mbyll kete dritare, ose shtyp "Ndalo robotin" te paneli.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3.12 -m venv .venv || goto :error
  .venv\Scripts\python -m pip install -r requirements.txt || goto :error
)
:loop
.venv\Scripts\python -m crypto_bot nis --ekip
if errorlevel 1 (
  echo Roboti u ndal nga nje gabim ^(%date% %time%^). Riniset pas 30 sekondash...
  timeout /t 30 /nobreak >nul
  goto loop
)
echo Roboti u ndal.
pause
goto :eof
:error
echo Instalimi deshtoi. Kontrollo qe Python 3.12 eshte i instaluar.
pause

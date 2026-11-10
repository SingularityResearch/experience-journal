@echo off
rem The journal's fusion on two simulated weeks: a "why" table and how the layers compare (journal\tools\demo_fusion.py).
rem Needs Python 3.12 with numpy (python -m pip install -r journal\requirements.txt). Simulated people only.
setlocal
set "PY="
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY set "PY=python"
%PY% "%~dp0journal\tools\demo_fusion.py"
pause

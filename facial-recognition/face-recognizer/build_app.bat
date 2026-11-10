@echo off
cd /d "%~dp0"
title Build FaceRecognizer.exe
rem Builds FaceRecognizer.exe (app.py: tracker + labeling tool in one window) next to this file.
rem The .exe carries the code and pages only; it uses the models\ and data\ folders beside it.
set "PY="
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY (
  echo Python 3.12 is not installed yet. Double-click setup.bat first, then run this again.
  pause
  exit /b 1
)
%PY% -m pip install -q -r "%~dp0requirements-build.txt" || goto :failed
rem The build itself is described once, in build_exe.py (CI runs the same script)
%PY% build_exe.py || goto :failed
echo.
echo Built FaceRecognizer.exe. Keep it in this folder: it uses models\ and data\ beside it.
exit /b 0
:failed
echo.
echo The build failed; see the messages above.
pause
exit /b 1

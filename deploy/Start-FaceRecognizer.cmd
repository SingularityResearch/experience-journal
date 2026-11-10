@echo off
rem Starts this test build's FaceRecognizer.exe with the test folders, never your own photo library:
rem   models and data in   <test folder>\face-root   (FACE_ROOT)
rem   private files in     <test folder>\face-home   (FACE_HOME: keys, alerts, presence log, window storage)
rem   ports 9764-9766      (FACE_PORTS), so it runs beside your usual copy on 8764-8766
rem Installed by deploy_local.ps1, the test folder is two levels up (builds\<commit>\ is this build). Unzipped on its
rem own, the folders are made beside this file.
setlocal
set "BASE=%~dp0..\.."
if not exist "%BASE%\face-root" set "BASE=%~dp0."
set "FACE_ROOT=%BASE%\face-root"
set "FACE_HOME=%BASE%\face-home"
if not defined FACE_PORTS set "FACE_PORTS=9764"
if not exist "%FACE_ROOT%" mkdir "%FACE_ROOT%"
if not exist "%FACE_HOME%" mkdir "%FACE_HOME%"
start "" "%~dp0FaceRecognizer.exe"

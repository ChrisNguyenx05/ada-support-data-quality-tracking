@echo off
set "PY=C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%PY%" (
  "%PY%" app.py
) else (
  python app.py
)

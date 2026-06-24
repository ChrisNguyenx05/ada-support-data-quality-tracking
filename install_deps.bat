@echo off
set "PY=C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%PY%" (
  "%PY%" -m pip install -r requirements.txt
) else (
  python -m pip install -r requirements.txt
)

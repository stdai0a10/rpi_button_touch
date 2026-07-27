@ECHO OFF

cd /d %~dp0

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

"%PYTHON_EXE%" -m app.command.service --host 127.0.0.1 --port 8000 --reload

@ECHO OFF

cd /d %~dp0

python -m app.command.service --host 127.0.0.1 --port 8000 --reload

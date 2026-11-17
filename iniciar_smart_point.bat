@echo off
setlocal
cd /d "%~dp0"

rem Altere esta porta se o Arduino estiver em outra COM.
set "PORTA_ARDUINO=COM3"

if not exist ".venv\Scripts\python.exe" (
    echo ERRO: Python do projeto nao encontrado em .venv\Scripts\python.exe.
    echo Consulte o README para configurar o ambiente virtual.
    pause
    exit /b 1
)

echo Iniciando o backend e a ponte na porta %PORTA_ARDUINO%...
echo Mantenha as duas janelas abertas durante o uso.
start "Quem Faz - Backend" /D "%~dp0" cmd /k ".venv\Scripts\python.exe -m uvicorn app.api:app --host 127.0.0.1 --port 8000"
start "Quem Faz - Ponte Arduino" /D "%~dp0" cmd /k ".venv\Scripts\python.exe -m app.bridge --porta %PORTA_ARDUINO%"
echo Interface: http://127.0.0.1:8000
endlocal

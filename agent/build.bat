@echo off
REM ============================================================
REM build.bat — Compilación del agente EHUkene con PyInstaller
REM
REM Requisitos:
REM   - Windows 64 bits
REM   - Python 64 bits instalado y en el PATH
REM   - pip install -r requirements.txt ejecutado previamente
REM
REM Uso:
REM   build.bat
REM
REM Resultado:
REM   dist\agent.exe  — ejecutable autocontenido listo para despliegue
REM ============================================================

setlocal

REM Directorio donde está este script (raíz del proyecto agent/)
set ROOT=%~dp0
cd /d "%ROOT%"

echo.
echo === EHUkene Agent — Build ===
echo Directorio: %ROOT%
echo.

REM ── Verificar Python 64 bits ─────────────────────────────────────────────
echo [1/4] Verificando Python...
python -c "import struct; assert struct.calcsize('P') == 8, 'ERROR: Se requiere Python 64 bits'"
if errorlevel 1 (
    echo.
    echo ERROR: Se requiere Python 64 bits. El ejecutable compilado en 32 bits
    echo        provoca fallos WMI en root\WMI en entornos corporativos.
    exit /b 1
)
echo        OK - Python 64 bits detectado.

REM ── Verificar PyInstaller ────────────────────────────────────────────────
echo [2/4] Verificando PyInstaller...
pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo        PyInstaller no encontrado. Instalando...
    pip install pyinstaller
    if errorlevel 1 (
        echo ERROR: No se pudo instalar PyInstaller.
        exit /b 1
    )
)
echo        OK - PyInstaller disponible.

REM ── Limpiar builds anteriores ────────────────────────────────────────────
echo [3/4] Limpiando builds anteriores...
if exist dist\agent.exe (
    del /f /q dist\agent.exe
    echo        dist\agent.exe eliminado.
)
if exist build\ (
    rmdir /s /q build
    echo        Directorio build\ eliminado.
)

REM ── Compilar ─────────────────────────────────────────────────────────────
echo [4/4] Compilando agent.exe...
echo.
pyinstaller agent.spec

if errorlevel 1 (
    echo.
    echo ============================================================
    echo ERROR: La compilacion fallo. Revisar el output anterior.
    echo ============================================================
    exit /b 1
)

REM ── Resultado ────────────────────────────────────────────────────────────
echo.
echo ============================================================
echo BUILD COMPLETADO
echo.
echo Ejecutable : %ROOT%dist\agent.exe
for %%A in (dist\agent.exe) do echo Tamanio    : %%~zA bytes
echo.
echo Proximos pasos:
echo   1. Copiar dist\agent.exe al paquete de Ivanti EPM
echo   2. Incluir config.json configurado por equipo
echo   3. Configurar Task Scheduler para lanzar agent.exe en inicio de sesion
echo ============================================================

endlocal

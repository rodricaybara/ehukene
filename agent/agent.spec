# -*- mode: python ; coding: utf-8 -*-
#
# agent.spec — Configuración de empaquetado PyInstaller para EHUkene Agent
#
# Genera: dist/agent.exe
#
# Uso:
#   pyinstaller agent.spec
#
# Requisitos:
#   - Windows 64 bits
#   - Python 64 bits
#   - pip install pyinstaller
#
# La compilación debe hacerse SIEMPRE en Windows 64 bits.
# Un ejecutable compilado en 32 bits provocará fallos WMI en root\WMI.

import os

# Directorio raíz del proyecto (donde está este .spec)
ROOT = os.path.dirname(os.path.abspath(SPEC))

# ---------------------------------------------------------------------------
# Análisis de dependencias
# ---------------------------------------------------------------------------
a = Analysis(
    # Punto de entrada del agente
    scripts=[os.path.join(ROOT, 'core', 'main.py')],

    # Rutas donde PyInstaller buscará módulos importados
    pathex=[
        ROOT,
        os.path.join(ROOT, 'core'),
        os.path.join(ROOT, 'plugins'),
    ],

    # Dependencias binarias adicionales (ninguna en este caso)
    binaries=[],

    # Ficheros de datos a incluir en el ejecutable
    # Formato: (ruta_origen, ruta_destino_dentro_del_exe)
    datas=[
        # Plugins Python — se cargan dinámicamente en runtime
        (os.path.join(ROOT, 'plugins', '*.py'), 'plugins'),

        # Configuración de targets de software
        # Nota: config.json NO se incluye en el .exe — se despliega por separado
        # para permitir configuración por equipo sin recompilar.
        (os.path.join(ROOT, 'config', 'software_targets.json'), 'config'),
    ],

    # Imports ocultos que PyInstaller no detecta automáticamente por ser
    # cargados dinámicamente (plugin_loader usa importlib.util)
    hiddenimports=[
        'core.config',
        'core.logger',
        'core.collector',
        'core.sender',
        'core.plugin_loader',
        # Módulos estándar usados por los plugins
        'winreg',
        'glob',
        'subprocess',
        'threading',
        'ssl',
        'html',
        'html.parser',
    ],

    # Ficheros de hooks adicionales (ninguno necesario)
    hookspath=[],
    hooksconfig={},

    # Ficheros de runtime hooks (ninguno necesario)
    runtime_hooks=[],

    # Módulos a excluir explícitamente para reducir el tamaño del ejecutable
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'PIL',
        'PyQt5',
        'PyQt6',
        'wx',
        'test',
        'unittest',
    ],

    # Cifrado del bytecode (no necesario en POC)
    cipher=None,
    noarchive=False,
)

# ---------------------------------------------------------------------------
# Empaquetado de archivos Python compilados
# ---------------------------------------------------------------------------
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# ---------------------------------------------------------------------------
# Generación del ejecutable
# ---------------------------------------------------------------------------
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],

    # Nombre del ejecutable final
    name='agent',

    # Sin consola visible al ejecutarse desde Task Scheduler.
    # NOTA: Puesto a True temporalmente para diagnóstico.
    # Cambiar a False para el build de producción.
    console=True,

    # Icono del ejecutable (opcional — descomentar si se dispone de .ico)
    # icon=os.path.join(ROOT, 'assets', 'ehukene.ico'),

    # Un único fichero .exe autocontenido (--onefile)
    # Todos los ficheros se extraen a un directorio temporal en runtime.
    # Alternativa: onedir=True genera una carpeta en lugar de un único .exe,
    # más rápido de arrancar pero más complejo de desplegar.
    upx=False,           # UPX comprime el exe pero puede disparar antivirus corporativos
    upx_exclude=[],
    strip=False,
    runtime_tmpdir=None,

    # Manifiesto Windows para solicitar privilegios de administrador.
    # El agente necesita admin para powercfg /batteryreport y Prefetch.
    uac_admin=True,

    # Metadatos del ejecutable (visibles en Propiedades → Detalles en Windows)
    version_file=os.path.join(ROOT, 'version_info.txt') if os.path.exists(
        os.path.join(ROOT, 'version_info.txt')
    ) else None,
)

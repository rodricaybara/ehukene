# EHUkene Agent — Guía de despliegue

## Estructura del paquete Ivanti

El paquete de despliegue contiene exactamente estos ficheros:

```
ehukene_agent_v1.0.0\
├── agent.exe                        ← Ejecutable compilado (PyInstaller)
├── config.json                      ← Configuración del agente
└── config\
    └── software_targets.json        ← Lista de software a monitorizar
```

> `config.json` NO está incluido dentro del `.exe`. Se despliega por separado
> para permitir actualizar la configuración sin recompilar el ejecutable.

---

## config.json — campos a configurar por entorno

```json
{
  "agent_version": "1.0.0",
  "auto_update": false,
  "enabled_plugins": ["battery", "software_usage", "boot_time"],
  "api_url": "https://ehukene.dominio.local/api",
  "api_key": "KEY_UNICA_POR_DISPOSITIVO",
  "retry_attempts": 3,
  "retry_wait_seconds": 30,
  "timeout_connect": 5,
  "timeout_read": 10,
  "data_dir": "C:\\ProgramData\\EHUkene"
}
```

**Importante:** `api_key` debe ser única por dispositivo. Generarla con el
endpoint `POST /api/devices/register` del backend antes del despliegue.

---

## Ruta de instalación en el endpoint

```
C:\Program Files\EHUkene\
├── agent.exe
├── config.json
└── config\
    └── software_targets.json
```

Los datos en runtime se escriben en:

```
C:\ProgramData\EHUkene\
├── agent.log       ← Log de ejecución (rotativo, máx. 3 × 5 MB)
└── last_run.json   ← Control de duplicados (fecha del último envío exitoso)
```

---

## Task Scheduler — configuración

Crear la tarea programada en cada endpoint como parte del paquete Ivanti:

| Parámetro | Valor |
|---|---|
| Nombre | `EHUkene Agent` |
| Trigger | Al inicio de sesión — cualquier usuario |
| Acción | `C:\Program Files\EHUkene\agent.exe` |
| Ejecutar como | Cuenta de servicio AD con privilegios de administrador local |
| Ejecutar con privilegios más altos | Sí |
| Frecuencia adicional | Una vez al día (el propio agente controla duplicados) |
| Si la tarea ya está en ejecución | No iniciar una nueva instancia |

### Comando para crear la tarea vía schtasks (incluir en el script Ivanti):

```batch
schtasks /create ^
  /tn "EHUkene Agent" ^
  /tr "\"C:\Program Files\EHUkene\agent.exe\"" ^
  /sc ONLOGON ^
  /ru "DOMINIO\svc_ehukene" ^
  /rp "PASSWORD" ^
  /rl HIGHEST ^
  /f
```

---

## Códigos de salida del agente

Ivanti puede usar estos códigos para clasificar el resultado de la ejecución:

| Código | Significado | Configurar en Ivanti como |
|---|---|---|
| `0` | Envío completado correctamente | Success |
| `1` | Error de configuración o ningún plugin cargado | Failed |
| `2` | Ya se ejecutó hoy — duplicado evitado | Success |
| `3` | Envío fallido tras todos los reintentos | Failed (reintentar) |

---

## Verificación post-despliegue

Tras el primer despliegue, verificar en el endpoint:

```
1. C:\Program Files\EHUkene\agent.exe  existe
2. C:\ProgramData\EHUkene\agent.log    existe y tiene entrada de inicio
3. C:\ProgramData\EHUkene\last_run.json existe (indica envío exitoso)
4. En el backend: GET /api/devices/{hostname} devuelve el dispositivo
```

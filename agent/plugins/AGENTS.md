# AGENTS.md — Plugins EHUkene

## 🧠 Contexto

Este directorio contiene plugins del agente EHUkene.

Cada plugin:
- Es un módulo Python independiente
- Implementa la función pública `collect() -> dict | None`
- Sigue estrictamente el estándar definido en:
  - ehukene_plugin_standard.md
  - ehukene_contratos.md

El plugin de referencia es: `battery.py`

---

## 🎯 Objetivo del agente

- Crear nuevos plugins siguiendo el estándar
- Modificar plugins existentes sin romper contrato
- Garantizar consistencia, resiliencia y tipado correcto

---

## 🧾 Uso del documento de referencia

Los estándares de plugins se encuentran en:

- docs/ehukene_plugin_standard.md
- docs/ehukene_contratos.md

## ⚠️ Regla obligatoria

Antes de crear o modificar un plugin:
1. - No asumir contratos de memoria

2. Leer completamente:
   - docs/ehukene_plugin_standard.md
   - docs/ehukene_contratos.md

3. Replicar la estructura del plugin de referencia:
   - agent/plugins/battery.py

Si hay conflicto:
→ El documento de contratos (`docs/ehukene_contratos.md`) es la fuente de verdad

## 📂 Archivos clave del proyecto

- docs/ehukene_plugin_standard.md → estándar de implementación
- docs/ehukene_contratos.md → definición de contratos (FUENTE DE VERDAD)
- agent/plugins/battery.py → implementación de referencia
---

## 🧩 Principios obligatorios

1. **Contrato estricto**
   - El dict devuelto debe contener EXACTAMENTE las claves del contrato
   - Nunca devolver dict parcial
   - Si no se puede cumplir → devolver `None`

2. **Aislamiento total**
   - No importar nada de `core/`
   - No depender de otros plugins
   - No acceder a red ni backend

3. **Resiliencia**
   - Nunca propagar excepciones
   - Todas las excepciones se capturan
   - Fallo = `None`, nunca crash

4. **Consistencia**
   - Seguir exactamente la estructura del estándar
   - Usar mismo estilo de logging, naming y organización

---

## ⚙️ Estructura obligatoria del plugin

Orden exacto del fichero:

1. Docstring de cabecera (contrato completo)
2. Imports (stdlib → terceros → nada de core)
3. Logger:
   ```python
   log = logging.getLogger(__name__)
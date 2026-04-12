# AGENTS.md

## 🧠 Principios de trabajo

1. Leer el código existente antes de modificar nada.
   - Buscar implementaciones similares.
   - Extender código existente en lugar de duplicarlo.

2. Respetar el comportamiento actual.
   - No romper funcionalidad existente.
   - No refactorizar fuera del alcance de la tarea.

3. Mantener consistencia.
   - Seguir patrones ya usados en el proyecto.
   - Usar la misma estructura y estilo de código.

4. Cambios atómicos.
   - Cada cambio debe ser completo y coherente.
   - Si afecta a varias capas (agent/backend/db), incluir todos los cambios necesarios.

---

## ⚙️ Reglas específicas del proyecto

### Sistema de plugins (AGENTE)

- Cada plugin debe:
  - Ser independiente
  - No romper el collector si falla
  - Capturar sus propias excepciones
  - Devolver un dict serializable

- No modificar plugins existentes salvo que sea necesario.

---

### Backend

- Validar siempre el payload recibido
- No confiar en datos del agente sin validación
- Mantener compatibilidad con payloads existentes

---

### Base de datos

- No romper esquema existente
- Si se añaden campos:
  - Mantener compatibilidad hacia atrás
  - Proponer migraciones si aplica

---

## 🧪 Testing

- Añadir tests para cualquier nueva funcionalidad
- No eliminar tests existentes
- Ejecutar:

```bash
pytest
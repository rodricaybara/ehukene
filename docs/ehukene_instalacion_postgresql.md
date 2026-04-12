# EHUkene — Instalación y configuración de PostgreSQL

**Entorno:** Ubuntu 22.04 / 24.04  
**Versión PostgreSQL:** 16 (repositorio oficial PGDG)  
**Fecha:** 2026-04-08

---

## 1. Instalación

Instalar desde el repositorio oficial de PostgreSQL (PGDG) para tener la versión 16 en lugar de la que incluye el sistema:

```bash
sudo apt install -y curl ca-certificates

curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
  | sudo gpg --dearmor -o /etc/apt/keyrings/postgresql.gpg

echo "deb [signed-by=/etc/apt/keyrings/postgresql.gpg] \
  https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
  | sudo tee /etc/apt/sources.list.d/pgdg.list

sudo apt update
sudo apt install -y postgresql-16

# Verificar que el servicio está activo
sudo systemctl status postgresql
```

---

## 2. Creación de la base de datos

PostgreSQL crea durante la instalación el usuario del sistema `postgres` y el rol de base de datos `postgres` con privilegios de superusuario. Todas las operaciones de administración inicial se realizan con ese usuario:

```bash
# Crear la base de datos
sudo -u postgres psql -c "CREATE DATABASE ehukene;"

# Verificar que se ha creado
sudo -u postgres psql -c "\l"
```

---

## 3. Aplicar el esquema

El fichero `ehukene_db_init.sql` contiene el esquema completo (tablas, índices, constraints y el rol de aplicación `ehukene_app`):

```bash
sudo -u postgres psql -d ehukene -f ehukene_db_init.sql
```

Verificar que las tablas se han creado correctamente:

```bash
sudo -u postgres psql -d ehukene -c "\dt"
```

Salida esperada:

```
              List of relations
 Schema |      Name       | Type  |  Owner
--------+-----------------+-------+----------
 public | agent_versions  | table | postgres
 public | battery_metrics | table | postgres
 public | boot_metrics    | table | postgres
 public | devices         | table | postgres
 public | software_usage  | table | postgres
 public | telemetry_raw   | table | postgres
```

---

## 4. Rol de aplicación

El script `ehukene_db_init.sql` crea automáticamente el rol `ehukene_app` con privilegios mínimos (solo las tablas necesarias, sin acceso a superusuario ni a otras bases de datos). Es el usuario que utiliza el backend FastAPI para conectarse.

**Cambiar la contraseña antes del primer uso:**

```bash
sudo -u postgres psql -d ehukene -c \
  "ALTER ROLE ehukene_app PASSWORD 'nueva_contraseña_segura';"
```

Verificar que el rol existe y puede conectarse:

```bash
psql -U ehukene_app -d ehukene -h localhost -c "\dt"
```

> Si solicita contraseña es que el rol funciona correctamente. Si falla con `peer authentication`, ver la sección 5.

---

## 5. Configuración de autenticación (`pg_hba.conf`)

Por defecto PostgreSQL usa autenticación `peer` para conexiones locales, lo que significa que el usuario del sistema operativo debe coincidir con el rol de base de datos. El backend FastAPI se ejecuta como `www-data`, no como `ehukene_app`, por lo que hay que permitir autenticación por contraseña (`scram-sha-256`) para conexiones desde `localhost`.

Editar `pg_hba.conf`:

```bash
sudo nano /etc/postgresql/16/main/pg_hba.conf
```

Añadir esta línea **antes** de las líneas existentes de `local` y `host`:

```
# EHUkene — permite conexión del backend por contraseña desde localhost
host    ehukene     ehukene_app     127.0.0.1/32     scram-sha-256
```

Recargar PostgreSQL para aplicar el cambio:

```bash
sudo systemctl reload postgresql
```

---

## 6. Cadena de conexión para el backend

Con la configuración anterior, la cadena de conexión que va en `/opt/ehukene/backend/.env` es:

```env
DATABASE_URL=postgresql+asyncpg://ehukene_app:TU_PASSWORD@127.0.0.1:5432/ehukene
```

> Usar `127.0.0.1` en lugar de `localhost` para forzar la conexión TCP (que usa `pg_hba.conf`) en lugar de la conexión por socket Unix (que usa autenticación `peer`).

---

## 7. Verificación funcional

Comprobar que el backend puede conectarse a la base de datos arrancando el servicio y consultando el health check:

```bash
sudo systemctl restart ehukene
curl -k https://10.227.81.132/health
```

Si devuelve `{"status":"ok","version":"1.0.0"}` la conexión a PostgreSQL es correcta.

Para consultar el estado de la base de datos directamente:

```bash
# Número de registros por tabla
sudo -u postgres psql -d ehukene -c "
  SELECT schemaname, tablename,
         n_live_tup AS filas
  FROM   pg_stat_user_tables
  ORDER  BY tablename;
"
```

---

## 8. Mantenimiento

### Retención de datos

Según los contratos del sistema, `telemetry_raw` retiene datos durante 12 meses. En Fase 3 se implementará particionado automático con `pg_partman`. De momento, purga manual si fuera necesario:

```bash
sudo -u postgres psql -d ehukene -c "
  DELETE FROM telemetry_raw
  WHERE received_at < NOW() - INTERVAL '12 months';
"
```

### Backup básico

```bash
# Volcado completo de la base de datos
sudo -u postgres pg_dump ehukene \
  | gzip > /opt/ehukene/backup_ehukene_$(date +%Y%m%d).sql.gz
```

### Acceso interactivo para diagnóstico

```bash
# Como superusuario
sudo -u postgres psql -d ehukene

# Como usuario de aplicación
psql -U ehukene_app -d ehukene -h 127.0.0.1
```

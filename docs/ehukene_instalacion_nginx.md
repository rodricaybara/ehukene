# EHUkene — Instalación y configuración de NGINX

**Entorno:** Ubuntu 22.04 / 24.04  
**Versión NGINX:** 1.28.3 (repositorio oficial)  
**Fecha:** 2026-04-08

---

## 1. Instalación

Instalar desde el repositorio oficial de NGINX para tener la versión estable más reciente en lugar de la del sistema:

```bash
curl -fsSL https://nginx.org/keys/nginx_signing.key \
  | sudo gpg --dearmor -o /etc/apt/keyrings/nginx.gpg

echo "deb [signed-by=/etc/apt/keyrings/nginx.gpg] \
  http://nginx.org/packages/ubuntu $(lsb_release -cs) nginx" \
  | sudo tee /etc/apt/sources.list.d/nginx.list

sudo apt update
sudo apt install -y nginx

sudo systemctl enable nginx
sudo systemctl start nginx
```

---

## 2. Certificado SSL autofirmado

En entornos de desarrollo sin DNS público no es posible usar Let's Encrypt. Se genera un certificado autofirmado con OpenSSL:

```bash
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/ssl/private/ehukene.key \
  -out    /etc/ssl/certs/ehukene.crt \
  -subj   "/CN=10.227.81.132"
```

Ajustar permisos de la clave privada:

```bash
sudo chmod 640 /etc/ssl/private/ehukene.key
sudo chown root:www-data /etc/ssl/private/ehukene.key
```

> En producción con dominio público sustituir por un certificado corporativo o de Let's Encrypt (`certbot --nginx -d dominio`). Las rutas están preparadas en el fichero de configuración, comentadas y listas para activar.

---

## 3. Estructura de ficheros de configuración

NGINX instalado desde el repositorio oficial usa esta estructura:

```
/etc/nginx/
├── nginx.conf                  # Configuración global (bloque http {})
├── conf.d/                     # Incluido por nginx.conf por defecto
├── sites-available/            # Ficheros de configuración de cada site
│   └── ehukene.conf            # Configuración de EHUkene
└── sites-enabled/              # Enlaces simbólicos a los sites activos
    └── ehukene.conf -> /etc/nginx/sites-available/ehukene.conf
```

> **Importante:** el repositorio oficial de NGINX no crea el directorio `sites-enabled` ni lo incluye en `nginx.conf` por defecto. Ambas cosas hay que hacerlas manualmente (ver secciones 4 y 5).

---

## 4. Fichero de configuración global: `nginx.conf`

El `nginx.conf` por defecto **no incluye `sites-enabled`**; solo incluye `conf.d/`. Hay que añadir el include y el `log_format` personalizado de EHUkene.

Contenido final de `/etc/nginx/nginx.conf`:

```nginx
user  nginx;
worker_processes  auto;

error_log  /var/log/nginx/error.log notice;
pid        /run/nginx.pid;

events {
    worker_connections  1024;
}

http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    # Formato de log estándar de NGINX
    log_format  main  '$remote_addr - $remote_user [$time_local] "$request" '
                      '$status $body_bytes_sent "$http_referer" '
                      '"$http_user_agent" "$http_x_forwarded_for"';

    # Formato extendido para EHUkene: incluye tiempo de respuesta y API Key.
    # Nota: NGINX no soporta subcadenas en log_format (sintaxis ${var:0:8} no válida).
    log_format  ehukene_fmt  '$remote_addr - $time_iso8601 '
                             '"$request" $status $body_bytes_sent '
                             'rt=$request_time '
                             'apikey="$http_x_api_key"';

    access_log  /var/log/nginx/access.log  main;

    sendfile        on;
    keepalive_timeout  65;

    include /etc/nginx/conf.d/*.conf;
    include /etc/nginx/sites-enabled/*;   # ← Añadido manualmente
}
```

> **Nota:** el `log_format ehukene_fmt` debe declararse aquí, en el bloque `http {}`, no dentro del bloque `server {}` del fichero de site. Declararlo en el `server {}` provoca que NGINX cargue el bloque HTTP (puerto 80) pero ignore silenciosamente el bloque HTTPS (puerto 443).

---

## 5. Fichero de configuración del site: `ehukene.conf`

Crear el fichero en `sites-available`:

```bash
sudo nano /etc/nginx/sites-available/ehukene.conf
```

Contenido:

```nginx
# ---------------------------------------------------------------------------
# Redireccionamiento HTTP → HTTPS
# ---------------------------------------------------------------------------
server {
    listen      80;
    listen      [::]:80;
    server_name 10.227.81.132;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

# ---------------------------------------------------------------------------
# Servidor HTTPS principal
# ---------------------------------------------------------------------------
server {
    listen      443 ssl;
    listen      [::]:443 ssl;
    server_name 10.227.81.132;

    # Certificado autofirmado (desarrollo)
    ssl_certificate     /etc/ssl/certs/ehukene.crt;
    ssl_certificate_key /etc/ssl/private/ehukene.key;

    # Certificado Let's Encrypt (producción) — descomentar y ajustar dominio:
    # ssl_certificate     /etc/letsencrypt/live/ehukene.dominio.local/fullchain.pem;
    # ssl_certificate_key /etc/letsencrypt/live/ehukene.dominio.local/privkey.pem;

    ssl_protocols             TLSv1.2 TLSv1.3;
    ssl_ciphers               ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;
    ssl_session_cache         shared:SSL:10m;
    ssl_session_timeout       1d;
    ssl_session_tickets       off;

    add_header X-Content-Type-Options  "nosniff"        always;
    add_header X-Frame-Options         "DENY"           always;
    add_header X-XSS-Protection        "1; mode=block"  always;
    add_header Referrer-Policy         "no-referrer"    always;

    client_max_body_size 2m;

    proxy_connect_timeout   10s;
    proxy_send_timeout      30s;
    proxy_read_timeout      30s;
    send_timeout            30s;

    access_log /var/log/nginx/ehukene_access.log ehukene_fmt;
    error_log  /var/log/nginx/ehukene_error.log  warn;

    # Health check
    location /health {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host            $host;
        proxy_set_header X-Real-IP       $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # API REST
    location /api/ {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
    }

    # Distribución de artefactos para auto-actualización (Fase 2)
    location /dist/ {
        root      /var/www/ehukene;
        autoindex off;
        location ~* \.(exe|py)$ {
            add_header Content-Disposition "attachment";
        }
    }

    # Bloqueo de rutas no definidas
    location / {
        return 404;
    }
}
```

---

## 6. Activar el site

```bash
# Crear el enlace simbólico (fichero, no directorio)
sudo ln -s /etc/nginx/sites-available/ehukene.conf /etc/nginx/sites-enabled/ehukene.conf

# Verificar que es un enlace simbólico correcto (debe mostrar ->)
ls -la /etc/nginx/sites-enabled/
```

La salida esperada:

```
lrwxrwxrwx 1 root root  /etc/nginx/sites-enabled/ehukene.conf -> /etc/nginx/sites-available/ehukene.conf
```

---

## 7. Verificar y recargar

```bash
# Comprobar sintaxis
sudo nginx -t

# Recargar configuración sin interrumpir conexiones activas
sudo systemctl reload nginx

# Verificar que escucha en 80 y 443
sudo ss -tulpn | grep nginx
```

Salida esperada:

```
tcp  LISTEN  0.0.0.0:80   ...  nginx
tcp  LISTEN  0.0.0.0:443  ...  nginx
tcp  LISTEN  [::]:80      ...  nginx
tcp  LISTEN  [::]:443     ...  nginx
```

---

## 8. Verificación funcional

```bash
# HTTP debe redirigir con 301 a HTTPS
curl -v http://10.227.81.132/health

# HTTPS debe devolver el health check (-k ignora el certificado autofirmado)
curl -k https://10.227.81.132/health
```

Respuesta esperada del health check:

```json
{"status":"ok","version":"1.0.0"}
```

---

## 9. Problemas encontrados durante la instalación

### `sites-enabled/ehukene` era un directorio en lugar de un enlace simbólico

Al copiar los ficheros de configuración se creó un directorio `ehukene/` dentro de `sites-available` y `sites-enabled` en lugar de un fichero. NGINX no lo cargaba.

**Solución:**

```bash
sudo rm -rf /etc/nginx/sites-available/ehukene
sudo rm -rf /etc/nginx/sites-enabled/ehukene
sudo mv /etc/nginx/sites-available/ehukene/ehukene.nginx.conf \
        /etc/nginx/sites-available/ehukene.conf
sudo ln -s /etc/nginx/sites-available/ehukene.conf \
           /etc/nginx/sites-enabled/ehukene.conf
```

### El puerto 443 no aparecía aunque `nginx -t` era correcto

El `log_format ehukene_fmt` estaba declarado dentro del bloque `server {}` del fichero de site. NGINX solo permite `log_format` en el bloque `http {}`. Al tenerlo en el lugar incorrecto, el bloque HTTPS fallaba al cargar sin reportar error en el test de sintaxis.

**Solución:** mover la directiva `log_format ehukene_fmt` al bloque `http {}` de `nginx.conf`.

### `nginx.conf` no incluía `sites-enabled`

El repositorio oficial de NGINX solo incluye `conf.d/` en `nginx.conf`. El directorio `sites-enabled` no se procesa hasta añadir explícitamente:

```nginx
include /etc/nginx/sites-enabled/*;
```

### Sintaxis de subcadena no soportada en `log_format`

La sintaxis `${http_x_api_key:0:8}` para truncar la API Key en el log no es válida en NGINX y produce el error:

```
[emerg] the closing bracket in "http_x_api_key" variable is missing
```

**Solución:** loguear la variable completa sin truncar:

```nginx
'apikey="$http_x_api_key"'
```

# Economía Doméstica — Resumen del proyecto

## Descripción general

Aplicación web para gestionar la economía de un hogar de dos personas.
Autoalojada en un NAS mediante Docker, accesible desde la red local.

---

## Modelo financiero

Tres bolsas de dinero independientes:

- **Cuenta común** — ingresos del hogar y gastos compartidos
  (alimentación, combustible, seguros, impuestos, suministros…)
- **Cuenta personal A** — asignación mensual fija + gastos individuales
- **Cuenta personal B** — asignación mensual fija + gastos individuales

A principio de mes se realiza una transferencia manual desde la cuenta
común a cada cuenta personal (asignación fija). El sistema la registra
como "transferencia pendiente" y cada usuario la confirma cuando la hace.

---

## Funcionalidades (v1)

- Registro de ingresos y gastos (manual y por importación CSV/Excel)
- Categorización de movimientos (categorías del sistema + personales)
- Informes detallados: resumen mensual, desglose por categoría,
  evolución mes a mes y comparativa entre personas
- Gestión de transferencias entre cuentas (asignación mensual)
- Dos usuarios independientes con login propio

Fuera de alcance en v1: presupuestos, metas de ahorro, alertas.

---

## Stack técnico

| Capa          | Tecnología                        |
|---------------|-----------------------------------|
| Base de datos | SQLite (fichero en volumen NAS)   |
| Backend       | Python 3.12 + FastAPI             |
| Frontend      | HTML + CSS + JavaScript           |
| Servidor web  | Nginx (proxy + ficheros estáticos)|
| Contenedores  | Docker + docker-compose           |

---

## Esquema de base de datos (5 tablas)

**usuarios** — id, nombre, email, password_hash, creado_en

**cuentas** — id, usuario_id (NULL = común), nombre, tipo, saldo_inicial
- tipo: 'comun' | 'personal'

**categorias** — id, nombre, tipo, usuario_id (NULL = sistema), es_sistema
- tipo: 'ingreso' | 'gasto'
- Las del sistema son editables pero no borrables

**movimientos** — id, cuenta_id, categoria_id, usuario_id, importe,
                  tipo, descripcion, fecha, creado_en
- tipo: 'ingreso' | 'gasto'
- Solo el propietario puede editar o borrar sus movimientos
- El saldo de cada cuenta se calcula sumando movimientos (no se almacena)

**transferencias** — id, cuenta_origen_id, cuenta_destino_id, importe,
                     fecha, descripcion, completada, creado_en
- completada: 0 (pendiente) | 1 (confirmada)

Migraciones numeradas en backend/migrations/. Se aplican automáticamente
al arrancar el backend.

---

## Endpoints (22 en total)

### Autenticación
- POST   /auth/login          → devuelve token JWT (8 h)
- POST   /auth/logout         → cierre de sesión
- GET    /auth/me             → datos del usuario actual

### Cuentas
- GET    /cuentas             → lista las tres cuentas
- GET    /cuentas/{id}        → detalle con saldo calculado
- GET    /cuentas/{id}/saldo  → saldo actual (saldo_inicial + movimientos)

### Movimientos
- GET    /movimientos         → lista con filtros (cuenta, categoría, fecha, tipo)
- POST   /movimientos         → registra ingreso o gasto
- GET    /movimientos/{id}    → detalle
- PUT    /movimientos/{id}    → edita (solo el propietario)
- DELETE /movimientos/{id}    → elimina (solo el propietario)
- POST   /movimientos/importar → importa desde CSV o Excel

### Transferencias
- GET    /transferencias               → lista (filtro: pendientes/completadas)
- POST   /transferencias               → crea transferencia entre cuentas
- PUT    /transferencias/{id}/confirmar → confirma transferencia pendiente

### Categorías
- GET    /categorias      → sistema + propias del usuario
- POST   /categorias      → crea categoría personalizada
- PUT    /categorias/{id} → edita nombre (sistema y propias)
- DELETE /categorias/{id} → elimina (solo propias)

### Informes
- GET    /informes/resumen        → ingresos, gastos y saldo neto del mes
- GET    /informes/por-categoria  → gastos agrupados por categoría (con %)
- GET    /informes/evolucion      → evolución mes a mes (para gráficas)
- GET    /informes/por-persona    → comparativa de gastos entre los dos usuarios

---

## Estructura de carpetas

economia-domestica/
├── docker-compose.yml
├── .env                        ← SECRET_KEY y configuración (no subir a git)
├── data/
│   └── economia.db             ← volumen persistente en el NAS
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   ├── database.py             ← conexión + sistema de migraciones
│   ├── routers/
│   │   ├── auth.py             ← ya implementado
│   │   ├── cuentas.py
│   │   ├── movimientos.py
│   │   ├── transferencias.py
│   │   ├── categorias.py
│   │   └── informes.py
│   └── migrations/
│       └── 001_schema_inicial.sql  ← ya generado
└── frontend/
    ├── Dockerfile
    ├── nginx.conf
    └── src/
        ├── index.html          ← login
        ├── dashboard.html
        ├── movimientos.html
        ├── informes.html
        ├── css/styles.css
        └── js/
            ├── api.js          ← todas las llamadas al backend
            ├── auth.js         ← gestión del token JWT
            ├── dashboard.js
            ├── movimientos.js
            └── informes.js

---

## Arranque del proyecto

# 1. Generar la clave secreta
openssl rand -hex 32

# 2. Copiar el resultado en .env como SECRET_KEY

# 3. Levantar los contenedores
docker compose up -d

# 4. Documentación interactiva del backend (solo desarrollo)
http://localhost:8000/docs

# 5. Aplicación web
http://localhost

---

## Ficheros ya generados

- schema.sql              → script para crear las tablas
- auth.py                 → endpoint POST /auth/login completo
- docker-compose.yml      → orquestación de contenedores
- ficheros_soporte.txt    → Dockerfiles, nginx.conf, main.py, database.py

---

## Orden de desarrollo recomendado

1. Crear la estructura de carpetas y los Dockerfiles
2. Copiar schema.sql como migrations/001_schema_inicial.sql
3. Implementar el backend router por router (empezando por auth)
4. Probar cada router con la documentación interactiva (/docs)
5. Desarrollar el frontend pantalla por pantalla
6. Pruebas conjuntas y ajustes
7. Despliegue final en el NAS

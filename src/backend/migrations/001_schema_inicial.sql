-- ============================================================
-- Economía doméstica — esquema SQLite
-- ============================================================

PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------
-- Usuarios
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS usuarios (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre       TEXT    NOT NULL,
    email        TEXT    NOT NULL UNIQUE,
    password_hash TEXT   NOT NULL,
    creado_en    DATETIME NOT NULL DEFAULT (datetime('now'))
);

-- ------------------------------------------------------------
-- Cuentas
-- usuario_id NULL = cuenta común del hogar
-- tipo: 'comun' | 'personal'
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cuentas (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id    INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    nombre        TEXT    NOT NULL,
    tipo          TEXT    NOT NULL CHECK (tipo IN ('comun', 'personal')),
    saldo_inicial REAL    NOT NULL DEFAULT 0,
    creado_en     DATETIME NOT NULL DEFAULT (datetime('now'))
);

-- ------------------------------------------------------------
-- Categorías
-- usuario_id NULL = categoría predefinida del sistema
-- tipo: 'ingreso' | 'gasto'
-- Las predefinidas son editables (nombre) pero no eliminables
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS categorias (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre      TEXT    NOT NULL,
    tipo        TEXT    NOT NULL CHECK (tipo IN ('ingreso', 'gasto')),
    usuario_id  INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    es_sistema  INTEGER NOT NULL DEFAULT 0 CHECK (es_sistema IN (0, 1)),
    UNIQUE (nombre, usuario_id)
);

-- ------------------------------------------------------------
-- Movimientos (ingresos y gastos)
-- tipo: 'ingreso' | 'gasto'
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS movimientos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    cuenta_id    INTEGER NOT NULL REFERENCES cuentas(id) ON DELETE CASCADE,
    categoria_id INTEGER NOT NULL REFERENCES categorias(id),
    usuario_id   INTEGER NOT NULL REFERENCES usuarios(id),
    importe      REAL    NOT NULL CHECK (importe > 0),
    tipo         TEXT    NOT NULL CHECK (tipo IN ('ingreso', 'gasto')),
    descripcion  TEXT,
    fecha        DATE    NOT NULL,
    creado_en    DATETIME NOT NULL DEFAULT (datetime('now'))
);

-- ------------------------------------------------------------
-- Transferencias periódicas (asignación mensual)
-- Confirmación manual: completada = 0 (pendiente) | 1 (confirmada)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS transferencias (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    cuenta_origen_id   INTEGER NOT NULL REFERENCES cuentas(id),
    cuenta_destino_id  INTEGER NOT NULL REFERENCES cuentas(id),
    importe            REAL    NOT NULL CHECK (importe > 0),
    fecha              DATE    NOT NULL,
    descripcion        TEXT,
    completada         INTEGER NOT NULL DEFAULT 0 CHECK (completada IN (0, 1)),
    creado_en          DATETIME NOT NULL DEFAULT (datetime('now')),
    CHECK (cuenta_origen_id != cuenta_destino_id)
);

-- ============================================================
-- Índices
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_movimientos_cuenta    ON movimientos(cuenta_id);
CREATE INDEX IF NOT EXISTS idx_movimientos_fecha     ON movimientos(fecha);
CREATE INDEX IF NOT EXISTS idx_movimientos_usuario   ON movimientos(usuario_id);
CREATE INDEX IF NOT EXISTS idx_transferencias_fecha  ON transferencias(fecha);
CREATE INDEX IF NOT EXISTS idx_transferencias_pendientes ON transferencias(completada) WHERE completada = 0;

-- ============================================================
-- Datos iniciales
-- ============================================================

-- Cuenta común del hogar
INSERT INTO cuentas (usuario_id, nombre, tipo, saldo_inicial)
VALUES (NULL, 'Cuenta común', 'comun', 0);

-- Categorías predefinidas del sistema
INSERT INTO categorias (nombre, tipo, usuario_id, es_sistema) VALUES
    ('Alimentación',      'gasto',   NULL, 1),
    ('Combustible',       'gasto',   NULL, 1),
    ('Seguros',           'gasto',   NULL, 1),
    ('Impuestos',         'gasto',   NULL, 1),
    ('Suministros',       'gasto',   NULL, 1),
    ('Transporte',        'gasto',   NULL, 1),
    ('Salud',             'gasto',   NULL, 1),
    ('Ocio',              'gasto',   NULL, 1),
    ('Ropa',              'gasto',   NULL, 1),
    ('Otros gastos',      'gasto',   NULL, 1),
    ('Nómina',            'ingreso', NULL, 1),
    ('Otros ingresos',    'ingreso', NULL, 1);
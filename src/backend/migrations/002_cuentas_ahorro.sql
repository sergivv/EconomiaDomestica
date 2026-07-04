-- 002_cuentas_ahorro.sql
-- Añade el tipo 'ahorro' a la tabla cuentas y crea las dos cuentas de ahorro
--
-- SQLite no permite modificar un CHECK existente con ALTER TABLE,
-- así que recreamos la tabla con el nuevo CHECK y copiamos los datos.

PRAGMA foreign_keys = OFF;

-- 1. Crear tabla nueva con el CHECK actualizado
CREATE TABLE cuentas_new (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id    INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    nombre        TEXT    NOT NULL,
    tipo          TEXT    NOT NULL CHECK (tipo IN ('comun', 'personal', 'ahorro')),
    saldo_inicial REAL    NOT NULL DEFAULT 0,
    creado_en     DATETIME NOT NULL DEFAULT (datetime('now'))
);

-- 2. Copiar los datos existentes
INSERT INTO cuentas_new (id, usuario_id, nombre, tipo, saldo_inicial, creado_en)
SELECT id, usuario_id, nombre, tipo, saldo_inicial, creado_en FROM cuentas;

-- 3. Sustituir la tabla antigua
DROP TABLE cuentas;
ALTER TABLE cuentas_new RENAME TO cuentas;

PRAGMA foreign_keys = ON;

-- 4. Insertar las dos cuentas de ahorro
INSERT INTO cuentas (usuario_id, nombre, tipo, saldo_inicial) VALUES
    (NULL, 'Cuenta Naranja',  'ahorro', 0),
    (NULL, 'Naranja Mini', 'ahorro', 0);
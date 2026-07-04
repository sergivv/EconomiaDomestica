import sqlite3
import os
import glob

DB_PATH = os.getenv("DB_PATH", "/data/economia.db")
MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "migrations")

def get_db():
    """Dependencia FastAPI: abre y cierra la conexión por petición."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """
    Aplica todas las migraciones pendientes al arrancar el backend.
    Crea la tabla 'migraciones' si no existe para llevar el registro.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS migraciones (
            nombre TEXT PRIMARY KEY,
            aplicada_en DATETIME DEFAULT (datetime('now'))
        )
    """)
    conn.commit()

    archivos = sorted(glob.glob(os.path.join(MIGRATIONS_DIR, "*.sql")))
    for ruta in archivos:
        nombre = os.path.basename(ruta)
        ya_aplicada = conn.execute(
            "SELECT 1 FROM migraciones WHERE nombre = ?", (nombre,)
        ).fetchone()
        if not ya_aplicada:
            with open(ruta) as f:
                conn.executescript(f.read())
            conn.execute(
                "INSERT INTO migraciones (nombre) VALUES (?)", (nombre,)
            )
            conn.commit()
            print(f"[DB] Migración aplicada: {nombre}")

    conn.close()
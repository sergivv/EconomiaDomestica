from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db
from routers import auth, cuentas, categorias, movimientos, transferencias, informes

app = FastAPI(title="Economía doméstica", version="1.0.0")

# Permite peticiones desde el frontend (mismo servidor, distinto puerto)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://localhost:7980"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicializa la BD y aplica migraciones al arrancar
@app.on_event("startup")
async def startup():
    init_db()

# Endpoint de salud (usado por el healthcheck de Docker)
@app.get("/health")
def health():
    return {"status": "ok"}

# Registro de routers
app.include_router(auth.router)
app.include_router(cuentas.router)
app.include_router(movimientos.router)
app.include_router(transferencias.router)
app.include_router(categorias.router)
app.include_router(informes.router)
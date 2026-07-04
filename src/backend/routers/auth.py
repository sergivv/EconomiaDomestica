# auth.py
# Módulo de autenticación: login, logout y usuario actual
#
# Dependencias necesarias:
#   pip install fastapi python-jose[cryptography] passlib[bcrypt] python-multipart

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
import sqlite3

# ------------------------------------------------------------
# Configuración  (en producción mueve estos valores a variables
# de entorno o a un fichero .env)
# ------------------------------------------------------------
SECRET_KEY = "cambia_esto_por_un_valor_aleatorio_largo"  # openssl rand -hex 32
ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 60 * 8  # 8 horas

DB_PATH = "/data/economia.db"   # volumen Docker

# ------------------------------------------------------------
# Utilidades
# ------------------------------------------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")
router = APIRouter(prefix="/auth", tags=["auth"])


def get_db():
    """Abre conexión a SQLite y activa las foreign keys."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_user_by_email(conn: sqlite3.Connection, email: str):
    return conn.execute(
        "SELECT * FROM usuarios WHERE email = ?", (email,)
    ).fetchone()


# ------------------------------------------------------------
# Dependencia reutilizable: usuario autenticado
# Úsala en cualquier endpoint con: user = Depends(current_user)
# ------------------------------------------------------------
async def current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    conn: sqlite3.Connection = Depends(get_db),
):
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido o expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is not None:
            user_id = int(user_id)
        if user_id is None:
            raise credentials_error
    except JWTError:
        raise credentials_error

    user = conn.execute(
        "SELECT id, nombre, email FROM usuarios WHERE id = ?", (user_id,)
    ).fetchone()
    if user is None:
        raise credentials_error
    return user


# ------------------------------------------------------------
# Schemas de respuesta
# ------------------------------------------------------------
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    nombre: str


class UserResponse(BaseModel):
    id: int
    nombre: str
    email: str


# ------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------

@router.post("/login", response_model=TokenResponse)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    conn: sqlite3.Connection = Depends(get_db),
):
    """
    Recibe email (username) y contraseña.
    Devuelve un JWT si las credenciales son correctas.
    """
    # 1. Buscar usuario por email
    user = get_user_by_email(conn, form.username)

    # 2. Verificar que existe y que la contraseña es correcta
    #    Usamos el mismo mensaje genérico para no revelar si el email existe
    if user is None or not verify_password(form.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. Generar token JWT con el id del usuario como subject
    token = create_access_token({"sub": str(user["id"])})

    return TokenResponse(
        access_token=token,
        user_id=user["id"],
        nombre=user["nombre"],
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    _: Annotated[dict, Depends(current_user)],
):
    """
    Con JWT stateless el logout real se hace en el cliente
    (borrando el token del almacenamiento local).
    Este endpoint existe para que el frontend tenga un punto
    explícito de cierre de sesión y para facilitar futuros
    mecanismos de revocación (lista negra en Redis, etc.).
    """
    return


@router.get("/me", response_model=UserResponse)
async def me(
    user: Annotated[dict, Depends(current_user)],
):
    """Devuelve los datos del usuario autenticado."""
    return UserResponse(id=user["id"], nombre=user["nombre"], email=user["email"])
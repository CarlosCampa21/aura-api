
from fastapi import FastAPI, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
from dotenv import load_dotenv
from datetime import datetime
from openai import OpenAI, BadRequestError
import requests 
import os

# ========= App & ENV =========
load_dotenv()
app = FastAPI(title="Aura API (Académica) + OpenAI")

# ---- CORS (para Vite/React en localhost:5173) ----
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========= MongoDB =========
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
try:
    client_mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
    client_mongo.admin.command("ping")
    db = client_mongo["aura_db"]
except ServerSelectionTimeoutError as e:
    raise RuntimeError(f"Mongo no accesible: {e}")

# ========= OpenAI =========
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client_oa = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
OPENAI_MODEL_PRIMARY = "gpt-5-nano"   # intenta primero aquí
OPENAI_MODEL_FALLBACK = "gpt-4o-mini" # y si falla, usa este

# ========= Ollama (gratuito/local) =========
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

# ========= Modelos =========
class Usuario(BaseModel):
    nombre: str
    correo: EmailStr
    carrera: str
    semestre: int = Field(ge=1, description="Semestre >= 1")

class Materia(BaseModel):
    codigo: str
    nombre: str
    profesor: str
    salon: str
    dias: List[str] = Field(default_factory=list)   # ej. ["Lun","Mie"]
    hora_inicio: str                                # ej. "08:00"
    hora_fin: str                                   # ej. "09:30"

class Horario(BaseModel):
    usuario_correo: EmailStr
    materia_codigo: str
    dia: str               # "Lun", "Mar", etc.
    hora_inicio: str
    hora_fin: str

class Nota(BaseModel):
    usuario_correo: EmailStr
    titulo: str
    contenido: str
    tags: List[str] = Field(default_factory=list)
    created_at: Optional[str] = None

class Consulta(BaseModel):
    usuario_correo: EmailStr
    pregunta: str
    respuesta: Optional[str] = None
    ts: Optional[str] = None

class Ask(BaseModel):  # Para /aura/ask
    usuario_correo: EmailStr
    pregunta: str

# ========= Utils =========
def insert_and_response(collection_name: str, doc: dict):
    """Inserta doc y regresa respuesta JSON-friendly (sin ObjectId)."""
    result = db[collection_name].insert_one(doc)
    safe_doc = {k: v for k, v in doc.items() if k != "_id"}
    return {"message": "ok", "id": str(result.inserted_id), "data": safe_doc}

def generar_respuesta_ia(pregunta: str, contexto: str = "") -> str:
    """
    Orden de resolución:
      1) OpenAI (modelo primario)
      2) OpenAI (fallback)
      3) Ollama local (gratis) si no hay OPENAI_API_KEY o si OpenAI falla
    """
    system = (
        "Eres Aura, una IA que apoya a alumnos de la UABCS. "
        "Responde breve, clara y con pasos accionables cuando aplique. "
        "Si faltan datos, dilo y sugiere qué falta."
    )
    user = f"Contexto:\n{contexto}\n---\nPregunta: {pregunta}"

    def call_openai(model_name: str) -> str:
        print(f"[IA] OpenAI → {model_name}")
        resp = client_oa.chat.completions.create(
            model=model_name,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=0.2,
        )
        out = resp.choices[0].message.content or ""
        out = out.strip()
        print(f"[IA] OpenAI OK ({model_name}): {out[:120]}...")
        return out or "Sin respuesta."

    def call_ollama() -> str:
        try:
            print(f"[IA] Ollama → {OLLAMA_MODEL} @ {OLLAMA_URL}")
            r = requests.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.2},
                },
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
            out = ((data.get("message") or {}).get("content") or "").strip()
            print(f"[IA] Ollama OK: {out[:120]}...")
            return out or "Sin respuesta."
        except Exception as e:
            print(f"[IA] Ollama error: {e.__class__.__name__}: {e}")
            return "Aura (local): no pude consultar el modelo."

    # --- Ruta de decisión ---
    if client_oa:
        try:
            return call_openai(OPENAI_MODEL_PRIMARY)
        except BadRequestError as e:
            print(f"[IA] OpenAI BadRequest({OPENAI_MODEL_PRIMARY}): {e}")
            try:
                return call_openai(OPENAI_MODEL_FALLBACK)
            except Exception as e2:
                print(f"[IA] Fallback OpenAI falló: {e2.__class__.__name__}: {e2}")
                return call_ollama()
        except Exception as e:
            print(f"[IA] OpenAI error: {e.__class__.__name__}: {e}")
            return call_ollama()
    else:
        # No hay API key → usar Ollama
        return call_ollama()
    """
    Llama a OpenAI con fallback automático:
      1) gpt-5-nano
      2) gpt-4o-mini
    Si no hay API key, retorna mensaje de demo.
    """
    if not client_oa:
        return "Aura (demo): falta OPENAI_API_KEY en el entorno."

    system = (
        "Eres Aura, una IA que apoya a alumnos de la UABCS. "
        "Responde breve, clara y con pasos accionables cuando aplique. "
        "Si faltan datos, dilo y sugiere qué falta."
    )
    user = f"Contexto:\n{contexto}\n---\nPregunta: {pregunta}"

    def call_model(model_name: str) -> str:
        print(f"[IA] Llamando modelo: {model_name}")
        resp = client_oa.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user}
            ],
            temperature=0.2,
        )
        out = resp.choices[0].message.content.strip()
        print(f"[IA] OK {model_name}: {out[:120]}...")
        return out

    try:
        return call_model(OPENAI_MODEL_PRIMARY)
    except BadRequestError as e:
        print(f"[IA] BadRequest con {OPENAI_MODEL_PRIMARY}: {e}")
        try:
            return call_model(OPENAI_MODEL_FALLBACK)
        except Exception as e2:
            print(f"[IA] Fallback también falló: {e2.__class__.__name__}: {e2}")
            return f"Aura (fallback): falló el modelo primario y el fallback ({e2.__class__.__name__})."
    except Exception as e:
        print(f"[IA] Error general: {e.__class__.__name__}: {e}")
        return f"Aura (fallback): no pude consultar el modelo ahora ({e.__class__.__name__})."

def build_contexto_academico(usuario_correo: str) -> str:
    """
    Arma un mini-contexto con datos del alumno desde Mongo para enriquecer la respuesta.
    (Ligero para no enviar demasiados tokens.)
    """
    try:
        u = db["usuarios"].find_one({"correo": usuario_correo}, {"_id": 0})
        hs = list(db["horarios"].find({"usuario_correo": usuario_correo}, {"_id": 0}))
        ms = list(db["materias"].find({}, {"_id": 0}))  # catálogo
        partes = []
        if u:
            partes.append(f"Alumno: {u.get('nombre')} | Carrera: {u.get('carrera')} | Semestre: {u.get('semestre')}")
        if hs:
            horarios_txt = "; ".join([f"{h['materia_codigo']} {h['dia']} {h['hora_inicio']}-{h['hora_fin']}" for h in hs])
            partes.append(f"Horarios del alumno: {horarios_txt}")
        if ms:
            materias_txt = "; ".join([f"{m['codigo']}:{m['nombre']} ({m['profesor']}, {m['salon']})" for m in ms][:8])
            partes.append(f"Materias catálogo (máx. 8): {materias_txt}")
        return "\n".join(partes) if partes else "Sin datos académicos del alumno aún."
    except Exception:
        return "No se pudo leer contexto de la BD."

# ========= Health / Ping =========
@app.get("/ping")
def ping():
    return {"message": "pong"}

@app.get("/health", status_code=status.HTTP_200_OK)
def health():
    try:
        client_mongo.admin.command("ping")
        return {"ok": True, "mongo": "up", "openai": bool(client_oa)}
    except Exception as e:
        return {"ok": False, "mongo": f"down: {e.__class__.__name__}", "openai": bool(client_oa)}

# ========= USUARIOS =========
@app.post("/add-usuario")
def add_usuario(usuario: Usuario):
    try:
        doc = usuario.model_dump(mode="json")
        doc["correo"] = str(doc["correo"])
        return insert_and_response("usuarios", doc)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Insert usuario failed: {e}")

@app.get("/usuarios")
def get_usuarios():
    try:
        usuarios = list(db["usuarios"].find({}, {"_id": 0}))
        return {"usuarios": usuarios}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query usuarios failed: {e}")

# ========= MATERIAS =========
@app.post("/add-materia")
def add_materia(materia: Materia):
    try:
        doc = materia.model_dump()
        return insert_and_response("materias", doc)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Insert materia failed: {e}")

@app.get("/materias")
def get_materias():
    try:
        materias = list(db["materias"].find({}, {"_id": 0}))
        return {"materias": materias}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query materias failed: {e}")

# ========= HORARIOS =========
@app.post("/add-horario")
def add_horario(horario: Horario):
    try:
        doc = horario.model_dump(mode="json")
        doc["usuario_correo"] = str(doc["usuario_correo"])
        return insert_and_response("horarios", doc)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Insert horario failed: {e}")

@app.get("/horarios")
def get_horarios(usuario_correo: Optional[EmailStr] = Query(None)):
    try:
        filtro = {}
        if usuario_correo:
            filtro["usuario_correo"] = str(usuario_correo)
        horarios = list(db["horarios"].find(filtro, {"_id": 0}))
        return {"horarios": horarios}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query horarios failed: {e}")

# ========= NOTAS =========
@app.post("/add-nota")
def add_nota(nota: Nota):
    try:
        doc = nota.model_dump(mode="json")
        doc["usuario_correo"] = str(doc["usuario_correo"])
        doc["created_at"] = doc.get("created_at") or datetime.utcnow().isoformat()
        return insert_and_response("notas", doc)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Insert nota failed: {e}")

@app.get("/notas")
def get_notas(usuario_correo: Optional[EmailStr] = Query(None)):
    try:
        filtro = {}
        if usuario_correo:
            filtro["usuario_correo"] = str(usuario_correo)
        notas = list(db["notas"].find(filtro, {"_id": 0}))
        return {"notas": notas}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query notas failed: {e}")

# ========= CONSULTAS =========
@app.post("/add-consulta")
def add_consulta(consulta: Consulta):
    try:
        doc = consulta.model_dump(mode="json")
        doc["usuario_correo"] = str(doc["usuario_correo"])
        doc["ts"] = doc.get("ts") or datetime.utcnow().isoformat()
        return insert_and_response("consultas", doc)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Insert consulta failed: {e}")

@app.get("/consultas")
def get_consultas(usuario_correo: Optional[EmailStr] = Query(None)):
    try:
        filtro = {}
        if usuario_correo:
            filtro["usuario_correo"] = str(usuario_correo)
        consultas = list(db["consultas"].find(filtro, {"_id": 0}))
        return {"consultas": consultas}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query consultas failed: {e}")

# ========= ASK (OpenAI) =========
@app.post("/aura/ask")
def aura_ask(payload: Ask):
    try:
        pregunta = payload.pregunta.strip()
        usuario = str(payload.usuario_correo)

        # 1) Construir contexto desde Mongo
        contexto = build_contexto_academico(usuario)

        # 2) Respuesta IA
        respuesta = generar_respuesta_ia(pregunta, contexto)

        # 3) Guardar en Mongo
        doc = {
            "usuario_correo": usuario,
            "pregunta": pregunta,
            "respuesta": respuesta,
            "ts": datetime.utcnow().isoformat(),
        }
        result = db["consultas"].insert_one(doc)

        # 4) Devolver
        return {
            "message": "Consulta registrada",
            "id": str(result.inserted_id),
            "pregunta": pregunta,
            "respuesta": respuesta,
            "contexto_usado": bool(contexto and contexto != "Sin datos académicos del alumno aún.")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ask failed: {e}")

print("DEBUG OPENAI KEY? ", bool(os.getenv("OPENAI_API_KEY")))

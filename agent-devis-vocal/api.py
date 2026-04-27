"""
API FastAPI — POC "Devis Vocal".

Expose :
  GET  /              → page HTML avec enregistrement micro
  GET  /health        → healthcheck
  POST /transcribe    → upload audio → texte (utile pour debug)
  POST /dicter-devis  → upload audio → transcription + agent → JSON structuré

Lancement :
    python api.py
    → http://127.0.0.1:8000/
"""

import logging
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from clients import creer_client, lister_clients
from config import (
    API_HOST, API_PORT, WHISPER_MODEL,
    PRICE_LLM_INPUT_PER_MTOK, PRICE_LLM_OUTPUT_PER_MTOK, PRICE_WHISPER_PER_MIN,
)
from main import agent
from transcribe import transcrire_bytes


def _cost_llm(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens * PRICE_LLM_INPUT_PER_MTOK / 1_000_000
        + output_tokens * PRICE_LLM_OUTPUT_PER_MTOK / 1_000_000
    )


def _cost_whisper(audio_seconds: float) -> float:
    return (audio_seconds / 60.0) * PRICE_WHISPER_PER_MIN

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-12s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("api")

STATIC_DIR = Path(__file__).parent / "static"


# === Schémas de réponse ===

class TranscriptionResponse(BaseModel):
    texte: str
    duree_s: float
    taille_mo: float
    langue: str | None = None
    modele: str


class DicterDevisResponse(BaseModel):
    texte_transcrit: str
    duree_transcription_s: float
    duree_agent_ms: int
    resultat: dict[str, Any]  # {type, devis, message}
    usage: dict[str, Any]     # {whisper, llm_routeur, llm_outil, total_cost_usd}


class ClientCreate(BaseModel):
    civilite: str = ""
    prenom: str = ""
    nom: str
    adresse: str = ""
    code_postal: str = ""
    ville: str = ""
    telephone: str = ""
    email: str = ""


class Health(BaseModel):
    status: str
    version: str


# === Application FastAPI ===

app = FastAPI(
    title="Agent Devis Vocal — POC",
    description="Dictée d'un devis → transcription Whisper → extraction JSON.",
    version="1.0",
)


@app.get("/health", response_model=Health)
def health():
    return Health(status="ok", version="1.0")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/clients")
def lister_clients_endpoint():
    """Liste tous les clients triés par nom puis prénom."""
    return lister_clients()


@app.post("/clients", status_code=201)
def creer_client_endpoint(payload: ClientCreate):
    """Crée un nouveau client dans clients.db et renvoie la fiche complète."""
    try:
        client = creer_client(payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Erreur création client : {type(e).__name__} — {e}")
        raise HTTPException(status_code=500, detail=str(e))
    return client


@app.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_endpoint(audio: UploadFile = File(...)):
    """Transcrit un fichier audio uploadé — retourne uniquement le texte."""
    data = await audio.read()
    if not data:
        raise HTTPException(status_code=400, detail="Fichier audio vide")

    try:
        res = transcrire_bytes(data, nom_fichier=audio.filename or "audio.webm")
    except ValueError as e:
        raise HTTPException(status_code=413, detail=str(e))
    except Exception as e:
        logger.error(f"Erreur transcription : {type(e).__name__} — {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return TranscriptionResponse(**res)


@app.post("/dicter-devis", response_model=DicterDevisResponse)
async def dicter_devis(audio: UploadFile = File(...)):
    """Transcrit un audio puis envoie le texte à l'agent d'extraction de devis."""
    data = await audio.read()
    if not data:
        raise HTTPException(status_code=400, detail="Fichier audio vide")

    # 1) Transcription Whisper
    try:
        res = transcrire_bytes(data, nom_fichier=audio.filename or "audio.webm")
    except ValueError as e:
        raise HTTPException(status_code=413, detail=str(e))
    except Exception as e:
        logger.error(f"Erreur transcription : {type(e).__name__} — {e}")
        raise HTTPException(status_code=500, detail=f"Transcription : {e}")

    texte = res["texte"].strip()
    if not texte:
        raise HTTPException(status_code=422, detail="Transcription vide — réessayez")

    # 2) Agent
    start = time.time()
    try:
        resultat = agent(texte)
    except Exception as e:
        logger.error(f"Erreur agent : {type(e).__name__} — {e}")
        raise HTTPException(status_code=500, detail=f"Agent : {e}")

    duree_agent_ms = int((time.time() - start) * 1000)

    # Calcul des coûts
    audio_s = float(res.get("audio_seconds") or 0.0)
    cost_whisper = _cost_whisper(audio_s)

    usage_llm = resultat.pop("usage_llm", {})
    routeur = usage_llm.get("routeur", {})
    outil = usage_llm.get("outil", {})
    cost_routeur = _cost_llm(routeur.get("input_tokens", 0), routeur.get("output_tokens", 0))
    cost_outil = _cost_llm(outil.get("input_tokens", 0), outil.get("output_tokens", 0))

    usage = {
        "whisper": {
            "model": WHISPER_MODEL,
            "audio_seconds": round(audio_s, 2),
            "cost_usd": cost_whisper,
        },
        "llm_routeur": {
            "model": routeur.get("model"),
            "input_tokens": routeur.get("input_tokens", 0),
            "output_tokens": routeur.get("output_tokens", 0),
            "cost_usd": cost_routeur,
        },
        "llm_outil": {
            "model": outil.get("model"),
            "nom": outil.get("nom"),
            "input_tokens": outil.get("input_tokens", 0),
            "output_tokens": outil.get("output_tokens", 0),
            "cost_usd": cost_outil,
        },
        "total_cost_usd": cost_whisper + cost_routeur + cost_outil,
    }

    logger.info(
        f"OK | transcr {res['duree_s']}s ({audio_s:.1f}s audio) | agent {duree_agent_ms}ms "
        f"| coût ${usage['total_cost_usd']:.5f} | type={resultat.get('type')} | « {texte[:60]} »"
    )

    return DicterDevisResponse(
        texte_transcrit=texte,
        duree_transcription_s=res["duree_s"],
        duree_agent_ms=duree_agent_ms,
        resultat=resultat,
        usage=usage,
    )


if __name__ == "__main__":
    import uvicorn

    logger.info(f"Démarrage de l'API sur http://{API_HOST}:{API_PORT}")
    uvicorn.run("api:app", host=API_HOST, port=API_PORT, reload=True)

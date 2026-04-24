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

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from clients import creer_client
from config import API_HOST, API_PORT
from main import (
    agent,
    extraire_champ_categorie,
    extraire_champ_client,
    extraire_champ_fourniture,
)
from transcribe import transcrire_bytes

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


class DicterChampResponse(BaseModel):
    champ: str
    texte_transcrit: str
    duree_transcription_s: float
    duree_agent_ms: int
    donnees: dict[str, Any]


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
    logger.info(
        f"OK | transcr {res['duree_s']}s | agent {duree_agent_ms}ms "
        f"| type={resultat.get('type')} | « {texte[:60]} »"
    )

    return DicterDevisResponse(
        texte_transcrit=texte,
        duree_transcription_s=res["duree_s"],
        duree_agent_ms=duree_agent_ms,
        resultat=resultat,
    )


EXTRACTEURS_CHAMP = {
    "client": extraire_champ_client,
    "categorie": extraire_champ_categorie,
    "fourniture": extraire_champ_fourniture,
}


@app.post("/dicter-champ", response_model=DicterChampResponse)
async def dicter_champ(
    champ: str = Form(...),
    audio: UploadFile = File(...),
):
    """Transcrit un audio puis extrait l'info pour un champ donné du formulaire."""
    extracteur = EXTRACTEURS_CHAMP.get(champ)
    if not extracteur:
        raise HTTPException(
            status_code=422,
            detail=f"champ invalide : '{champ}' (attendu : {list(EXTRACTEURS_CHAMP)})",
        )

    data = await audio.read()
    if not data:
        raise HTTPException(status_code=400, detail="Fichier audio vide")

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

    start = time.time()
    try:
        donnees = extracteur(texte)
    except Exception as e:
        logger.error(f"Erreur extraction '{champ}' : {type(e).__name__} — {e}")
        raise HTTPException(status_code=500, detail=f"Extraction : {e}")

    duree_agent_ms = int((time.time() - start) * 1000)
    logger.info(
        f"OK champ={champ} | transcr {res['duree_s']}s "
        f"| agent {duree_agent_ms}ms | « {texte[:60]} »"
    )

    return DicterChampResponse(
        champ=champ,
        texte_transcrit=texte,
        duree_transcription_s=res["duree_s"],
        duree_agent_ms=duree_agent_ms,
        donnees=donnees,
    )


if __name__ == "__main__":
    import uvicorn

    logger.info(f"Démarrage de l'API sur http://{API_HOST}:{API_PORT}")
    uvicorn.run("api:app", host=API_HOST, port=API_PORT, reload=True)

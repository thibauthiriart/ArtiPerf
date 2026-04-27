"""
Wrapper de l'API Whisper d'OpenAI — transcription d'audio en texte.

Utilisé par :
- le CLI main.py (argument fichier audio)
- l'API api.py (endpoint /transcribe et /ask-audio)

Formats audio supportés par Whisper : mp3, mp4, mpeg, mpga, m4a, wav, webm.
Taille max par fichier : 25 MB.
"""

import logging
import time
from pathlib import Path

from openai import OpenAI

from config import WHISPER_MODEL, WHISPER_LANGUAGE, WHISPER_RESPONSE_FORMAT

logger = logging.getLogger("transcribe")

_client = None
MAX_AUDIO_MB = 25


def _get_client():
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


def transcrire_fichier(chemin):
    """Transcrit un fichier audio depuis le disque.

    Args:
        chemin: str ou Path vers le fichier audio.

    Returns:
        dict : {"texte": str, "duree_s": float, "langue": str, "modele": str}
    """
    chemin = Path(chemin)
    if not chemin.exists():
        raise FileNotFoundError(f"Fichier audio introuvable : {chemin}")

    taille_mo = chemin.stat().st_size / (1024 * 1024)
    if taille_mo > MAX_AUDIO_MB:
        raise ValueError(
            f"Fichier trop gros : {taille_mo:.1f} Mo (max {MAX_AUDIO_MB} Mo "
            f"pour l'API Whisper)."
        )

    logger.info(f"Transcription de {chemin.name} ({taille_mo:.1f} Mo)…")
    start = time.time()

    with open(chemin, "rb") as f:
        resultat = _appel_whisper(f, chemin.name)

    duree = time.time() - start
    texte = resultat["texte"]
    logger.info(f"Transcription terminée en {duree:.1f}s → {len(texte)} chars")

    return {
        "texte": texte,
        "duree_s": round(duree, 2),
        "audio_seconds": resultat.get("audio_seconds", 0.0),
        "langue": resultat.get("langue", WHISPER_LANGUAGE),
        "modele": WHISPER_MODEL,
        "taille_mo": round(taille_mo, 2),
    }


def transcrire_bytes(data, nom_fichier="audio.webm"):
    """Transcrit un blob audio en mémoire (utile pour l'upload HTTP).

    Args:
        data: bytes du fichier audio.
        nom_fichier: nom avec extension (Whisper détecte le format dessus).
    """
    taille_mo = len(data) / (1024 * 1024)
    if taille_mo > MAX_AUDIO_MB:
        raise ValueError(
            f"Audio trop gros : {taille_mo:.1f} Mo (max {MAX_AUDIO_MB} Mo)."
        )

    logger.info(f"Transcription de {nom_fichier} ({taille_mo:.1f} Mo)…")
    start = time.time()

    # L'API OpenAI attend un tuple (nom, bytes) pour les uploads en mémoire
    resultat = _appel_whisper((nom_fichier, data), nom_fichier)

    duree = time.time() - start
    texte = resultat["texte"]
    logger.info(f"Transcription terminée en {duree:.1f}s → {len(texte)} chars")

    return {
        "texte": texte,
        "duree_s": round(duree, 2),
        "audio_seconds": resultat.get("audio_seconds", 0.0),
        "langue": resultat.get("langue", WHISPER_LANGUAGE),
        "modele": WHISPER_MODEL,
        "taille_mo": round(taille_mo, 2),
    }


def _appel_whisper(file_arg, nom):
    """Appelle l'API Whisper et normalise la réponse."""
    kwargs = {
        "model": WHISPER_MODEL,
        "file": file_arg,
        "response_format": WHISPER_RESPONSE_FORMAT,
    }
    if WHISPER_LANGUAGE:
        kwargs["language"] = WHISPER_LANGUAGE

    response = _get_client().audio.transcriptions.create(**kwargs)

    # Suivant response_format, l'objet varie
    if WHISPER_RESPONSE_FORMAT == "text":
        return {"texte": str(response), "audio_seconds": 0.0}
    # json / verbose_json → .text existe ; verbose_json fournit aussi .duration
    return {
        "texte": getattr(response, "text", str(response)),
        "langue": getattr(response, "language", None),
        "audio_seconds": float(getattr(response, "duration", 0.0) or 0.0),
    }

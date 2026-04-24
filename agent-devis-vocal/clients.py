"""
Recherche de clients dans la base SQLite clients.db.

Matching : on extrait le nom de famille depuis la dictée (on retire
les civilités et prénoms éventuels) puis on cherche par nom exact
(insensible à la casse/accents).
"""

import logging
import re
import sqlite3
import unicodedata
from pathlib import Path

logger = logging.getLogger("clients")

DB_PATH = Path(__file__).parent / "clients.db"

# Mots à retirer pour isoler le nom de famille
CIVILITES = {
    "m", "m.", "mr", "mr.", "monsieur",
    "mme", "mme.", "madame",
    "mlle", "mlle.", "mademoiselle",
}


def _strip_accents(s):
    """supprime les accents pour la comparaison"""
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def extraire_noms(nom_dicte):
    """
    Depuis une chaîne libre ("Madame Martin", "M. Jean Dupont", "martin"),
    retourne (prenom_probable | None, nom_famille | None).
    Hypothèse : le dernier mot est le nom de famille, l'avant-dernier (si
    présent et non civilité) est le prénom.
    """
    if not nom_dicte:
        return None, None

    txt = _strip_accents(nom_dicte.strip().lower())
    txt = re.sub(r"[^a-z\s\-']", " ", txt)
    mots = [m for m in txt.split() if m and m not in CIVILITES]

    if not mots:
        return None, None
    if len(mots) == 1:
        return None, mots[0]
    return mots[-2], mots[-1]


def rechercher_client(nom_dicte):
    """
    Cherche le client dans clients.db à partir du nom dicté.

    Returns:
        dict : {
            "status": "trouve" | "ambigu" | "inconnu",
            "nom_cherche": str,
            "client": {...} | None,   # rempli si status == "trouve"
            "candidats": [{...}, ...] # rempli si status == "ambigu"
        }
    """
    prenom, nom = extraire_noms(nom_dicte)
    if not nom:
        return {
            "status": "inconnu",
            "nom_cherche": nom_dicte,
            "client": None,
            "candidats": [],
        }

    if not DB_PATH.exists():
        logger.error(f"Base clients absente : {DB_PATH}")
        return {
            "status": "inconnu",
            "nom_cherche": nom,
            "client": None,
            "candidats": [],
        }

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM clients WHERE LOWER(nom) = LOWER(?)",
        (nom,),
    ).fetchall()
    conn.close()

    resultats = [dict(r) for r in rows]

    # Si un prénom a été dicté et qu'il permet de désambiguïser, on filtre
    if prenom and len(resultats) > 1:
        filtres = [
            r for r in resultats
            if _strip_accents(r["prenom"].lower()) == prenom
        ]
        if filtres:
            resultats = filtres

    if len(resultats) == 0:
        status = "inconnu"
        client = None
        candidats = []
    elif len(resultats) == 1:
        status = "trouve"
        client = resultats[0]
        candidats = []
    else:
        status = "ambigu"
        client = None
        candidats = resultats

    logger.info(f"Recherche '{nom_dicte}' → nom='{nom}' → {status} ({len(resultats)} résultat(s))")
    return {
        "status": status,
        "nom_cherche": nom,
        "client": client,
        "candidats": candidats,
    }

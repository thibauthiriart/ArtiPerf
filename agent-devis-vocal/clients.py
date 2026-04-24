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

import jellyfish

logger = logging.getLogger("clients")

# Seuil de similarité Jaro-Winkler pour retenir un candidat phonétique
PHONETIC_THRESHOLD = 0.82
MAX_PHONETIC_CANDIDATES = 5

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

    resultats = [dict(r) for r in rows]

    # Si un prénom a été dicté et qu'il permet de désambiguïser, on filtre
    if prenom and len(resultats) > 1:
        filtres = [
            r for r in resultats
            if _strip_accents(r["prenom"].lower()) == prenom
        ]
        if filtres:
            resultats = filtres

    if len(resultats) == 1:
        conn.close()
        logger.info(f"Recherche '{nom_dicte}' → nom='{nom}' → trouve (exact)")
        return {
            "status": "trouve",
            "nom_cherche": nom,
            "client": resultats[0],
            "candidats": [],
        }

    if len(resultats) > 1:
        conn.close()
        logger.info(f"Recherche '{nom_dicte}' → nom='{nom}' → ambigu ({len(resultats)} exact)")
        return {
            "status": "ambigu",
            "nom_cherche": nom,
            "client": None,
            "candidats": resultats,
        }

    # Pas de match exact → recherche phonétique
    tous = [dict(r) for r in conn.execute("SELECT * FROM clients").fetchall()]
    conn.close()
    candidats = _recherche_phonetique(nom, prenom, tous)

    if candidats:
        logger.info(
            f"Recherche '{nom_dicte}' → nom='{nom}' → phonétique "
            f"({len(candidats)} candidat(s))"
        )
        return {
            "status": "ambigu",
            "nom_cherche": nom,
            "client": None,
            "candidats": candidats,
        }

    logger.info(f"Recherche '{nom_dicte}' → nom='{nom}' → inconnu")
    return {
        "status": "inconnu",
        "nom_cherche": nom,
        "client": None,
        "candidats": [],
    }


def creer_client(data):
    """
    Insère un nouveau client en base. `data` est un dict avec au minimum "nom".
    Les champs manquants sont stockés comme chaîne vide (colonnes NOT NULL).
    Retourne le client complet avec son id.
    """
    nom = (data.get("nom") or "").strip()
    if not nom:
        raise ValueError("Le nom est obligatoire")

    champs = {
        "civilite":    (data.get("civilite")    or "").strip(),
        "prenom":      (data.get("prenom")      or "").strip(),
        "nom":         nom,
        "adresse":     (data.get("adresse")     or "").strip(),
        "code_postal": (data.get("code_postal") or "").strip(),
        "ville":       (data.get("ville")       or "").strip(),
        "telephone":   (data.get("telephone")   or "").strip(),
        "email":       (data.get("email")       or "").strip() or None,
    }

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "INSERT INTO clients "
        "(civilite, prenom, nom, adresse, code_postal, ville, telephone, email) "
        "VALUES (:civilite, :prenom, :nom, :adresse, :code_postal, :ville, "
        ":telephone, :email)",
        champs,
    )
    conn.commit()
    new_id = cur.lastrowid
    row = conn.execute("SELECT * FROM clients WHERE id = ?", (new_id,)).fetchone()
    conn.close()

    logger.info(f"Client créé id={new_id} : {champs['prenom']} {champs['nom']}")
    return dict(row)


def _recherche_phonetique(nom, prenom, tous_clients):
    """
    Cherche des clients par similarité phonétique (metaphone + Jaro-Winkler).
    Retourne jusqu'à MAX_PHONETIC_CANDIDATES résultats triés par score décroissant.
    """
    cible = _strip_accents(nom).lower()
    cible_meta = jellyfish.metaphone(cible)

    scored = []
    for c in tous_clients:
        db_nom = _strip_accents(c["nom"]).lower()
        db_meta = jellyfish.metaphone(db_nom)

        sim = jellyfish.jaro_winkler_similarity(cible, db_nom)
        meta_match = bool(cible_meta) and cible_meta == db_meta

        if not meta_match and sim < PHONETIC_THRESHOLD:
            continue

        score = sim + (0.10 if meta_match else 0)
        if prenom and _strip_accents(c["prenom"]).lower() == prenom:
            score += 0.15

        scored.append((score, c))

    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:MAX_PHONETIC_CANDIDATES]]

"""
Agent "devis vocal" — Point d'entrée principal.

Usage :
    python main.py                         # mode interactif texte (dictée tapée)
    python main.py chemin/vers/audio.mp3   # transcrit puis envoie à l'agent

Formats audio : mp3, mp4, m4a, wav, webm, mpeg, mpga (max 25 Mo).
"""

import json
import logging
import sys

from clients import rechercher_client
from llm import appeler_llm, appeler_llm_json
from memory.store import store, recall_as_text
from transcribe import transcrire_fichier
from config import SYSTEM_PROMPT, DEVIS_EXTRACTION_PROMPT, LLM_MODEL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-12s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("agent")


# === Schéma JSON attendu pour un devis ===
SCHEMA_DEVIS = (
    '{"client": "Nom du client ou null", '
    '"nouveau_client": "true ou false", '
    '"domaine": "type de travaux ou null", '
    '"lignes": ['
    '{"type": "fourniture|pose|frais_annexe", '
    '"sous_type": "transport|deplacement|location_materiel|evacuation_dechets|autre|null", '
    '"description": "texte court", '
    '"marque": "marque ou null", '
    '"unite": "piece|m2|ml|heure|forfait", '
    '"quantite": "nombre ou null", '
    '"prix_unitaire_ht": "nombre ou null", '
    '"prix_a_completer": "true ou false"}'
    ']}'
)

VALID_TYPES = {"fourniture", "pose", "frais_annexe"}
VALID_SOUS_TYPES = {"transport", "deplacement", "location_materiel",
                    "evacuation_dechets", "autre"}
VALID_UNITES = {"piece", "m2", "ml", "heure", "forfait"}


def _to_number(v):
    """Parse souple : 17, 17.5, '17', '17,5', None → float ou None."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _normaliser_ligne(ligne):
    """Force la ligne dans le schéma attendu, valeurs hors enum → défaut sûr."""
    if not isinstance(ligne, dict):
        return None

    type_ = ligne.get("type") if ligne.get("type") in VALID_TYPES else "fourniture"
    sous_type = ligne.get("sous_type")
    if type_ != "frais_annexe" or sous_type not in VALID_SOUS_TYPES:
        sous_type = None

    unite = ligne.get("unite") if ligne.get("unite") in VALID_UNITES else "piece"

    quantite = _to_number(ligne.get("quantite"))
    prix = _to_number(ligne.get("prix_unitaire_ht"))

    return {
        "type": type_,
        "sous_type": sous_type,
        "description": (ligne.get("description") or "").strip() or "—",
        "marque": (ligne.get("marque") or None) if type_ == "fourniture" else None,
        "unite": unite,
        "quantite": quantite,
        "prix_unitaire_ht": prix,
        "prix_a_completer": bool(ligne.get("prix_a_completer")) or prix is None,
    }


def calculer_totaux(devis):
    """Enrichit le devis avec total_ligne_ht et total_devis_ht. Mute et retourne."""
    total = 0.0
    toutes_completes = True
    for ligne in devis.get("lignes", []):
        q = ligne.get("quantite")
        p = ligne.get("prix_unitaire_ht")
        if q is not None and p is not None:
            ligne["total_ligne_ht"] = round(q * p, 2)
            total += ligne["total_ligne_ht"]
        else:
            ligne["total_ligne_ht"] = None
            toutes_completes = False
    devis["total_devis_ht"] = round(total, 2)
    devis["total_complet"] = toutes_completes and bool(devis.get("lignes"))
    return devis


# === Outils de l'agent ===

def extraire_devis(texte):
    """Appelle le LLM avec le prompt d'extraction. Retourne (devis_dict, usage)."""
    logger.info("Outil : extraire_devis")
    prompt = f"{DEVIS_EXTRACTION_PROMPT}\n\nDictée à analyser :\n« {texte} »"
    res = appeler_llm_json(prompt, SCHEMA_DEVIS, system_prompt=SYSTEM_PROMPT)
    donnees = res["data"]

    lignes_brutes = donnees.get("lignes") or donnees.get("fournitures") or []
    lignes = [n for n in (_normaliser_ligne(l) for l in lignes_brutes) if n is not None]

    devis = {
        "client": donnees.get("client"),
        "nouveau_client": bool(donnees.get("nouveau_client")),
        "domaine": donnees.get("domaine"),
        "lignes": lignes,
    }
    calculer_totaux(devis)
    return devis, res["usage"]


def reponse_directe(texte):
    """Répond en texte libre quand la dictée n'est pas un devis. Retourne (texte, usage)."""
    logger.info("Outil : reponse_directe")
    prompt = (
        f"Dictée reçue : « {texte} »\n\n"
        "Elle ne ressemble pas à un devis. Explique poliment à l'utilisateur "
        "(en 1 ou 2 phrases) qu'on attend une dictée de devis (client, "
        "domaine de travaux, fournitures)."
    )
    res = appeler_llm(prompt, system_prompt=SYSTEM_PROMPT)
    return res["texte"], res["usage"]


# === Agent : routeur + exécution ===

def agent(texte):
    """
    Analyse la dictée, choisit l'outil adapté, puis l'exécute.

    Returns:
        dict : {"type": "devis"|"autre", "devis": {...}|None, "message": str}
    """
    store({"role": "user", "content": texte})
    context = recall_as_text()

    logger.info(f"Dictée reçue : {texte[:80]}")

    # --- Étape 1 : raisonnement — quel outil ? ---
    decision_res = appeler_llm_json(
        f"""Dictée de l'utilisateur : « {texte} »

Contexte récent :
{context}

Tu es un agent qui traite des dictées vocales d'artisans.
Outils disponibles :
- extraire_devis : quand la dictée décrit un devis (mentionne un client,
  des travaux, des fournitures, des quantités, des marques).
- reponse_directe : quand la dictée est hors contexte (salutation, blague,
  question sans rapport, silence retranscrit…).

Choisis l'outil le plus adapté.""",
        '{"reflexion": "ce que je pense", '
        '"outil": "extraire_devis|reponse_directe"}',
        system_prompt=SYSTEM_PROMPT,
    )

    decision = decision_res["data"]
    usage_routeur = decision_res["usage"]
    reflexion = decision.get("reflexion", "?")
    outil = decision.get("outil", "extraire_devis")
    logger.info(f"Réflexion : {reflexion}")
    logger.info(f"Outil choisi : {outil}")

    # --- Étape 2 : action ---
    if outil == "extraire_devis":
        devis, usage_outil = extraire_devis(texte)

        # Enrichissement : recherche du client en base
        nom_dicte = devis.get("client")
        if devis.get("nouveau_client"):
            devis["client_db"] = {
                "status": "inconnu",
                "nom_cherche": nom_dicte,
                "client": None,
                "candidats": [],
            }
        elif nom_dicte:
            devis["client_db"] = rechercher_client(nom_dicte)
        else:
            devis["client_db"] = {
                "status": "inconnu",
                "nom_cherche": None,
                "client": None,
                "candidats": [],
            }

        message = "Devis extrait avec succès."
        resultat = {"type": "devis", "devis": devis, "message": message}
    else:
        message, usage_outil = reponse_directe(texte)
        resultat = {"type": "autre", "devis": None, "message": message}

    resultat["usage_llm"] = {
        "routeur": {**usage_routeur, "model": LLM_MODEL},
        "outil": {**usage_outil, "model": LLM_MODEL, "nom": outil},
    }

    store({"role": "assistant", "content": json.dumps(resultat, ensure_ascii=False)})
    return resultat


# === Point d'entrée CLI ===
if __name__ == "__main__":
    print("=" * 60)
    print("  Agent Devis Vocal — POC")
    print("=" * 60)

    # --- Mode fichier audio en argument ---
    if len(sys.argv) > 1:
        chemin_audio = sys.argv[1]
        print(f"\nTranscription de : {chemin_audio}")
        try:
            res = transcrire_fichier(chemin_audio)
        except (FileNotFoundError, ValueError) as e:
            print(f"Erreur : {e}")
            sys.exit(1)

        print(f"Texte reconnu ({res['duree_s']}s, {res['taille_mo']} Mo) :")
        print(f"   « {res['texte']} »\n")

        resultat = agent(res["texte"])
        print(json.dumps(resultat, ensure_ascii=False, indent=2))
        sys.exit(0)

    # --- Mode interactif texte ---
    print("Tapez votre dictée (ou 'quit' pour sortir) :")
    while True:
        try:
            texte = input("\nDictée : ").strip()
            if texte.lower() in ("quit", "exit", "q"):
                print("Au revoir !")
                break
            if not texte:
                continue

            resultat = agent(texte)
            print(json.dumps(resultat, ensure_ascii=False, indent=2))
        except KeyboardInterrupt:
            print("\nAu revoir !")
            break

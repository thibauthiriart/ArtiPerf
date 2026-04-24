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
from config import SYSTEM_PROMPT, DEVIS_EXTRACTION_PROMPT

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
    '"fournitures": ['
    '{"description": "produit", "marque": "marque ou null", "quantite": "nombre ou null"}'
    ']}'
)


# === Outils de l'agent ===

def extraire_devis(texte):
    """Appelle le LLM avec le prompt d'extraction et retourne un JSON structuré."""
    logger.info("Outil : extraire_devis")
    prompt = f"{DEVIS_EXTRACTION_PROMPT}\n\nDictée à analyser :\n« {texte} »"
    donnees = appeler_llm_json(prompt, SCHEMA_DEVIS, system_prompt=SYSTEM_PROMPT)

    # On force la forme attendue même si le LLM renvoie autre chose
    return {
        "client": donnees.get("client"),
        "nouveau_client": bool(donnees.get("nouveau_client")),
        "domaine": donnees.get("domaine"),
        "fournitures": donnees.get("fournitures", []) or [],
    }


def reponse_directe(texte):
    """Répond en texte libre quand la dictée n'est pas un devis."""
    logger.info("Outil : reponse_directe")
    prompt = (
        f"Dictée reçue : « {texte} »\n\n"
        "Elle ne ressemble pas à un devis. Explique poliment à l'utilisateur "
        "(en 1 ou 2 phrases) qu'on attend une dictée de devis (client, "
        "domaine de travaux, fournitures)."
    )
    return appeler_llm(prompt, system_prompt=SYSTEM_PROMPT)


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
    decision = appeler_llm_json(
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

    reflexion = decision.get("reflexion", "?")
    outil = decision.get("outil", "extraire_devis")
    logger.info(f"Réflexion : {reflexion}")
    logger.info(f"Outil choisi : {outil}")

    # --- Étape 2 : action ---
    if outil == "extraire_devis":
        devis = extraire_devis(texte)

        # Enrichissement : recherche du client en base
        nom_dicte = devis.get("client")
        if devis.get("nouveau_client"):
            # L'utilisateur a explicitement signalé un nouveau client :
            # on saute la recherche BDD pour afficher directement le formulaire.
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
        message = reponse_directe(texte)
        resultat = {"type": "autre", "devis": None, "message": message}

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

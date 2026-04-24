"""
Mémoire de conversation de l'agent.
- Mémoire courte (session) : liste Python en mémoire
- Persistance simple : sauvegarde/chargement JSON sur disque
"""

import json
import logging
from config import MAX_MEMORY

logger = logging.getLogger("memory")

# Stockage en mémoire
_memory = []


def store(message):
    """
    Ajoute un message à la mémoire.

    Args:
        message: dict avec 'role' ("user" ou "assistant") et 'content' (texte).
    """
    _memory.append(message)
    if len(_memory) > MAX_MEMORY:
        _memory.pop(0)  # Supprimer le plus ancien
    logger.debug(f"Mémoire : {len(_memory)} messages (max {MAX_MEMORY})")


def recall(n=5):
    """Retourne les n derniers messages."""
    return _memory[-n:]


def recall_as_text(n=5):
    """Retourne la mémoire formatée pour injection dans le prompt."""
    messages = recall(n)
    if not messages:
        return ""
    return "\n".join([f"{m['role']}: {m['content']}" for m in messages])


def clear():
    """Vide la mémoire."""
    _memory.clear()
    logger.info("Mémoire vidée.")


def save_to_file(path="memory.json"):
    """Sauvegarde la mémoire sur disque."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_memory, f, ensure_ascii=False, indent=2)
    logger.info(f"Mémoire sauvegardée dans {path}")


def load_from_file(path="memory.json"):
    """Charge la mémoire depuis le disque."""
    global _memory
    try:
        with open(path, "r", encoding="utf-8") as f:
            _memory = json.load(f)
        logger.info(f"Mémoire chargée depuis {path} ({len(_memory)} messages)")
    except FileNotFoundError:
        _memory = []
        logger.info("Aucun fichier mémoire trouvé, démarrage à vide.")

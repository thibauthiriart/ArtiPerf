"""
Configuration globale de l'agent "devis vocal".
Les clés API sont lues depuis le fichier .env.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ================================================================
# LLM — Modèle de langage
# ================================================================
LLM_PROVIDER = "openai"              # "openai" ou "anthropic"
LLM_MODEL = "gpt-4o-mini"            # rapide et peu coûteux pour un POC
TEMPERATURE = 0.1                    # extraction déterministe
MAX_TOKENS = 1024

# ================================================================
# CLÉS API (depuis .env)
# ================================================================
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")

# ================================================================
# Whisper — Transcription audio
# ================================================================
WHISPER_MODEL = "whisper-1"
WHISPER_LANGUAGE = "fr"
WHISPER_RESPONSE_FORMAT = "json"

# ================================================================
# API FastAPI
# ================================================================
API_HOST = os.environ.get("API_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("API_PORT", 8000))

# ================================================================
# MÉMOIRE
# ================================================================
MAX_MEMORY = 10

# ================================================================
# AGENT — System prompt général
# ================================================================
SYSTEM_PROMPT = """Tu es un assistant spécialisé dans la prise de notes vocales
pour des devis d'artisan (carrelage, plomberie, peinture, menuiserie, etc.).

RÈGLES :
- Tu extraits les informations métier depuis une dictée libre.
- Tu réponds toujours en français.
- Tu n'inventes jamais d'information : si une donnée est absente, tu laisses null.
- Tu respectes scrupuleusement les schémas JSON demandés.
"""

# ================================================================
# Prompt d'extraction du devis
# ================================================================
DEVIS_EXTRACTION_PROMPT = """Tu analyses une dictée d'artisan décrivant un devis.
Extrais les informations essentielles et renvoie-les en JSON.

Règles d'extraction :
- "client" : le nom du client tel que dicté, proprement capitalisé
  (ex : "madame martin" → "Madame Martin", "monsieur dupont" → "Monsieur Dupont").
  Si absent, mets null.
- "domaine" : le type de travaux évoqué (carrelage, plomberie, peinture,
  menuiserie, électricité, maçonnerie, etc.), en minuscules. Si absent, mets null.
- "fournitures" : liste des articles/matériaux dictés. Pour chacun :
    * "description" : nom du produit en minuscules (ex: "carreaux", "robinet")
    * "marque" : marque citée (respect de la casse d'origine de la marque),
      null si non précisée. Attention : Whisper peut mal transcrire les noms
      de marque ("de la fond" → "Delafon", "grosse foie" → "Grohe", etc.) :
      reconnais les marques plausibles du BTP quand c'est évident.
    * "quantite" : nombre entier si une quantité chiffrée est donnée,
      null si c'est vague ("tant de", "quelques", "plusieurs") ou absent.
- Si la dictée ne ressemble pas à un devis, renvoie tous les champs à null
  et "fournitures": [].
"""

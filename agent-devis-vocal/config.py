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
WHISPER_RESPONSE_FORMAT = "verbose_json"  # nécessaire pour récupérer la durée audio facturable

# ================================================================
# Prix API OpenAI (USD) — à actualiser si OpenAI change ses tarifs.
# Cohérents avec le modèle déclaré dans LLM_MODEL ci-dessus (gpt-4o-mini).
# ================================================================
PRICE_LLM_INPUT_PER_MTOK = 0.15      # $ / 1M input tokens
PRICE_LLM_OUTPUT_PER_MTOK = 0.60     # $ / 1M output tokens
PRICE_WHISPER_PER_MIN = 0.006        # $ / minute audio

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

Tous les prix sont en EUROS HORS TAXES (HT) — la TVA sera ajoutée plus tard.
N'INVENTE JAMAIS un prix : si l'artisan ne le dicte pas, mets null et signale-le.

============================================================
CHAMPS DE PREMIER NIVEAU
============================================================

- "client" : nom du client dicté, proprement capitalisé
  (ex: "madame martin" → "Madame Martin"). null si absent.
  Si "nouveau client Jean Dupont" → extrais "Jean Dupont" sans "nouveau client".

- "nouveau_client" : true si la dictée signale explicitement la création
  ("nouveau client", "client inconnu", "pas encore dans la base", "à créer").

- "domaine" : type de travaux en minuscules (carrelage, plomberie, peinture,
  menuiserie, électricité, maçonnerie, etc.). null si absent.

- "lignes" : liste des lignes du devis (fournitures, prestations, frais).
  Chaque ligne suit le schéma ci-dessous. [] si rien à extraire.

============================================================
SCHÉMA D'UNE LIGNE
============================================================

{
  "type": "fourniture" | "pose" | "frais_annexe",
  "sous_type": null | "transport" | "deplacement" | "location_materiel"
               | "evacuation_dechets" | "autre",
  "description": "texte court en minuscules",
  "marque": "Marque" | null,
  "unite": "piece" | "m2" | "ml" | "heure" | "forfait",
  "quantite": nombre | null,
  "prix_unitaire_ht": nombre | null,
  "prix_a_completer": true | false
}

Règles par champ :

- "type" :
  * "fourniture" → matériel, produit, article (carreaux, robinet, peinture, vis…)
  * "pose" → main d'œuvre, prestation de pose, installation, travaux.
    ⚠️ Whisper transcrit souvent "pose" en "pause" : "30 € de pause" =
    "30 € de POSE". Corrige systématiquement.
  * "frais_annexe" → tout le reste (livraison, déplacement, location, déchets…).

- "sous_type" : UNIQUEMENT pour type="frais_annexe", sinon null.
  * "transport" → livraison de matériel, port
  * "deplacement" → trajet de l'artisan (km, péages)
  * "location_materiel" → échafaudage, nacelle, perforateur, benne…
  * "evacuation_dechets" → benne à gravats, déchetterie
  * "autre" → tout le reste

- "marque" : casse d'origine respectée (Grohe, Delafon, Knauf, Placo,
  Sika, Weber, Marazzi, Tarkett, Sigma, Tollens, Bosch, Makita…).
  Whisper massacre les marques : "de la fond" → "Delafon",
  "grosse foie" → "Grohe", "vé bère" → "Weber". Reconnais quand c'est évident.
  null si pas de marque dictée. Vide pour pose/frais_annexe.

- "unite" :
  * "piece" → vendu à l'unité (lavabo, robinet, sac de plâtre, pot de peinture)
  * "m2" → au mètre carré (carrelage, peinture mur, isolation)
  * "ml" → au mètre linéaire (plinthe, gouttière, tuyau, baguette)
  * "heure" → à l'heure (typiquement la pose)
  * "forfait" → montant global non décomposable (déplacement forfait, pose
    comprise sans détail). Dans ce cas quantite = 1.

- "quantite" : nombre (entier ou décimal pour les m²/ml/heures).
  null si vague ("quelques", "plusieurs", "tant de") ou absent.

- "prix_unitaire_ht" : prix HT à l'unité dictée.
  ⚠️ Si la dictée donne un PRIX TOTAL et une QUANTITÉ
  ("500 € pour 20 m² de carrelage"), divise : prix_unitaire = 500 / 20 = 25.
  null si non dicté.

- "prix_a_completer" : true SI prix_unitaire_ht est null (à compléter manuellement).
  false sinon.

============================================================
EXEMPLES
============================================================

Dictée : "devis pour Madame Dupont en carrelage. 17 mètres carrés de carreaux
Marazzi à 25 € le m². Pose à 30 € le m². Forfait livraison 50 €."

→ lignes : [
  {"type":"fourniture","sous_type":null,"description":"carreaux",
   "marque":"Marazzi","unite":"m2","quantite":17,"prix_unitaire_ht":25,
   "prix_a_completer":false},
  {"type":"pose","sous_type":null,"description":"pose carrelage",
   "marque":null,"unite":"m2","quantite":17,"prix_unitaire_ht":30,
   "prix_a_completer":false},
  {"type":"frais_annexe","sous_type":"transport","description":"livraison",
   "marque":null,"unite":"forfait","quantite":1,"prix_unitaire_ht":50,
   "prix_a_completer":false}
]

Dictée : "trois lavabos Grohe et un robinet, j'ai pas le prix"
→ lignes : [
  {"type":"fourniture","sous_type":null,"description":"lavabos",
   "marque":"Grohe","unite":"piece","quantite":3,"prix_unitaire_ht":null,
   "prix_a_completer":true},
  {"type":"fourniture","sous_type":null,"description":"robinet",
   "marque":null,"unite":"piece","quantite":1,"prix_unitaire_ht":null,
   "prix_a_completer":true}
]

Si la dictée n'est pas un devis : renvoie tous les champs à null et "lignes": [].
"""

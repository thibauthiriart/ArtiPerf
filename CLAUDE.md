# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Contexte parent** : ce dossier est un POC autonome (repo git séparé) pour la fonctionnalité **devis vocal** d'Artiperf. Le contexte produit/contractuel global est dans `/var/www/local/artiperf/CLAUDE.md` (à lire avant toute discussion scope/budget). Ici on documente uniquement le code du POC.

## 1. Nature du POC

Démontrer la chaîne **dictée micro → transcription Whisper → extraction JSON structurée (client, domaine, fournitures) → match en base clients**. C'est un prototype jetable, pas du code de production : l'objectif est de valider l'UX et le prompt engineering avant la réécriture en Laravel/Vue prévue au MVP.

Divergence assumée avec le MVP cible :
- Stack POC : **Python + FastAPI + OpenAI (Whisper + GPT-4o-mini)**
- Stack MVP cible : **Laravel 11 + Vue 3 + Web Speech API + Claude Haiku 4.5**

Ne pas chercher à aligner le POC sur la stack cible — ce qu'on transpose, c'est le prompt + le flow agent, pas le code.

## 2. Commandes

Tout se passe dans `agent-devis-vocal/`. **Toujours utiliser `.venv/bin/python`** (Debian/Ubuntu PEP 668 interdit le pip global).

```bash
cd agent-devis-vocal

# Setup initial
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python seed_db.py             # crée clients.db (50 clients fictifs, plusieurs "Martin" pour tester l'ambiguïté)
.venv/bin/python seed_db.py --reset     # recrée la base à zéro

# Lancer le serveur (http://127.0.0.1:8000/, Swagger sur /docs)
.venv/bin/python api.py

# Mode CLI sans navigateur
.venv/bin/python main.py                          # dictée tapée
.venv/bin/python main.py chemin/vers/audio.mp3    # transcrire un fichier
```

Pas de suite de tests automatisés. Recette manuelle via les 4 scénarios documentés dans `agent-devis-vocal/README.md` (Dupont = match unique, Martin = ambiguïté, Isabelle Martin = désambiguïsation par prénom, Lecoustre = inconnu).

`.env` est obligatoire avec `OPENAI_API_KEY=sk-...` (Whisper + GPT). Les clés `ANTHROPIC_API_KEY` / `MISTRAL_API_KEY` ne servent que si on bascule `LLM_PROVIDER` dans `config.py`.

Contrainte navigateur : `MediaRecorder` exige HTTPS **ou** `localhost`/`127.0.0.1`. `0.0.0.0` ne marche pas depuis un autre poste sans certificat — c'est volontaire, ne pas chercher à contourner pour un POC local.

## 3. Architecture du flow agent

Le cœur est dans `main.py:agent()`. Pour chaque dictée, deux appels LLM séquentiels :

1. **Routeur** (`appeler_llm_json` avec décision `extraire_devis | reponse_directe`) — le LLM choisit l'outil. Le contexte des 5 derniers messages est injecté depuis `memory/store.py`.
2. **Outil sélectionné** :
   - `extraire_devis` → appel LLM avec `DEVIS_EXTRACTION_PROMPT` + schéma JSON forcé, puis enrichissement BDD via `clients.rechercher_client()`
   - `reponse_directe` → réponse texte libre

Si le LLM marque `nouveau_client: true` dans l'extraction, on **court-circuite la recherche BDD** et on renvoie directement `status: "inconnu"` pour déclencher le formulaire de création côté front. C'est intentionnel — ne pas re-router vers le matcher dans ce cas.

Schéma de réponse `agent()` toujours : `{"type": "devis"|"autre", "devis": {...}|None, "message": str}`. L'API HTTP enveloppe ça dans `DicterDevisResponse` avec les durées.

## 4. Matching client (`clients.py`)

Le pipeline est en deux passes — toute modification doit préserver l'ordre :

1. **Match exact insensible casse/accents** sur `nom`. Si un prénom est dicté et qu'il y a plusieurs résultats, on filtre par prénom (désambiguïsation).
2. **Recherche phonétique** (fallback si pas de match exact) : Metaphone + Jaro-Winkler avec seuil `PHONETIC_THRESHOLD = 0.82`. Bonus de score si match metaphone (+0.10) ou prénom identique (+0.15). Max 5 candidats.

`extraire_noms()` isole le nom de famille en retirant les civilités (M., Mme, Mlle, Monsieur…) et part du principe que **le dernier mot = nom de famille**, l'avant-dernier = prénom. Cette heuristique est volontairement simple — les noms composés ne sont pas gérés et c'est OK pour le POC.

Statuts retournés : `"trouve"` (1 candidat), `"ambigu"` (2+ candidats, à choisir côté UI), `"inconnu"` (0 candidat ou base absente).

## 5. Couche LLM (`llm.py`)

Wrapper multi-provider (`openai` / `anthropic` / `mistral`) qui charge dynamiquement le SDK pour ne pas forcer toutes les dépendances. Stratégie de retry :
- **Auth errors** → pas de retry, message clair sur `.env`
- **Connection / Timeout** → retry exponentiel ×2 (délai 1s puis 2s)
- **Rate limit** → retry plus agressif ×2 (délai 1s puis 4s)
- **Status errors / inattendues** → pas de retry

`appeler_llm_json()` post-parse la réponse, avec fallback regex `\{.*\}` si le LLM ajoute du texte autour. Toujours retourner `{"erreur": "...", "brut": "..."}` en cas d'échec — les appelants en dépendent.

## 6. Prompts (`config.py`)

Les prompts sont des constantes module — pas de templating dynamique externe. Modifier directement `SYSTEM_PROMPT` et `DEVIS_EXTRACTION_PROMPT`. Points sensibles validés en recette à ne pas casser :
- Reconnaissance des marques BTP malgré erreurs Whisper ("de la fond" → Delafon, "grosse foie" → Grohe)
- `nouveau_client: true` quand l'utilisateur dit "nouveau client X" / "à créer" / "pas encore dans la base"
- `quantite: null` pour les vagues ("quelques", "plusieurs")
- Capitalisation propre du `client` ("madame martin" → "Madame Martin")

Si on touche `LLM_MODEL`, vérifier que le modèle supporte `response_format` ou que la post-extraction regex tient.

## 7. Front (`static/`)

HTML/JS/CSS vanilla, pas de framework. `app.js` utilise `MediaRecorder` natif (format `audio/webm`), POST sur `/dicter-devis`, rendu à plat. Pas de build step. Toute évolution UI doit rester dans cet esprit — le vrai front sera Vue dans le MVP.

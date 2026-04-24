# Agent Devis Vocal — POC

Dicter la description d'un devis à la voix et obtenir en sortie un JSON structuré
(client, domaine, fournitures) enrichi automatiquement par les infos d'un client
retrouvé dans une base SQLite.

## Stack

- **Python 3.10+** — backend
- **FastAPI** + **Uvicorn** — serveur HTTP
- **OpenAI** — Whisper (transcription) + GPT-4o-mini (extraction / routeur d'agent)
- **SQLite** — base `clients.db` (50 clients fictifs)
- **HTML/JS/CSS vanilla** — frontend avec `MediaRecorder`

## Prérequis

- Python 3.10 ou plus (vérifier avec `python3 --version`)
- Une **clé API OpenAI** (https://platform.openai.com/api-keys)
- Un navigateur moderne avec autorisation micro (Chrome, Firefox, Safari)

## Installation

```bash
cd agent-devis-vocal

# 1. Créer un environnement virtuel (obligatoire sur Debian/Ubuntu à cause de PEP 668)
python3 -m venv .venv

# 2. Installer les dépendances dans le venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

## Configuration

Éditer `.env` à la racine du dossier et renseigner la clé OpenAI :

```
OPENAI_API_KEY=sk-...
```

Les autres clés (`ANTHROPIC_API_KEY`, `MISTRAL_API_KEY`) peuvent rester à `test` :
elles ne sont pas utilisées tant que `LLM_PROVIDER = "openai"` dans `config.py`.

> Le fichier `.env` est déjà dans `.gitignore`, il ne sera jamais committé.

## Initialiser la base clients

```bash
.venv/bin/python seed_db.py          # crée clients.db avec 50 clients fictifs
.venv/bin/python seed_db.py --reset  # supprime et recrée la base
```

Fait une seule fois (la base est ensuite persistée dans `clients.db`).

## Lancer le serveur

```bash
.venv/bin/python api.py
```

Puis ouvrir **http://127.0.0.1:8000/** dans le navigateur.
Le port peut être changé via `.env` (`API_PORT=...`).

## Utilisation

1. Cliquer sur le bouton micro bleu
2. Autoriser l'accès au micro (première fois seulement)
3. Dicter un devis, par exemple :
   > *« Devis pour Monsieur Dupont en plomberie, on va installer un robinet
   > Grohe et deux lavabos. »*
4. Re-cliquer sur le micro pour arrêter l'enregistrement
5. Le résultat s'affiche :
   - **Transcription** (texte brut de Whisper)
   - **Devis extrait** (client, domaine, fournitures, adresse si client identifié)
   - **Fiche client** (fiche DB si trouvé, liste à choisir si ambigu, message si inconnu)

### Trois scénarios à tester

| Dictée                                     | Résultat attendu                         |
|-------------------------------------------|------------------------------------------|
| « devis pour monsieur Dupont en plomberie » | Match unique → Pierre Dupont (Lyon)     |
| « devis pour madame Martin en carrelage »   | 3 candidats → cliquer pour en choisir un |
| « devis pour Isabelle Martin en carrelage » | Match unique via prénom → Isabelle Martin|
| « devis pour monsieur Lecoustre »           | Client inconnu (message rouge)           |

## Endpoints API

| Méthode | Route            | Description                                      |
|---------|------------------|--------------------------------------------------|
| GET     | `/`              | Page web (frontend)                              |
| GET     | `/health`        | Healthcheck JSON                                 |
| POST    | `/transcribe`    | Audio → texte (debug)                            |
| POST    | `/dicter-devis`  | Audio → transcription + extraction + match DB    |

Documentation Swagger : **http://127.0.0.1:8000/docs**

## Mode CLI (sans navigateur)

```bash
.venv/bin/python main.py                # dictée tapée au clavier
.venv/bin/python main.py chemin/vers/audio.mp3   # transcrit un fichier audio
```

## Structure du projet

```
agent-devis-vocal/
├── .env                  # clés API (ignoré par git)
├── .venv/                # environnement Python (ignoré par git)
├── requirements.txt      # dépendances Python
├── config.py             # paramètres LLM, Whisper, API, prompts
├── llm.py                # wrapper multi-provider (OpenAI / Anthropic / Mistral)
├── transcribe.py         # wrapper Whisper (OpenAI)
├── clients.py            # recherche par nom dans clients.db
├── seed_db.py            # script de création/seed de la base
├── clients.db            # base SQLite (générée par seed_db.py)
├── main.py               # agent (routeur + outils extraire_devis / reponse_directe)
├── api.py                # serveur FastAPI
├── memory/               # mémoire conversationnelle courte
└── static/
    ├── index.html        # UI micro
    ├── app.js            # enregistrement + rendu
    └── style.css         # design clair
```

## Paramètres ajustables (`config.py`)

| Variable        | Rôle                                           | Défaut           |
|-----------------|------------------------------------------------|------------------|
| `LLM_PROVIDER`  | `"openai"`, `"anthropic"` ou `"mistral"`       | `openai`         |
| `LLM_MODEL`     | Modèle de génération                           | `gpt-4o-mini`    |
| `TEMPERATURE`   | Déterminisme du LLM (0 = stable)               | `0.1`            |
| `WHISPER_MODEL` | Modèle de transcription                        | `whisper-1`      |
| `WHISPER_LANGUAGE` | Langue forcée (ISO-639-1) ou `None` = auto | `fr`             |
| `API_PORT`      | Port du serveur (via `.env`)                   | `8000`           |

## Dépannage

**`error: externally-managed-environment` au `pip install`**
Utilise le venv (cf. section Installation) — ne jamais installer en global sur Debian/Ubuntu.

**`ModuleNotFoundError: No module named 'dotenv'`**
Tu lances `python` au lieu de `.venv/bin/python` (ou le venv n'est pas activé).

**Micro non détecté dans le navigateur**
L'API `MediaRecorder` exige HTTPS **ou** un accès via `localhost` / `127.0.0.1`.
Utiliser `0.0.0.0` ne fonctionne pas depuis un autre poste sans certificat.

**Clé API OpenAI invalide**
Vérifier `.env` : la clé doit commencer par `sk-...` et être active sur https://platform.openai.com/.

## Coût indicatif

Environ **1 à 2 centimes par dictée** :
- Whisper : ~0,6 ¢/minute
- 2 appels GPT-4o-mini (routeur + extraction) : quelques millicents

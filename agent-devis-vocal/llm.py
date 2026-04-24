"""
Couche d'abstraction pour les appels LLM.
Supporte Anthropic (Claude), OpenAI et Mistral.
Gestion complète des exceptions API.
"""

import json
import re
import time
import logging

from config import (
    LLM_PROVIDER, LLM_MODEL, TEMPERATURE, MAX_TOKENS, SYSTEM_PROMPT,
    ANTHROPIC_API_KEY, OPENAI_API_KEY, MISTRAL_API_KEY
)

logger = logging.getLogger("llm")

# Nombre de tentatives en cas d'erreur temporaire
MAX_RETRIES = 2
RETRY_BASE_DELAY = 1  # secondes


def appeler_llm(question, system_prompt=None, temperature=None, max_tokens=None):
    """
    Appelle le LLM configuré et retourne la réponse texte.
    Gère toutes les exceptions API avec retry sur les erreurs temporaires.
    """
    system_prompt = system_prompt or SYSTEM_PROMPT
    temperature = temperature if temperature is not None else TEMPERATURE
    max_tokens = max_tokens or MAX_TOKENS

    for attempt in range(MAX_RETRIES + 1):
        start = time.time()
        try:
            if LLM_PROVIDER == "anthropic":
                return _appeler_anthropic(question, system_prompt, temperature, max_tokens)
            elif LLM_PROVIDER == "openai":
                return _appeler_openai(question, system_prompt, temperature, max_tokens)
            elif LLM_PROVIDER == "mistral":
                return _appeler_mistral(question, system_prompt, temperature, max_tokens)
            else:
                return f"Erreur : provider '{LLM_PROVIDER}' non supporté."

        # === Erreurs d'authentification (pas de retry) ===
        except _get_auth_errors() as e:
            logger.error(f"Clé API invalide ({LLM_PROVIDER}) : {e}")
            return "Erreur : clé API invalide. Vérifiez votre configuration dans .env."

        # === Erreurs de connexion (retry) ===
        except _get_connection_errors() as e:
            duration = time.time() - start
            if attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(f"Erreur connexion ({duration:.1f}s), retry {attempt+1}/{MAX_RETRIES} dans {delay}s : {e}")
                time.sleep(delay)
            else:
                logger.error(f"Erreur connexion après {MAX_RETRIES} tentatives : {e}")
                return "Erreur : impossible de joindre le service. Vérifiez votre connexion internet."

        # === Timeout (retry) ===
        except _get_timeout_errors() as e:
            duration = time.time() - start
            if attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(f"Timeout ({duration:.1f}s), retry {attempt+1}/{MAX_RETRIES} dans {delay}s")
                time.sleep(delay)
            else:
                logger.error(f"Timeout après {MAX_RETRIES} tentatives : {e}")
                return "Erreur : le service met trop de temps à répondre. Réessayez dans quelques instants."

        # === Rate limit / quota dépassé (retry avec délai plus long) ===
        except _get_rate_limit_errors() as e:
            duration = time.time() - start
            if attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * (4 ** attempt)  # Backoff plus agressif
                logger.warning(f"Rate limit ({duration:.1f}s), retry {attempt+1}/{MAX_RETRIES} dans {delay}s : {e}")
                time.sleep(delay)
            else:
                logger.error(f"Rate limit dépassé après {MAX_RETRIES} tentatives : {e}")
                return "Erreur : quota API dépassé. Attendez quelques minutes ou vérifiez votre plan."

        # === Erreur de statut API (modèle inexistant, requête invalide, etc.) ===
        except _get_status_errors() as e:
            duration = time.time() - start
            logger.error(f"Erreur API ({duration:.1f}s) : {e}")
            return f"Erreur API : {e}"

        # === Erreur inattendue (pas de retry) ===
        except Exception as e:
            duration = time.time() - start
            logger.error(f"Erreur inattendue ({duration:.1f}s) : {type(e).__name__} — {e}")
            return f"Erreur inattendue : {e}"

    return "Erreur : échec après plusieurs tentatives."


def appeler_llm_json(question, schema_attendu, system_prompt=None):
    """
    Appelle le LLM et parse la réponse en JSON.
    Fallback regex si le LLM ajoute du texte autour du JSON.
    """
    prompt_json = f"""{question}

Réponds UNIQUEMENT en JSON valide avec ce schéma :
{schema_attendu}

Ne mets aucun texte avant ou après le JSON."""

    reponse_brute = appeler_llm(prompt_json, system_prompt)

    # Si c'est un message d'erreur, le retourner tel quel
    if reponse_brute.startswith("Erreur"):
        return {"erreur": reponse_brute}

    try:
        return json.loads(reponse_brute)
    except json.JSONDecodeError:
        # Fallback : extraire le JSON du texte
        match = re.search(r'\{.*\}', reponse_brute, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return {"erreur": "Réponse non-JSON", "brut": reponse_brute}


# ================================================================
# Helpers pour récupérer les classes d'exception par provider
# (importées dynamiquement pour ne pas forcer l'install de tous les SDK)
# ================================================================

def _get_auth_errors():
    """Retourne le tuple des exceptions d'authentification selon le provider."""
    errors = []
    if LLM_PROVIDER == "openai":
        try:
            from openai import AuthenticationError
            errors.append(AuthenticationError)
        except ImportError:
            pass
    elif LLM_PROVIDER == "anthropic":
        try:
            from anthropic import AuthenticationError
            errors.append(AuthenticationError)
        except ImportError:
            pass
    return tuple(errors) if errors else (type(None),)


def _get_connection_errors():
    """Retourne le tuple des exceptions de connexion selon le provider."""
    errors = []
    if LLM_PROVIDER == "openai":
        try:
            from openai import APIConnectionError
            errors.append(APIConnectionError)
        except ImportError:
            pass
    elif LLM_PROVIDER == "anthropic":
        try:
            from anthropic import APIConnectionError
            errors.append(APIConnectionError)
        except ImportError:
            pass
    errors.append(ConnectionError)
    return tuple(errors)


def _get_timeout_errors():
    """Retourne le tuple des exceptions de timeout selon le provider."""
    errors = []
    if LLM_PROVIDER == "openai":
        try:
            from openai import APITimeoutError
            errors.append(APITimeoutError)
        except ImportError:
            pass
    elif LLM_PROVIDER == "anthropic":
        try:
            from anthropic import APITimeoutError
            errors.append(APITimeoutError)
        except ImportError:
            pass
    errors.append(TimeoutError)
    return tuple(errors)


def _get_rate_limit_errors():
    """Retourne le tuple des exceptions de rate limit selon le provider."""
    errors = []
    if LLM_PROVIDER == "openai":
        try:
            from openai import RateLimitError
            errors.append(RateLimitError)
        except ImportError:
            pass
    elif LLM_PROVIDER == "anthropic":
        try:
            from anthropic import RateLimitError
            errors.append(RateLimitError)
        except ImportError:
            pass
    return tuple(errors) if errors else (type(None),)


def _get_status_errors():
    """Retourne le tuple des exceptions de statut API selon le provider."""
    errors = []
    if LLM_PROVIDER == "openai":
        try:
            from openai import APIStatusError, BadRequestError, NotFoundError, PermissionDeniedError
            errors.extend([APIStatusError, BadRequestError, NotFoundError, PermissionDeniedError])
        except ImportError:
            pass
    elif LLM_PROVIDER == "anthropic":
        try:
            from anthropic import APIStatusError, BadRequestError, NotFoundError, PermissionDeniedError
            errors.extend([APIStatusError, BadRequestError, NotFoundError, PermissionDeniedError])
        except ImportError:
            pass
    return tuple(errors) if errors else (type(None),)


# ================================================================
# Providers
# ================================================================

def _appeler_openai(question, system_prompt, temperature, max_tokens):
    """Appel via le SDK OpenAI."""
    from openai import OpenAI

    client = OpenAI()
    response = client.responses.create(
        model=LLM_MODEL,
        input=f"{system_prompt}\n\n{question}",
        temperature=temperature,
        max_output_tokens=max_tokens,
    )
    return response.output_text


def _appeler_anthropic(question, system_prompt, temperature, max_tokens):
    """Appel via le SDK Anthropic (Claude)."""
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=LLM_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": question}]
    )
    return response.content[0].text


def _appeler_mistral(question, system_prompt, temperature, max_tokens):
    """Appel via le SDK Mistral."""
    from mistralai import Mistral
    import os

    client = Mistral(api_key=os.environ.get("MISTRAL_API_KEY", ""))
    response = client.chat.complete(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question}
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content

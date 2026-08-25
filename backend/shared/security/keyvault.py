"""
CartPilot Cloud Security & Secrets Ingestion via Azure Key Vault
Enables secret loading through Managed Identity with local .env fallback.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger("cartpilot.security")

KEYVAULT_NAME = os.getenv("AZURE_KEYVAULT_NAME") or os.getenv("KEYVAULT_NAME")

_secret_client = None

def get_secret_client():
    global _secret_client
    if _secret_client is not None:
        return _secret_client

    if not KEYVAULT_NAME:
        return None

    try:
        from azure.keyvault.secrets import SecretClient
        from azure.identity import DefaultAzureCredential

        vault_url = f"https://{KEYVAULT_NAME}.vault.azure.net"
        _secret_client = SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())
        logger.info(f"Connected to Azure Key Vault: {KEYVAULT_NAME}")
        return _secret_client
    except Exception as e:
        logger.warning(f"Could not initialize Azure Key Vault client: {e}")
        return None


def get_secret(secret_name: str, default: Optional[str] = None) -> Optional[str]:
    """
    Fetches a secret value:
    1. First checks Azure Key Vault (if KEYVAULT_NAME configured with Managed Identity).
    2. Falls back to environment variables (for local Docker and development).
    """
    client = get_secret_client()
    if client:
        try:
            # Key Vault secrets use hyphens instead of underscores (e.g. OPENAI-API-KEY)
            kv_name = secret_name.replace("_", "-")
            secret = client.get_secret(kv_name)
            if secret and secret.value:
                return secret.value
        except Exception:
            pass

    # Fallback to local environment variable
    return os.getenv(secret_name, default)

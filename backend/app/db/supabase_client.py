import os
import logging
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("pathwise")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    raise RuntimeError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is missing from your .env file.")

# Module-level singleton (service_role). Imported directly by routers as `supabase_admin`.
supabase_admin: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
logger.info("Supabase Admin Client (service_role) initialized successfully.")


def get_supabase_client() -> Client:
    """Returns the shared service_role Supabase client."""
    return supabase_admin


def get_supabase_admin() -> Client:
    """Alias for get_supabase_client()."""
    return supabase_admin
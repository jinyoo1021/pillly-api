from supabase import create_client, Client
from app.core.config import settings

# service_role key — RLS detour, only backend
supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY,
)
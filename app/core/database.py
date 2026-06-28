from supabase import create_client, Client
from app.core.config import settings

# Client using the anon key (respects RLS)
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

# Client using the service role key (bypasses RLS for backend operations)
supabase_admin: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)

def get_supabase_client() -> Client:
    return supabase

def get_supabase_admin() -> Client:
    return supabase_admin

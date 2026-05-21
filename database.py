"""database.py — routes to Supabase or local SQLite based on MODE."""
from config import settings

if settings.is_local:
    from database_local import *
    from database_local import LOCAL_USER
else:
    from database_cloud import *
import os
import sys
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client

# Add project root to sys.path to enable app imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from app.core.config import settings

def main():
    # Verify environment settings
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
        print("Error: Missing SUPABASE_URL or SUPABASE_SERVICE_KEY config values.")
        sys.exit(1)

    print("Initializing Supabase Client...")
    supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
    
    # Calculate threshold (current time - 48 hours)
    cutoff_time = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    print(f"Querying CV records created before: {cutoff_time}")

    try:
        # 1. Fetch CV records older than 48 hours
        response = (
            supabase.table("cv_records")
            .select("id, file_path")
            .lt("created_at", cutoff_time)
            .execute()
        )
        records = response.data or []
        
        if not records:
            print("No outdated CV records found.")
            return

        print(f"Found {len(records)} outdated record(s) to process.")

        file_paths = [r["file_path"] for r in records if r.get("file_path")]
        record_ids = [r["id"] for r in records]

        # 2. Remove files from Supabase Storage
        if file_paths:
            print(f"Removing {len(file_paths)} file(s) from storage bucket '{settings.SUPABASE_BUCKET}'...")
            try:
                supabase.storage.from_(settings.SUPABASE_BUCKET).remove(file_paths)
                print("Storage files successfully removed.")
            except Exception as se:
                print(f"Warning: Storage removal partially/fully failed: {str(se)}")

        # 3. Delete matching CV records from database
        print(f"Deleting database entries for {len(record_ids)} record(s)...")
        db_response = supabase.table("cv_records").delete().in_("id", record_ids).execute()
        print(f"Successfully cleaned up {len(db_response.data)} CV database entries.")

    except Exception as e:
        print(f"Fatal error during cleanup process: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()

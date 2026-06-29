import os
import sys
from datetime import datetime, timezone, timedelta

# Add root directory to sys.path to resolve app imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()

from app.core.database import get_supabase_admin
from app.core.config import settings

def cleanup_old_cvs():
    print("Starting CV cleanup process...")
    supabase = get_supabase_admin()
    bucket_name = settings.SUPABASE_BUCKET
    threshold_time = datetime.now(timezone.utc) - timedelta(hours=48)
    
    # 1. Cleanup based on Database Records (handles DB deletion and associated storage)
    print("Checking database records older than 48 hours...")
    try:
        response = supabase.table("cv_records").select("id", "file_path", "created_at").lt("created_at", threshold_time.isoformat()).execute()
        records = response.data or []
        print(f"Found {len(records)} database records older than 48 hours.")
        
        for record in records:
            file_path = record.get("file_path")
            record_id = record.get("id")
            
            # Delete file from storage first
            if file_path:
                try:
                    supabase.storage.from_(bucket_name).remove([file_path])
                    print(f"Deleted storage file associated with DB record: {file_path}")
                except Exception as e:
                    print(f"Failed to delete storage file {file_path}: {e}")
            
            # Delete record from database (cascade deletes evaluations/chats)
            try:
                supabase.table("cv_records").delete().eq("id", record_id).execute()
                print(f"Deleted database record: {record_id}")
            except Exception as e:
                print(f"Failed to delete database record {record_id}: {e}")
                
    except Exception as e:
        print(f"Error cleaning up database records: {e}")

    # 2. Cleanup orphaned files directly from Storage
    print("Checking storage files directly...")
    try:
        files = supabase.storage.from_(bucket_name).list(path="cvs")
        print(f"Listed {len(files)} files in 'cvs/' folder.")
        
        for file_item in files:
            name = file_item.get("name") or getattr(file_item, "name", None)
            created_at_str = file_item.get("created_at") or getattr(file_item, "created_at", None)
            
            if not name or name == ".emptyFolderPlaceholder":
                continue
                
            if created_at_str:
                created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                if created_at < threshold_time:
                    storage_path = f"cvs/{name}"
                    try:
                        supabase.storage.from_(bucket_name).remove([storage_path])
                        print(f"Deleted orphaned storage file: {storage_path} (created at {created_at_str})")
                    except Exception as e:
                        print(f"Failed to delete orphaned storage file {storage_path}: {e}")
                        
    except Exception as e:
        print(f"Error cleaning up storage files: {e}")

    print("Cleanup process finished.")

if __name__ == "__main__":
    cleanup_old_cvs()

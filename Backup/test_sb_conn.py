import os
import requests
from dotenv import load_dotenv

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def test_supabase():
    print(f"Testing Supabase at: {SUPABASE_URL}")
    print(f"Key starts with: {SUPABASE_KEY[:10]}...")
    
    # Try a simple GET on reportes_hq
    url = f"{SUPABASE_URL}/rest/v1/reportes_hq?limit=1"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    
    try:
        r = requests.get(url, headers=headers, timeout=10)
        print(f"Status Code: {r.status_code}")
        print(f"Response: {r.text[:200]}")
        if r.status_code == 200:
            print("✅ Supabase connection SUCCESSFUL")
        else:
            print("❌ Supabase connection FAILED")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_supabase()

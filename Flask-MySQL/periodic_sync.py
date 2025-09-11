#!/usr/bin/env python3
"""
Periodic sync script for DocuSign envelopes.
Can be run via cron job or Windows Task Scheduler.
"""
import requests
import sys
import os
import json
from datetime import datetime
from dotenv import load_dotenv

def run_sync(base_url="http://localhost:5000", timeout=300):
    """Run envelope sync and return results."""
    try:
        print(f"[{datetime.now()}] Starting envelope sync...")
        
        # Make sync request (incremental sync by default)
        response = requests.post(
            f"{base_url}/sync/envelopes",
            json={},  # Empty payload = incremental sync
            timeout=timeout
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"[{datetime.now()}] Sync completed successfully:")
            print(f"  - Status: {data.get('status')}")
            print(f"  - Synced: {data.get('synced_count', 0)} envelopes")
            print(f"  - Message: {data.get('message')}")
            return True
        else:
            error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {"error": response.text}
            print(f"[{datetime.now()}] Sync failed with status {response.status_code}:")
            print(f"  - Error: {error_data.get('error', 'Unknown error')}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"[{datetime.now()}] Error: Cannot connect to Flask server at {base_url}")
        print("Make sure the Flask application is running.")
        return False
    except requests.exceptions.Timeout:
        print(f"[{datetime.now()}] Error: Sync request timed out after {timeout}s")
        return False
    except Exception as e:
        print(f"[{datetime.now()}] Unexpected error: {e}")
        return False

def get_sync_status(base_url="http://localhost:5000"):
    """Get current sync status."""
    try:
        response = requests.get(f"{base_url}/sync/status", timeout=30)
        if response.status_code == 200:
            data = response.json()
            last_sync = data.get("last_sync")
            if last_sync:
                print(f"[{datetime.now()}] Last sync status:")
                print(f"  - Date: {last_sync.get('date')}")
                print(f"  - Status: {last_sync.get('status')}")
                print(f"  - Envelopes: {last_sync.get('envelopes_synced', 0)}")
                if last_sync.get('error_message'):
                    print(f"  - Error: {last_sync.get('error_message')}")
            else:
                print(f"[{datetime.now()}] No previous sync found.")
            return True
        else:
            print(f"[{datetime.now()}] Failed to get sync status: {response.status_code}")
            return False
    except Exception as e:
        print(f"[{datetime.now()}] Error getting sync status: {e}")
        return False

def main():
    """Main function."""
    load_dotenv()
    
    # Get configuration from environment or command line
    base_url = os.getenv("FLASK_BASE_URL", "http://localhost:5000")
    
    # Parse command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == "status":
            success = get_sync_status(base_url)
            sys.exit(0 if success else 1)
        elif sys.argv[1] == "--help":
            print("Usage:")
            print("  python periodic_sync.py        # Run incremental sync")
            print("  python periodic_sync.py status # Show sync status")
            print("  python periodic_sync.py --help # Show this help")
            print()
            print("Environment variables:")
            print("  FLASK_BASE_URL: Base URL for Flask app (default: http://localhost:5000)")
            sys.exit(0)
    
    # Run sync
    success = run_sync(base_url)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
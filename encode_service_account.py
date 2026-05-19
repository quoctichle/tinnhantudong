#!/usr/bin/env python3
"""
Script to encode service account JSON to base64 for Render deployment.
Run this locally to get the base64 string to paste into Render environment variable.
"""

import base64
import json
import sys
import os

def encode_service_account():
    # Try to find the service account file
    default_file = "dondoi-492808-e0f43cf58b1e.json"
    
    if not os.path.exists(default_file):
        print(f"Error: {default_file} not found in current directory")
        print("Please run this script from the project root directory")
        sys.exit(1)
    
    # Read and validate JSON
    try:
        with open(default_file, 'r') as f:
            json_content = f.read()
            # Validate it's valid JSON
            json.loads(json_content)
    except Exception as e:
        print(f"Error reading {default_file}: {e}")
        sys.exit(1)
    
    # Encode to base64
    b64_encoded = base64.b64encode(json_content.encode('utf-8')).decode('utf-8')
    
    print("=" * 80)
    print("SERVICE ACCOUNT BASE64 STRING FOR RENDER")
    print("=" * 80)
    print("\nCopy this entire string below:\n")
    print(b64_encoded)
    print("\n" + "=" * 80)
    print("NEXT STEPS:")
    print("=" * 80)
    print("1. Go to https://dashboard.render.com")
    print("2. Open your 'tinnhan-api' service")
    print("3. Go to 'Environment' tab")
    print("4. Add new environment variable:")
    print("   Key: GOOGLE_SERVICE_ACCOUNT_JSON_B64")
    print("   Value: (paste the base64 string above)")
    print("5. Click 'Save Changes' and wait for redeploy")
    print("\n")

if __name__ == "__main__":
    encode_service_account()

import os
import base64
import json


BASE_DIR = os.path.dirname(__file__)


def get_env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip()


def get_service_account_file(default_filename: str = "dondoi-492808-e0f43cf58b1e.json") -> str:
    # Check if service account JSON is provided as base64 (for Render/cloud deployment)
    service_account_b64 = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_B64")
    if service_account_b64:
        # Decode base64 and save to /tmp
        try:
            json_content = base64.b64decode(service_account_b64).decode('utf-8')
            tmp_path = "/tmp/service-account.json"
            with open(tmp_path, 'w') as f:
                f.write(json_content)
            return tmp_path
        except Exception as e:
            print(f"Warning: Failed to decode GOOGLE_SERVICE_ACCOUNT_JSON_B64: {e}")
    
    # Fall back to file path
    return get_env(
        "GOOGLE_SERVICE_ACCOUNT_FILE",
        os.path.join(BASE_DIR, default_filename),
    )


def get_chrome_user_data_dir(default_folder: str = "chrome-profile") -> str:
    return get_env(
        "CHROME_USER_DATA_DIR",
        os.path.join(BASE_DIR, default_folder),
    )


def get_chrome_profile(default_profile: str = "Default") -> str:
    return get_env("CHROME_PROFILE", default_profile)

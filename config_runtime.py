import os


BASE_DIR = os.path.dirname(__file__)


def get_env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip()


def get_service_account_file(default_filename: str = "dondoi-492808-e0f43cf58b1e.json") -> str:
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

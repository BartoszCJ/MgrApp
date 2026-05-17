"""Ladowanie zmiennych srodowiskowych z .env przez pydantic-settings.

Co to robi:
- czyta plik .env i zmienne srodowiskowe systemu,
- waliduje ze wszystkie wymagane klucze sa ustawione,
- udostepnia je jako obiekt `settings` w calej aplikacji.

UWAGA: `.env` szukamy po absolute path (backend root), zeby dzialalo niezaleznie
od tego skad odpalisz aplikacje:
  - `cd backend && uv run forensics serve` (cwd = backend)
  - `npm run dev` z root MagisterkaApp (cwd = MagisterkaApp/)
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/src/forensics/config.py -> backend/
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_PATH = _BACKEND_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_PATH,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # API keys
    etherscan_api_key: str = Field(default="", description="Klucz Etherscan API")
    arkham_api_key: str = Field(default="", description="Klucz Arkham API")
    alchemy_api_key: str = Field(default="", description="Klucz Alchemy API")
    alchemy_rpc_url: str = Field(default="", description="Pelny URL RPC z kluczem Alchemy")

    # Backend
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000

    # CORS
    frontend_url: str = "http://localhost:3000"


settings = Settings()

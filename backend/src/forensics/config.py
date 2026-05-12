"""Ladowanie zmiennych srodowiskowych z .env przez pydantic-settings.

Co to robi:
- czyta plik .env i zmienne srodowiskowe systemu,
- waliduje ze wszystkie wymagane klucze sa ustawione,
- udostepnia je jako obiekt `settings` w calej aplikacji.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
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

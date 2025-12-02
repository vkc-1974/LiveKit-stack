#!/usr/bin/env python3

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # LiveKit credentials and endpoint
    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str

    # Ollama service URL
    ollama_url: str = "http://ollama:11434"

    # MariaDB connection settings
    db_host: str = "mariadb"
    db_port: int = 3306
    db_user: str
    db_pass: str
    db_name: str

    # Computed properties for convenience
    @property
    def database_url(self) -> str:
        """Returns full SQLAlchemy-compatible database URL"""
        return f"mariadb+pymysql://{self.db_user}:{self.db_pass}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def livekit_wss_url(self) -> str:
        """Returns secure WebSocket URL (wss://) for production use"""
        return self.livekit_url.replace("ws://", "wss://", 1)

    model_config = SettingsConfigDict(
        env_file=".env",           # Automatically loads .env from project root
        env_file_encoding="utf-8",
        case_sensitive=False,      # Allows lowercase/uppercase in env vars
        extra="ignore",            # Ignores undefined environment variables
    )


# Singleton instance — import and use anywhere in the project
settings = Settings()

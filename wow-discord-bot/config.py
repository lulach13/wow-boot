from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    discord_token: str
    blizzard_client_id: str
    blizzard_client_secret: str
    blizzard_region: str = "us"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    db_path: str = "./wow_bot.db"
    patch_check_interval_minutes: int = 30

    # Guild the slash commands sync to, and the channel used for the
    # /check_registered roster dump. Set these in .env for your own server.
    discord_guild_id: int = 0
    discord_patch_channel_id: int = 0


settings = Settings()

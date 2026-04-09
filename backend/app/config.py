from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Codebase Onboarding Agent"
    debug: bool = False
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/onboarding_agent"
    openai_api_key: str = ""
    temporal_host: str = "localhost:7233"

    class Config:
        env_file = ".env"


settings = Settings()

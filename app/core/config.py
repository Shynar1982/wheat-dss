from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url_async: str
    database_url_sync: str

    class Config:
        env_file = ".env"

settings = Settings()

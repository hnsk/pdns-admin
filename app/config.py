from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "POWERADMIN_"}

    pdns_api_url: str = "http://localhost:8081"
    pdns_api_key: str = "changeme"
    pdns_server_id: str = "localhost"

    database_path: str = "/data/poweradmin.db"
    secret_key: str = "change-this-to-a-random-secret"
    session_lifetime_hours: int = 8
    default_admin_password: str = "admin"


settings = Settings()

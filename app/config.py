import logging

from pydantic import model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

_DEFAULT_SECRET = "change-this-to-a-random-secret"


class Settings(BaseSettings):
    model_config = {"env_prefix": "POWERADMIN_"}

    database_path: str = "/data/poweradmin.db"
    secret_key: str = _DEFAULT_SECRET
    session_lifetime_hours: int = 8
    default_admin_password: str = "admin"

    @model_validator(mode="after")
    def check_secrets(self) -> "Settings":
        if self.secret_key == _DEFAULT_SECRET:
            raise ValueError(
                "POWERADMIN_SECRET_KEY is not set. "
                "Set it to a random secret before starting the application."
            )
        if self.default_admin_password == "admin":
            logger.warning(
                "POWERADMIN_DEFAULT_ADMIN_PASSWORD is still 'admin'. "
                "Change it after first login."
            )
        return self


settings = Settings()

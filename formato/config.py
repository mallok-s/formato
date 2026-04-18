from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

CONFIG_PATH = Path.home() / ".config" / "formato" / "config.toml"


class Config(BaseSettings):
    model_config = SettingsConfigDict(toml_file=str(CONFIG_PATH))

    github_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("github_token", "GITHUB_TOKEN"),
    )
    poll_interval: float = 0.1
    slack_poll_interval: float = 0.25

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, env_settings, TomlConfigSettingsSource(settings_cls))

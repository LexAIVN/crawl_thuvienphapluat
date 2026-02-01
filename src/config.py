"""Configuration management for the law document crawler."""

from pathlib import Path
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class CrawlerConfig(BaseSettings):
    """Configuration settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CRAWLER_",
        case_sensitive=False,
    )

    # Authentication
    username: str
    password: SecretStr

    # URLs
    base_url: str = "https://thuvienphapluat.vn"
    login_url: str = "https://thuvienphapluat.vn/page/login.aspx"

    # Directories
    download_dir: Path = Path("data")
    auth_state_path: Path = Path(".auth/state.json")
    progress_file: Path = Path("progress.json")
    log_dir: Path = Path("logs")

    # Crawler settings
    max_concurrent: int = 3
    retry_attempts: int = 3
    retry_base_delay: float = 2.0
    request_delay_min: float = 1.0
    request_delay_max: float = 3.0
    page_timeout: int = 30000  # milliseconds

    # Browser settings
    headless: bool = True
    slow_mo: int = 0  # milliseconds between actions

    def ensure_directories(self) -> None:
        """Create required directories if they don't exist."""
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.auth_state_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)


class LuatVietnamConfig(BaseSettings):
    """Configuration for luatvietnam.vn crawler."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="LUATVIETNAM_",
        case_sensitive=False,
        extra="ignore",
    )

    # Authentication
    user: str
    password: SecretStr

    # URLs
    base_url: str = "https://luatvietnam.vn"
    login_url: str = "https://luatvietnam.vn"
    search_url: str = (
        "https://luatvietnam.vn/tim-van-ban.html"
        "?Keywords="
        "&SearchByDate=IssueDate"
        "&DateFrom="
        "&DateTo="
        "&lDocTypeId=11"
        "&OrganId=0"
        "&lEffectStatusId=4"
        "&LanguageId=0"
        "&SignerId=0"
    )

    # Directories
    download_dir: Path = Path("data/nghidinh")
    auth_state_path: Path = Path(".auth/luatvietnam_state.json")
    progress_file: Path = Path("progress_nghidinh.json")
    log_dir: Path = Path("logs")

    # Crawler settings
    max_concurrent: int = 3
    retry_attempts: int = 3
    retry_base_delay: float = 2.0
    request_delay_min: float = 1.5
    request_delay_max: float = 4.0
    page_timeout: int = 30000  # milliseconds

    # Scraping settings (pagination)
    scrape_delay_min: float = 1.0
    scrape_delay_max: float = 2.5

    # Browser settings
    headless: bool = True
    slow_mo: int = 0  # milliseconds between actions

    def ensure_directories(self) -> None:
        """Create required directories if they don't exist."""
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.auth_state_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

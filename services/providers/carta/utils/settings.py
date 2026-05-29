import os
from enum import Enum
from pydantic_settings import BaseSettings

class CartaRuntimeMode(str, Enum):
    DISCOVERY = "discovery"
    RUNTIME = "runtime"

class CartaSettings(BaseSettings):
    mode: CartaRuntimeMode = CartaRuntimeMode.DISCOVERY
    
    # Environment/URL settings
    login_base_url: str = "https://login.playground.carta.team"
    app_base_url: str = "https://app.playground.carta.team"
    api_base_url: str = "https://app.playground.carta.team/api"
    
    # Discovery mode settings
    enable_har: bool = False
    har_path: str = "output/carta/network.har"
    enable_network_discovery: bool = True
    max_capture_bytes: int = 500_000

    class Config:
        env_prefix = "CARTA_"
        env_file = ".env"
        extra = "ignore"

settings = CartaSettings()

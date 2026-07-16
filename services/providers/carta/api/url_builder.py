from ..utils.settings import settings

class URLBuilder:
    APP_BASE_URL = settings.app_base_url
    API_BASE_URL = settings.app_base_url

    @classmethod
    def build_api_url(cls, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        clean_path = path.lstrip('/')
        return f"{cls.API_BASE_URL}/{clean_path}"


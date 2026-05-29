class URLBuilder:
    APP_BASE_URL = "https://app.playground.carta.team"
    API_BASE_URL = "https://app.playground.carta.team"

    @classmethod
    def build_api_url(cls, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        clean_path = path.lstrip('/')
        return f"{cls.API_BASE_URL}/{clean_path}"

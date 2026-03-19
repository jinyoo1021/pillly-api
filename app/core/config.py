from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # app base
    APP_ENV: str = "development"
    API_URL: str = "http://localhost:8000"
    SECRET_KEY: str

    # Supabase
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str

    # Redis
    UPSTASH_REDIS_URL: str = "redis://localhost:6379"
    UPSTASH_REDIS_TOKEN: str = "local"

    # QStash
    QSTASH_TOKEN: str = "local-dummy"
    QSTASH_CURRENT_SIGNING_KEY: str = "local-dummy"
    QSTASH_NEXT_SIGNING_KEY: str = "local-dummy"

    # Firebase FCM
    FIREBASE_PROJECT_ID: str = "pillly-app"
    FIREBASE_CREDENTIALS_PATH: str = "./secrets/firebase-adminsdk.json"

    # APNs
    APNS_KEY_ID: str = "local-dummy"
    APNS_TEAM_ID: str = "local-dummy"
    APNS_PRIVATE_KEY_PATH: str = "./secrets/apns-key.p8"
    APNS_BUNDLE_ID: str = "com.pillly.app"

    # Sentry
    SENTRY_DSN: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
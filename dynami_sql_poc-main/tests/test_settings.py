from app.settings import Settings

def test_settings_load(mock_env):
    settings = Settings()
    assert settings.API_URL == "http://api"
    assert settings.API_PORT == "8080"
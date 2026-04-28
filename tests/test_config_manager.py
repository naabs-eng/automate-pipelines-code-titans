import pytest
from src.config.config_manager import ConfigManager


def test_config_loads():
    config = ConfigManager()
    assert config.get("spark.app_name") == "SalesDataPipeline"
    assert config.get("spark.master") == "local[*]"


def test_config_paths():
    config = ConfigManager()
    assert config.get("paths.bronze") is not None
    assert config.get("paths.silver") is not None
    assert config.get("paths.gold") is not None


def test_config_tables():
    config = ConfigManager()
    tables = config.get("tables.source")
    assert isinstance(tables, list)
    assert len(tables) == 4


def test_config_missing_key_returns_default():
    config = ConfigManager()
    assert config.get("nonexistent.key", "default") == "default"

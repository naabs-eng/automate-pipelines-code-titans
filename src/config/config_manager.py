from pathlib import Path

import yaml


class ConfigManager:
    def __init__(self, config_path="config.yaml"):
        self.config_path = Path(config_path)
        self.config = self._load_config()

    def _load_config(self):
        with open(self.config_path, "r") as f:
            return yaml.safe_load(f)

    def get(self, key, default=None):
        keys = key.split(".")
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default

    def get_sql_server_connection_string(self):
        sql_config = self.config["sql_server"]
        return (
            f"Driver={{{sql_config['driver']}}};Server={sql_config['server']};"
            f"Database={sql_config['database']};Trusted_Connection={sql_config['trusted_connection']}"
        )

import os
from utils.jsonc import load_jsonc
from utils.logger import log

class Config:
    def __init__(self):
        self._data = {}
        self.load()

    def load(self):
        try:
            config_path = os.path.join(os.getcwd(), 'config.json')
            self._data = load_jsonc(config_path)
            log.info("Config loaded successfully.")
        except Exception as e:
            log.error(f"Failed to load config.json: {e}")
            self._data = {}

    @property
    def premium_guild_ids(self):
        ids = self._data.get("premium_guild_ids", [])
        # Fallback to old guild_id if present for backward compatibility
        if not ids and "guild_id" in self._data:
            ids = [self._data["guild_id"]]
        return [int(gid) for gid in ids]

    @property
    def master_guild_ids(self):
        ids = self._data.get("master_guild_ids", [])
        # Fallback to old guild_id if present
        if not ids and "guild_id" in self._data:
            ids = [self._data["guild_id"]]
        return [int(gid) for gid in ids]

    @property
    def language(self):
        return self._data.get("language", "en")

    @property
    def command_suffix(self):
        return self._data.get("command_suffix", "")

    @property
    def command_prefix(self):
        return self._data.get("command_prefix", "!")

    @property
    def version(self):
        return self._data.get("globals", {}).get("version", "v2.1.0")

    @property
    def wizard_timeout(self):
        return self._data.get("globals", {}).get("wizard_timeout", 600)

    def get(self, key, default=None):
        return self._data.get(key, default)

# Global instances
config = Config()

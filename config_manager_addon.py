import os
import json

class ConfigManager:
    """
    Simple JSON-based persistent config for the S3 UI.
    Stores:
      - profile
      - region
      - bucket
      - prefix
      - local_path
      - transfer_mode
      - window geometry
    """

    def __init__(self):
        self.config_path = os.path.join(os.path.expanduser("~"), ".mc_s3_config.json")
        self.data = {
            "profile": "",
            "region": "",
            "bucket": "",
            "prefix": "",
            "local_path": "",
            "transfer_mode": "",
            "geometry": "",
            "sso_start_url":"",
            "sso_region":""
        }
        self.load()

    def load(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    self.data.update(json.load(f))
            except Exception:
                pass

    def save(self):
        try:
            with open(self.config_path, "w") as f:
                json.dump(self.data, f, indent=2)
        except Exception:
            pass

    # Convenience accessors
    def get(self, key, default=""):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()

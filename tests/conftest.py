import os
import tempfile

# Point config + cache at a throwaway dir before any backend module is imported.
_tmp = tempfile.mkdtemp(prefix="mtg-brewmaster-test-")
os.environ["CONFIG_PATH"] = os.path.join(_tmp, "settings.yaml")
os.environ["CACHE_DIR"] = os.path.join(_tmp, "cache")

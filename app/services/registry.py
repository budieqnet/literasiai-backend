import json
import os
import sys
from app.utils.logging import get_logger
from app.services.handlers import HANDLER_MAP

log = get_logger("registry")


def _get_config_path():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = os.path.dirname(sys.executable)
        external = os.path.join(base, "config", "setting_sumber.json")
        if os.path.exists(external):
            return external
        return os.path.join(sys._MEIPASS, "config", "setting_sumber.json")
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "config", "setting_sumber.json"
    )


CONFIG_PATH = _get_config_path()

CUSTOM_HANDLER_MAP = {}


def _import_custom_handler(handler_id):
    if handler_id in CUSTOM_HANDLER_MAP:
        return CUSTOM_HANDLER_MAP[handler_id]

    mapping = {
        "custom_arxiv": "app.services.arxiv",
        "custom_pubmed": "app.services.pubmed",
        "custom_garuda": "app.services.garuda",
        "custom_sinta": "app.services.sinta",
        "custom_openaccess": "app.services.openaccess",
    }

    module_path = mapping.get(handler_id)
    if not module_path:
        return None

    try:
        import importlib
        mod = importlib.import_module(module_path)
        handler_obj = type("DynamicHandler", (), {"search": staticmethod(mod.search)})
        CUSTOM_HANDLER_MAP[handler_id] = handler_obj
        return handler_obj
    except Exception as e:
        log.error(f"Failed to load custom handler '{handler_id}': {e}")
        return None


class SourceRegistry:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._config = self._load_config()
        self._source_map = {}
        self._source_infos = {}
        self._groups = {}
        self._build_registry()

    def _load_config(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.error(f"Failed to load setting_sumber.json: {e}")
            return {"sources": [], "content_groups": {}, "global": {}}

    def _build_registry(self):
        sources = self._config.get("sources", [])
        self._source_map = {}
        self._source_infos = {}

        for src in sources:
            sid = src.get("id")
            if not sid:
                continue
            if not src.get("enabled", True):
                continue

            handler_type = src.get("handler", "")
            handler_cls = HANDLER_MAP.get(handler_type)

            if handler_cls:
                instance = handler_cls(src)
                self._source_map[sid] = instance.search
            else:
                handler_obj = _import_custom_handler(handler_type)
                if handler_obj:
                    self._source_map[sid] = handler_obj.search
                else:
                    log.warning(f"No handler found for source '{sid}' (handler={handler_type})")
                    continue

            self._source_infos[sid] = {
                "id": sid,
                "name": src.get("name", sid),
                "description": src.get("description", ""),
                "type": src.get("type", "journal"),
                "language": src.get("language", "multi"),
                "api_available": src.get("api_available", True),
                "enabled": src.get("enabled", True),
                "handler": handler_type,
            }

        self._groups = self._config.get("content_groups", {})

    @property
    def SOURCE_MAP(self):
        return dict(self._source_map)

    @property
    def source_ids(self):
        return list(self._source_map.keys())

    def get_group(self, group_name):
        group = self._groups.get(group_name, [])
        return [s for s in group if s in self._source_map]

    @property
    def JOURNAL_SOURCES(self):
        return self.get_group("journal")

    @property
    def BOOK_SOURCES(self):
        return self.get_group("book")

    @property
    def ALL_SOURCES(self):
        return self.get_group("all") or self.source_ids

    def get_source_info(self, source_id):
        return self._source_infos.get(source_id)

    def list_source_infos(self):
        return [info for info in self._source_infos.values()]

    def get_source_config(self, source_id):
        for src in self._config.get("sources", []):
            if src.get("id") == source_id:
                return src
        return None

    def reload(self):
        self._config = self._load_config()
        self._build_registry()

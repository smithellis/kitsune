from django.apps import AppConfig
import sys
import importlib
import types
from django.conf import settings


class SearchConfig(AppConfig):
    name = "kitsune.search"
    default_auto_field = "django.db.models.AutoField"

    def ready(self):
        # Set up compatibility layer before any other imports
        ES_VERSION = getattr(settings, "ES_VERSION", 7)

        # Main module and submodules to handle
        modules_to_proxy = [
            "elasticsearch",
            "elasticsearch.exceptions",
            "elasticsearch.helpers",
            "elasticsearch.client",
        ]

        # Source module prefix based on version
        source_prefix = "elasticsearch8" if ES_VERSION == 8 else "elasticsearch7"

        # Create dynamic proxy modules
        for module_name in modules_to_proxy:
            # Get the source module path
            source_name = module_name.replace("elasticsearch", source_prefix)

            try:
                # Import the source module
                source_module = importlib.import_module(source_name)

                # Create or get the module
                if module_name not in sys.modules:
                    sys.modules[module_name] = types.ModuleType(module_name)

                # Create a proxy module that dynamically gets attributes from the source
                proxy_module = sys.modules[module_name]

                # Define __getattr__ function for dynamic attribute lookup
                def make_getattr(src):
                    def __getattr__(name):
                        return getattr(src, name)

                    return __getattr__

                # Set the __getattr__ function to dynamically look up attributes from source
                proxy_module.__getattr__ = make_getattr(source_module)

                # Copy all existing attributes
                for attr in dir(source_module):
                    if not attr.startswith("__"):  # Skip special attributes
                        setattr(proxy_module, attr, getattr(source_module, attr))

            except ImportError:
                # Log the error but continue - some submodules might not exist
                print(f"Warning: Could not import {source_name}")
                continue

        # Additional special handling for elasticsearch_dsl
        # In ES7, we use elasticsearch_dsl (standalone package)
        # In ES8, we use elasticsearch8.dsl (part of elasticsearch8)
        try:
            if ES_VERSION == 8:
                # For ES8, proxy elasticsearch8.dsl as elasticsearch_dsl
                source_module = importlib.import_module("elasticsearch8.dsl")
            else:
                # For ES7, use the standalone elasticsearch_dsl package
                source_module = importlib.import_module("elasticsearch_dsl")

            # Create or get the module
            if "elasticsearch_dsl" not in sys.modules:
                sys.modules["elasticsearch_dsl"] = types.ModuleType("elasticsearch_dsl")

            # Create a proxy module that dynamically gets attributes from the source
            proxy_module = sys.modules["elasticsearch_dsl"]

            # Set the __getattr__ function to dynamically look up attributes from source
            proxy_module.__getattr__ = make_getattr(source_module)

            # Copy all existing attributes
            for attr in dir(source_module):
                if not attr.startswith("__"):  # Skip special attributes
                    setattr(proxy_module, attr, getattr(source_module, attr))

            # Also handle submodules of elasticsearch_dsl
            if ES_VERSION == 8:
                # Try to map common submodules
                for submodule_name in [
                    "connections",
                    "analysis",
                    "field",
                    "faceted_search",
                    "wrappers",
                ]:
                    try:
                        source_submodule = importlib.import_module(
                            f"elasticsearch8.dsl.{submodule_name}"
                        )
                        target_module_name = f"elasticsearch_dsl.{submodule_name}"

                        if target_module_name not in sys.modules:
                            sys.modules[target_module_name] = types.ModuleType(target_module_name)

                        proxy_submodule = sys.modules[target_module_name]
                        proxy_submodule.__getattr__ = make_getattr(source_submodule)

                        for attr in dir(source_submodule):
                            if not attr.startswith("__"):
                                setattr(proxy_submodule, attr, getattr(source_submodule, attr))
                    except ImportError:
                        # Skip submodules that don't exist
                        continue

        except ImportError:
            print("Warning: Could not set up elasticsearch_dsl proxy")

        # Now import signals - this happens after the compatibility layer is set up
        from kitsune.search import signals  # noqa

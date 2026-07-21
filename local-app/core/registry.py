import importlib
import pkgutil
import logging
from typing import Dict, Any, Type
from fastapi import FastAPI
from interfaces.module_base import BaseModule

logger = logging.getLogger(__name__)

class PluginRegistry:
    def __init__(self):
        self.modules: Dict[str, BaseModule] = {}

    def discover_and_load_modules(self, app: FastAPI, package_name: str = "modules", disabled_modules: list = None):
        if disabled_modules is None:
            disabled_modules = []

        logger.info(f"Scanning for modules in package: {package_name}")
        
        try:
            package = importlib.import_module(package_name)
        except ImportError as e:
            logger.error(f"Failed to import modules package '{package_name}': {e}")
            return

        for _, module_name, is_pkg in pkgutil.iter_modules(package.__path__):
            if not is_pkg or module_name in disabled_modules:
                continue
                
            full_module_name = f"{package_name}.{module_name}"
            try:
                module = importlib.import_module(full_module_name)
                # Look for a class inheriting from BaseModule
                for item_name in dir(module):
                    item = getattr(module, item_name)
                    if isinstance(item, type) and issubclass(item, BaseModule) and item is not BaseModule:
                        module_instance = item()
                        self.modules[module_name] = module_instance
                        logger.info(f"Loading module: {module_name}")
                        module_instance.setup(app)
                        break
                else:
                    logger.warning(f"No valid BaseModule implementation found in {full_module_name}")
            except Exception as e:
                logger.error(f"Error loading module {module_name}: {e}")

registry = PluginRegistry()

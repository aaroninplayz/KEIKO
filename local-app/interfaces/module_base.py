from abc import ABC, abstractmethod
from fastapi import FastAPI

class BaseModule(ABC):
    """
    Abstract base class that all pluggable modules must implement.
    """
    
    @abstractmethod
    def setup(self, app: FastAPI) -> None:
        """
        Called by the Plugin Registry during application startup.
        Modules should register their routes, background tasks, or database models here.
        """
        pass

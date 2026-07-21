from fastapi import FastAPI
from interfaces.module_base import BaseModule
from core.database import Base, engine
from .router import router
from . import models_db

class AuthModule(BaseModule):
    def setup(self, app: FastAPI) -> None:
        # Automatically create tables in SQLite on application setup
        Base.metadata.create_all(bind=engine)
        
        # Register the router with prefix /api/v1
        app.include_router(router, prefix="/api/v1", tags=["Auth Module"])

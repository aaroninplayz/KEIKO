from fastapi import FastAPI
from interfaces.module_base import BaseModule
from core.database import Base, engine
from .router import router
from . import models_db

class InterviewModule(BaseModule):
    def setup(self, app: FastAPI) -> None:
        # Automatically create tables in SQLite on application plugin loading setup
        Base.metadata.create_all(bind=engine)

        app.include_router(router, prefix="/api/v1/interview", tags=["Interview Module"])
        # WebSockets typically don't have tags in the same way, but prefix applies.

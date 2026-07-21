from fastapi import FastAPI
from interfaces.module_base import BaseModule
from .router import router

class ExampleModule(BaseModule):
    def setup(self, app: FastAPI) -> None:
        app.include_router(router, prefix="/api/v1/example", tags=["Example Module"])

from fastapi import APIRouter

router = APIRouter()

@router.get("/")
def get_example_data():
    return {"message": "Hello from the example module! Architecture is pluggable."}

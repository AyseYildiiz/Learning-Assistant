from fastapi import FastAPI

app = FastAPI(title="Learning Assistant")


@app.get("/health")
def health() -> dict[str, str]:
    return {"message": "Hello, world"}

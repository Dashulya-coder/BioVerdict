from fastapi import FastAPI

app = FastAPI(title="BioVerdict")


@app.get("/health")
def health():
    return {"status": "ok"}

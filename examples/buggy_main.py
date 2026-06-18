"""Intentionally buggy FastAPI app for demoing ui-ux-doctor.

Run:  python3 scripts/scan.py examples/buggy_main.py
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Bug: wildcard origins + credentials -> browser blocks all authed requests,
# the React UI silently fails to load data.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

EXTERNAL_API = "http://localhost:9000/v1"  # Bug: hardcoded host


@app.get("/api/products")
async def products():
    print("fetching products")  # Bug: print in request handler
    return [{"id": 1, "name": "Widget"}]

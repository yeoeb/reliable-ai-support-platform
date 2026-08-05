# Reliable AI Support Operations Platform

An enterprise internal customer service and IT support AI platform focused on reliability, security, evaluation, auditability, and human approval workflows.

## Current Stage

Sprint 0 — Project Bootstrap

## Local Development

Create and activate a virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1

Install development dependencies:
python -m pip install -r requirements\dev.txt

Start the FastAPI application:
python -m uvicorn app.main:app --reload

Open API documentation:
http://127.0.0.1:8000/docs

Testing

Run the automated tests:
python -m pytest -v
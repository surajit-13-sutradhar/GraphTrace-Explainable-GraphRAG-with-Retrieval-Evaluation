# GraphTrace

Explainable GraphRAG over fictional SaaS architecture documentation, with a
measured comparison against baseline vector RAG.

> Work in progress. Full documentation arrives in the final milestone.

## Setup (Windows PowerShell)

    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    Copy-Item .env.example .env   # then add your GEMINI_API_KEY
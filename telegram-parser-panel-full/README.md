# Telegram Parser Panel (Railway-ready)

## Overview
FastAPI + Telethon panel to authorize Telegram accounts, parse members from public groups, save to DB and export CSV.

## Quick start (local)
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app.main:app --reload

## Deploy on Railway
1. Push repository to GitHub.
2. Create new project on Railway -> Deploy from GitHub.
3. Ensure Procfile and requirements.txt are in repo root.
4. Add PostgreSQL plugin in Railway to populate DATABASE_URL.
5. Deploy.

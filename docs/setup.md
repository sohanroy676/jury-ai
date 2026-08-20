# Supabase Setup Guide

This guide walks you through getting the free-tier Supabase credentials you need to run JuryAI locally, and where each value goes.

## 1. Create a Supabase project (free)

1. Go to <https://supabase.com> and sign up / log in.
2. Click **New project**.
3. Choose an organization, a project name (e.g. `jury-ai`), and a **Database Password** — save this somewhere safe; you'll need it for `SUPABASE_DB_PASSWORD`.
4. Pick a region close to you and click **Create new project**.
5. Wait for the project to provision (a minute or two).

## 2. Get your API keys

1. In your project dashboard, go to **Project Settings → API** (or the **Connect** tab).
2. You'll find three values you need:

| `.env` variable | Where to find it | Notes |
|---|---|---|
| `SUPABASE_URL` | **Project URL** (e.g. `https://abcdefghijklm.supabase.co`) | |
| `SUPABASE_ANON_KEY` | **anon public** key | Safe for the frontend/browser |
| `SUPABASE_SERVICE_ROLE_KEY` | **service_role** key | **Server-side only.** Never expose to the frontend. Bypasses RLS. |

## 3. Create the `submissions` table

1. In the dashboard, go to **SQL Editor**.
2. Open `infra/migrations/0001_create_submissions.sql` from this repo and paste its contents.
3. Click **Run**. You should see the `submissions` table created under **Table Editor**.

## 4. Create the Storage bucket

1. In the dashboard, go to **Storage → New bucket**.
2. Name it `submissions` (must match `SUPABASE_STORAGE_BUCKET` in `.env`).
3. Set it to **Public** so uploaded files get a public URL (the backend returns this URL to the frontend).

## 5. Fill in `.env`

1. Copy `.env.example` to `.env`:
   ```
   cp .env.example .env
   ```
2. Fill in the values from step 2, plus:
   - `SUPABASE_DB_PASSWORD` — the database password you set in step 1.
   - `SUPABASE_STORAGE_BUCKET=submissions` — already set by default.

> **Security:** `.env` is git-ignored. Never commit it. The `service_role` key in particular must never appear in frontend code or be committed.

## 6. Run the backend

```bash
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload
```

The API will be available at <http://localhost:8000> (docs at `/docs`).

## 7. Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000> and try uploading a PDF or PPTX.
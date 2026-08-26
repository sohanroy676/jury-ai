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

## 3. Run the database migrations

Apply each migration file from `infra/migrations/` **in filename order**:

1. In the dashboard, go to **SQL Editor**.
2. For each of the following files, paste its contents into the editor and click **Run**:
   - `0001_create_submissions.sql` — creates the `submissions` table
   - `0002_create_parsed_submissions.sql` — creates the `parsed_submissions` table
   - `0003_create_scores.sql` — creates the `scores` table
   - `0004_create_image_cache.sql` — creates the `image_cache` table *(v0.3.5)*
   - `0005_add_image_descriptions.sql` — adds the `image_descriptions` column to `parsed_submissions` *(v0.3.5)*
   - `0006_create_rubric_config.sql` — creates the `rubric_config` table + default equal weights *(v0.6.0)*
   - `0007_create_feedback.sql` — creates the `feedback` table *(v0.7.0)*
   - `0008_allow_resubmission.sql` — adds `superseded_at` for re-submission history *(v1.1.0)*
   - `0009_add_team_email.sql` — adds the `team_email` column for notifications *(v1.2.0)*
3. After all migrations you should see the tables under **Table Editor**: `submissions`, `parsed_submissions`, `scores`, `image_cache`, `rubric_config`, `feedback`.


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
   - `GROQ_API_KEY` — required for scoring and image descriptions (free key at console.groq.com).

   The image-understanding variables (`GROQ_VISION_MODEL`, `CLIP_MODEL`, `CLIP_PRETRAINED`, `IMAGE_CLASSIFY_THRESHOLD`, `PHASH_HAMMING_THRESHOLD`, `MIN_IMAGE_DIMENSION`) have sensible defaults — see `.env.example` if you want to override them.

3. **(Optional) Gemini for image descriptions** *(v0.3.6)*: by default images are described with Groq's qwen model. To use Google's Gemini instead:
   1. Create a free API key at <https://aistudio.google.com/apikey> (no credit card needed).
   2. In `.env`, set:
      ```
      VISION_PROVIDER=gemini
      GEMINI_API_KEY=your-key-here
      ```
      Optionally override the model via `GEMINI_VISION_MODEL` (default `gemini-3.6-flash`; note that `gemini-2.5-flash` returns 404 on newly created API keys).
   3. Restart the backend.

   Scoring and all text stages always use Groq regardless of this setting; leaving `VISION_PROVIDER=groq` (the default) keeps behavior identical to v0.3.5.

4. **(Optional but recommended) Notification emails** *(v1.2.0)*: teams get a confirmation email right after a successful upload and a results-with-feedback email when their feedback is generated. The portal collects each team's contact email at upload time (stored in `submissions.team_email`, migration 0009).

   **Gmail SMTP (default transport):**
   1. Enable 2-Step Verification on your Google account.
   2. Create an App Password at <https://myaccount.google.com/apppasswords>.
   3. In `.env` set:
      ```
      EMAIL_PROVIDER=smtp
      EMAIL_FROM=yourgmail@gmail.com
      SMTP_USER=yourgmail@gmail.com
      SMTP_PASSWORD=<16-char App Password>
      ```

   **Resend (alternative):**
   1. Create a free API key at <https://resend.com> (no credit card needed).
   2. In `.env` set:
      ```
      EMAIL_PROVIDER=resend
      EMAIL_FROM=onboarding@resend.dev
      RESEND_API_KEY=your-key-here
      ```
      Caveat: without a verified custom domain, Resend only delivers to your own account email — fine for development, not for a real event.

   Leaving every credential blank disables notifications gracefully — uploads and feedback generation never fail because of mail problems; outcomes are logged and reported in the API responses. Restart the backend after changing any of these.

> **Security:** `.env` is git-ignored. Never commit it. The `service_role` key in particular must never appear in frontend code or be committed.

## 6. Run the backend

```bash
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload
```

The API will be available at <http://localhost:8000> (docs at `/docs`).

> **First-run note (image understanding, v0.3.5):** the local CLIP classifier downloads ~350 MB of model weights on first use and caches them locally — the first upload containing images will take a few extra minutes. Subsequent runs are fast. On Windows, `pip install torch` installs the CPU-only build by default; no GPU is needed.

## 7. Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000> and try uploading a PDF or PPTX.
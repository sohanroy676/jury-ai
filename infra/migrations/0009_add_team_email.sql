-- ============================================================
-- 0009_add_team_email.sql
-- v1.2.0 — Notifications: store the team's contact email so the
-- backend can send a submission confirmation and a results-with-
-- feedback email. Nullable: rows that predate this migration have
-- no address and simply never receive notifications (uploads and
-- scoring are unaffected).
--
-- Apply in Supabase SQL Editor (Dashboard -> SQL Editor).
-- ============================================================

alter table public.submissions
    add column if not exists team_email text;

-- Defense-in-depth alongside the route/form validation: reject values
-- that clearly aren't an email. NULL stays allowed. Wrapped in a DO
-- block because Postgres has no ADD CONSTRAINT IF NOT EXISTS.
do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'submissions_team_email_format'
    ) then
        alter table public.submissions
            add constraint submissions_team_email_format
            check (
                team_email is null
                or team_email ~* '^[^@\s]+@[^@\s]+\.[^@\s]+$'
            );
    end if;
end $$;
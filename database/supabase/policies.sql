-- LEADFORGE — optional Supabase-only hardening.
--
-- Apply in the Supabase SQL editor AFTER `alembic upgrade head`. Not part of the
-- Alembic chain because the `auth` schema and `auth.uid()` exist only on Supabase.
--
-- Default posture (set by migration 0001): RLS is ENABLED on every table with NO
-- policies, so the anon/authenticated roles cannot read or write anything through
-- the Supabase Data API. All application access goes through the FastAPI backend,
-- which connects as the table owner and enforces organization membership itself.
--
-- The read-only policies below are only needed if you later choose to query
-- tables directly from the browser with the Supabase client. They never grant
-- write access; writes stay behind the API.

begin;

-- 1. Tie profiles to Supabase Auth users (cascade on account deletion).
alter table public.profiles
    drop constraint if exists fk_profiles_id_auth_users,
    add constraint fk_profiles_id_auth_users
        foreign key (id) references auth.users (id) on delete cascade;

-- 2. Membership helper. SECURITY DEFINER avoids recursive RLS evaluation on
--    organization_members; search_path is pinned to prevent hijacking.
create or replace function public.leadforge_is_member(org uuid)
returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
    select exists (
        select 1
        from public.organization_members m
        where m.organization_id = org
          and m.profile_id = auth.uid()
    );
$$;

revoke all on function public.leadforge_is_member(uuid) from public;
grant execute on function public.leadforge_is_member(uuid) to authenticated;

-- 3. Read policies.
drop policy if exists profiles_select_self on public.profiles;
create policy profiles_select_self on public.profiles
    for select to authenticated using (id = auth.uid());

drop policy if exists organizations_select_member on public.organizations;
create policy organizations_select_member on public.organizations
    for select to authenticated using (public.leadforge_is_member(id));

drop policy if exists organization_members_select_member on public.organization_members;
create policy organization_members_select_member on public.organization_members
    for select to authenticated using (public.leadforge_is_member(organization_id));

do $$
declare
    t text;
begin
    foreach t in array array[
        'businesses', 'contacts', 'website_audits', 'audit_findings', 'lead_scores',
        'jobs', 'campaigns', 'email_drafts', 'suppressions', 'activities'
    ]
    loop
        execute format('drop policy if exists %I on public.%I', t || '_select_member', t);
        execute format(
            'create policy %I on public.%I for select to authenticated '
            'using (public.leadforge_is_member(organization_id))',
            t || '_select_member', t
        );
    end loop;
end;
$$;

-- audit_logs intentionally has no client policy: it is readable only by the backend.

commit;

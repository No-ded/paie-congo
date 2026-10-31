-- Migration : absences, retards et retenues
-- À exécuter une seule fois dans Supabase > SQL Editor (nouvelle requête).

-- Paramètres de retenue propres à chaque entreprise
alter table entreprises
  add column if not exists diviseur_jours numeric(4,1) not null default 26,
  add column if not exists heures_mensuelles numeric(6,2) not null default 173.33;

-- Absences et retards
create table if not exists absences (
  id uuid primary key default gen_random_uuid(),
  entreprise_id uuid not null references entreprises(id) on delete cascade,
  employe_id uuid not null references employes(id) on delete cascade,
  date_absence date not null,
  type text not null check (type in (
    'injustifiee', 'retard', 'autorisee_non_payee', 'autorisee_payee', 'maladie', 'autre')),
  unite text not null default 'jours' check (unite in ('jours', 'heures')),
  duree numeric(5,2) not null check (duree > 0),
  taux_maintien numeric(5,2) not null default 0 check (taux_maintien between 0 and 100),
  motif text,
  created_at timestamptz not null default now()
);

create index if not exists absences_employe_date on absences (employe_id, date_absence);

alter table absences enable row level security;
create policy "isolation_absences" on absences for all
  using (entreprise_id in (select mes_entreprises()))
  with check (entreprise_id in (select mes_entreprises()));

-- Schéma PostgreSQL (compatible Supabase) - SaaS RH & paie Congo
-- Montants en XAF (entiers). Multi-entreprises : chaque ligne métier porte entreprise_id
-- et la sécurité par ligne (RLS) isole les données de chaque client.

create extension if not exists "pgcrypto";

-- 1. Entreprises clientes
create table entreprises (
  id uuid primary key default gen_random_uuid(),
  nom text not null,
  nif text,                 -- numéro d'identification fiscale
  numero_cnss text,
  ville text default 'Brazzaville',
  created_at timestamptz not null default now()
);

-- 2. Utilisateurs rattachés à une entreprise (auth.users = table Supabase)
create table membres (
  user_id uuid not null references auth.users(id) on delete cascade,
  entreprise_id uuid not null references entreprises(id) on delete cascade,
  role text not null check (role in ('admin', 'rh', 'lecture')),
  primary key (user_id, entreprise_id)
);

-- 3. Employés
create table employes (
  id uuid primary key default gen_random_uuid(),
  entreprise_id uuid not null references entreprises(id) on delete cascade,
  matricule text not null,
  nom text not null,
  prenom text not null,
  date_naissance date,
  numero_cnss text,
  situation_familiale text,
  parts numeric(3,1) not null default 1,   -- quotient familial
  telephone_mobile_money text,             -- pour le paiement des salaires plus tard
  actif boolean not null default true,
  created_at timestamptz not null default now(),
  unique (entreprise_id, matricule)
);

-- 4. Contrats
create table contrats (
  id uuid primary key default gen_random_uuid(),
  entreprise_id uuid not null references entreprises(id) on delete cascade,
  employe_id uuid not null references employes(id) on delete cascade,
  type text not null check (type in ('CDI', 'CDD', 'stage', 'journalier')),
  poste text not null,
  date_debut date not null,
  date_fin date,
  salaire_base numeric(14,0) not null check (salaire_base >= 0),
  primes jsonb not null default '{}'::jsonb,   -- ex: {"transport": 25000}
  created_at timestamptz not null default now()
);

-- 5. Paramètres de paie versionnés (taux, plafonds, barème) - communs à tous
create table parametres_paie (
  id uuid primary key default gen_random_uuid(),
  date_effet date not null unique,
  valeurs jsonb not null,        -- même contenu que ParametresPaie en Python
  source text,                   -- ex: "Loi de finances 2026, validé par expert-comptable"
  valide boolean not null default false,   -- n'utiliser en production que si true
  created_at timestamptz not null default now()
);

-- 6. Bulletins de paie (un par employé et par mois)
create table bulletins (
  id uuid primary key default gen_random_uuid(),
  entreprise_id uuid not null references entreprises(id) on delete cascade,
  employe_id uuid not null references employes(id) on delete cascade,
  periode date not null,                         -- 1er jour du mois
  parametres_id uuid not null references parametres_paie(id),
  brut numeric(14,0) not null,
  retraite_salarie numeric(14,0) not null,
  camu_salarie numeric(14,0) not null,
  impot numeric(14,0) not null,
  net_a_payer numeric(14,0) not null,
  charges_employeur numeric(14,0) not null,
  detail jsonb,                                  -- copie complète du calcul (audit)
  statut text not null default 'brouillon' check (statut in ('brouillon', 'valide', 'paye')),
  created_at timestamptz not null default now(),
  unique (employe_id, periode)
);

-- 7. Congés et absences
create table conges (
  id uuid primary key default gen_random_uuid(),
  entreprise_id uuid not null references entreprises(id) on delete cascade,
  employe_id uuid not null references employes(id) on delete cascade,
  type text not null check (type in ('annuel', 'maladie', 'maternite', 'sans_solde', 'autre')),
  date_debut date not null,
  date_fin date not null check (date_fin >= date_debut),
  statut text not null default 'demande' check (statut in ('demande', 'accepte', 'refuse')),
  created_at timestamptz not null default now()
);

-- Index utiles
create index on employes (entreprise_id);
create index on contrats (employe_id);
create index on bulletins (entreprise_id, periode);
create index on conges (employe_id, date_debut);

-- ========== Sécurité par ligne (RLS) ==========
create or replace function mes_entreprises() returns setof uuid
language sql stable security definer set search_path = public as $$
  select entreprise_id from membres where user_id = auth.uid()
$$;

do $$
declare t text;
begin
  foreach t in array array['employes', 'contrats', 'bulletins', 'conges'] loop
    execute format('alter table %I enable row level security', t);
    execute format(
      'create policy "isolation_%1$s" on %1$I for all
       using (entreprise_id in (select mes_entreprises()))
       with check (entreprise_id in (select mes_entreprises()))', t);
  end loop;
end $$;

alter table entreprises enable row level security;
create policy "voir_mes_entreprises" on entreprises for select
  using (id in (select mes_entreprises()));

alter table membres enable row level security;
create policy "voir_mes_memberships" on membres for select
  using (user_id = auth.uid());

alter table parametres_paie enable row level security;
create policy "lecture_parametres_valides" on parametres_paie for select
  using (valide = true);

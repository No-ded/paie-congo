-- Migration : suivi des congés
-- À exécuter une seule fois dans Supabase > SQL Editor (nouvelle requête).

-- Taux d'acquisition par entreprise (1,25 jour par mois = 15 jours par an)
alter table entreprises
  add column if not exists conge_jours_par_mois numeric(4,2) not null default 1.25;

-- Solde de congés reporté à l'arrivée dans l'application
alter table employes
  add column if not exists solde_initial_conges numeric(5,1) not null default 0;

-- Nombre de jours décomptés pour chaque demande, et commentaire
alter table conges
  add column if not exists nb_jours numeric(4,1),
  add column if not exists commentaire text;

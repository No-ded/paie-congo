# Paie Congo - MVP

## Installation

1. **Supabase** : crée un projet gratuit, ouvre l'éditeur SQL, colle et exécute `schema.sql`.
2. **Utilisateur** : Authentication > Users > Add user (ton email + mot de passe).
3. **Clés** : Project Settings > API : copie l'URL du projet et la clé `anon`.
4. **Ton entreprise** (SQL Editor, remplace l'email) :

```sql
with e as (
  insert into entreprises (nom) values ('Mon entreprise test') returning id
)
insert into membres (user_id, entreprise_id, role)
select u.id, e.id, 'admin' from e, auth.users u where u.email = 'ton@email.com';
```

5. **Paramètres de paie** (à `valide = false` tant qu'un expert-comptable n'a pas confirmé les règles) :

```sql
insert into parametres_paie (date_effet, source, valide, valeurs) values (
  '2026-01-01', 'A VALIDER - exemple fictif', false,
  '{"plafond_retraite":1200000,"plafond_famille_at":600000,
    "retraite_salarie":0.04,"camu_salarie":0.005,
    "retraite_employeur":0.08,"allocations_familiales":0.1003,
    "accident_travail":0.0225,"tus_employeur":0.075,
    "abattement_impot":0.20,
    "bareme":[[900000,0.01],[2000000,0.10],[4000000,0.25],[8000000,0.40],[null,0.45]]}'
);
```

Quand les taux et le barème sont confirmés : modifie `valeurs`, puis
`update parametres_paie set valide = true where date_effet = '2026-01-01';`
Tant qu'aucun jeu n'est validé, l'application reste en mode démo (enregistrement bloqué).

6. **Secrets locaux** : crée `.streamlit/secrets.toml` :

```toml
SUPABASE_URL = "https://xxxx.supabase.co"
SUPABASE_KEY = "ta_cle_anon"
```

7. **Lancer** :

```bash
pip install -r requirements.txt
streamlit run app.py
```

Ne publie jamais le fichier `secrets.toml` ni la clé `service_role`.

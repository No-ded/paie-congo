"""Application Paie Congo (MVP) - Streamlit + Supabase."""
from dataclasses import fields
from datetime import date

import requests
import streamlit as st
from supabase import create_client

from paie_congo import ParametresPaie, calculer_bulletin

st.set_page_config(page_title="Paie Congo", page_icon="🧾", layout="centered")


def fmt(x) -> str:
    return f"{int(x):,}".replace(",", " ") + " XAF"


# ---------- Connexion ----------
def get_client():
    # Un client par utilisateur (session_state), jamais partagé entre visiteurs.
    if "sb" not in st.session_state:
        st.session_state.sb = create_client(
            st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"]
        )
    return st.session_state.sb


def page_connexion():
    st.title("🧾 Paie Congo")
    st.caption("Gestion RH et paie pour PME")
    email = st.text_input("Email")
    mdp = st.text_input("Mot de passe", type="password")
    if st.button("Se connecter", type="primary"):
        try:
            # Appel direct à l'API d'authentification de Supabase
            url = st.secrets["SUPABASE_URL"].strip().rstrip("/")
            cle = st.secrets["SUPABASE_KEY"].strip()
            r = requests.post(
                f"{url}/auth/v1/token?grant_type=password",
                headers={"apikey": cle, "Content-Type": "application/json"},
                json={"email": email.strip(), "password": mdp},
                timeout=20,
            )
            data = r.json()
            if r.status_code != 200:
                raise Exception(data.get("msg") or data.get("error_description") or data)
            get_client().postgrest.auth(data["access_token"])
            st.session_state.connecte = True
            st.rerun()
        except Exception as err:
            st.error(f"Connexion impossible : {err}")


def entreprise_courante(sb):
    if "entreprise_id" not in st.session_state:
        r = sb.table("membres").select("entreprise_id, role").execute().data
        if not r:
            return None
        st.session_state.entreprise_id = r[0]["entreprise_id"]
        st.session_state.role = r[0]["role"]
    return st.session_state.entreprise_id


# ---------- Paramètres de paie ----------
def charger_parametres(sb, periode: date):
    """Dernier jeu de paramètres VALIDÉ en vigueur à la période donnée."""
    r = (
        sb.table("parametres_paie").select("*")
        .eq("valide", True).lte("date_effet", periode.isoformat())
        .order("date_effet", desc=True).limit(1).execute().data
    )
    if not r:
        return None, None
    row = r[0]
    noms = {f.name for f in fields(ParametresPaie)} - {"date_effet"}
    v = {k: val for k, val in row["valeurs"].items() if k in noms}
    if "bareme" in v:
        v["bareme"] = tuple((pl, taux) for pl, taux in v["bareme"])
    return ParametresPaie(date_effet=date.fromisoformat(row["date_effet"]), **v), row["id"]


# ---------- Pages ----------
def page_employes(sb, eid):
    st.header("Employés")
    employes = sb.table("employes").select("*").eq("entreprise_id", eid).order("nom").execute().data
    if employes:
        st.dataframe(
            [{"Matricule": e["matricule"], "Nom": e["nom"], "Prénom": e["prenom"],
              "Parts": e["parts"], "Actif": e["actif"]} for e in employes],
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("Aucun employé pour l'instant.")

    st.subheader("Ajouter un employé")
    with st.form("nouvel_employe", clear_on_submit=True):
        c1, c2 = st.columns(2)
        matricule = c1.text_input("Matricule")
        numero_cnss = c2.text_input("N° CNSS")
        nom = c1.text_input("Nom")
        prenom = c2.text_input("Prénom")
        parts = c1.number_input("Nombre de parts", min_value=1.0, max_value=6.0, value=1.0, step=0.5)
        type_contrat = c2.selectbox("Contrat", ["CDI", "CDD", "stage", "journalier"])
        poste = c1.text_input("Poste")
        debut = c2.date_input("Début du contrat", value=date.today())
        salaire = st.number_input("Salaire de base mensuel (XAF)", min_value=0, step=5000)
        ok = st.form_submit_button("Enregistrer", type="primary")
    if ok:
        if not (matricule and nom and prenom and poste and salaire > 0):
            st.error("Remplis matricule, nom, prénom, poste et salaire.")
            return
        try:
            e = sb.table("employes").insert({
                "entreprise_id": eid, "matricule": matricule, "nom": nom,
                "prenom": prenom, "numero_cnss": numero_cnss or None, "parts": parts,
            }).execute().data[0]
            sb.table("contrats").insert({
                "entreprise_id": eid, "employe_id": e["id"], "type": type_contrat,
                "poste": poste, "date_debut": debut.isoformat(), "salaire_base": salaire,
            }).execute()
            st.success(f"{prenom} {nom} ajouté.")
            st.rerun()
        except Exception as err:
            st.error(f"Erreur : {err}")


def page_bulletin(sb, eid):
    st.header("Générer un bulletin")
    employes = sb.table("employes").select("*").eq("entreprise_id", eid).eq("actif", True).order("nom").execute().data
    if not employes:
        st.info("Ajoute d'abord un employé.")
        return
    choix = {f"{e['prenom']} {e['nom']} ({e['matricule']})": e for e in employes}
    e = choix[st.selectbox("Employé", list(choix))]
    mois = st.date_input("Mois de paie", value=date.today().replace(day=1)).replace(day=1)

    contrat = (
        sb.table("contrats").select("*").eq("employe_id", e["id"])
        .order("date_debut", desc=True).limit(1).execute().data
    )
    if not contrat:
        st.warning("Cet employé n'a pas de contrat.")
        return
    c = contrat[0]
    primes_contrat = sum(float(v) for v in (c["primes"] or {}).values())
    extra = st.number_input("Primes exceptionnelles du mois (XAF)", min_value=0, step=5000)
    brut = float(c["salaire_base"]) + primes_contrat + extra
    st.caption(f"Brut : {fmt(brut)} (base {fmt(c['salaire_base'])} + primes)")

    params, params_id = charger_parametres(sb, mois)
    mode_demo = params is None
    if mode_demo:
        st.warning(
            "Aucun jeu de paramètres validé pour cette période. "
            "Résultat en MODE DÉMO (barème fictif) : enregistrement bloqué."
        )
        params = ParametresPaie(date_effet=mois)

    b = calculer_bulletin(brut, float(e["parts"]), params)
    st.subheader("Résultat")
    c1, c2 = st.columns(2)
    c1.metric("Net à payer", fmt(b["net_a_payer"]))
    c2.metric("Coût total employeur", fmt(b["cout_total_employeur"]))
    st.write(
        f"- Retraite salarié : {fmt(b['retraite_salarie'])}\n"
        f"- CAMU salarié : {fmt(b['camu_salarie'])}\n"
        f"- Impôt sur salaire : {fmt(b['impot'])}\n"
        f"- Charges employeur : {fmt(b['charges_employeur'])}"
    )

    if st.button("Enregistrer le bulletin", type="primary", disabled=mode_demo):
        try:
            sb.table("bulletins").upsert({
                "entreprise_id": eid, "employe_id": e["id"], "periode": mois.isoformat(),
                "parametres_id": params_id, "brut": b["brut"],
                "retraite_salarie": b["retraite_salarie"], "camu_salarie": b["camu_salarie"],
                "impot": b["impot"], "net_a_payer": b["net_a_payer"],
                "charges_employeur": b["charges_employeur"], "detail": b,
                "statut": "brouillon",
            }, on_conflict="employe_id,periode").execute()
            st.success("Bulletin enregistré (brouillon).")
        except Exception as err:
            st.error(f"Erreur : {err}")


def page_historique(sb, eid):
    st.header("Historique des bulletins")
    r = (
        sb.table("bulletins").select("*, employes(nom, prenom)")
        .eq("entreprise_id", eid).order("periode", desc=True).execute().data
    )
    if not r:
        st.info("Aucun bulletin enregistré.")
        return
    st.dataframe(
        [{"Période": x["periode"][:7],
          "Employé": f"{x['employes']['prenom']} {x['employes']['nom']}",
          "Brut": x["brut"], "Net": x["net_a_payer"],
          "Charges employeur": x["charges_employeur"], "Statut": x["statut"]} for x in r],
        use_container_width=True, hide_index=True,
    )


# ---------- Main ----------
def main():
    if not st.session_state.get("connecte"):
        page_connexion()
        return
    sb = get_client()
    eid = entreprise_courante(sb)
    if not eid:
        st.error("Ton compte n'est rattaché à aucune entreprise. Vois le README (étape 4).")
        return
    page = st.sidebar.radio("Menu", ["Employés", "Bulletin", "Historique"])
    if st.sidebar.button("Se déconnecter"):
        st.session_state.clear()
        st.rerun()
    {"Employés": page_employes, "Bulletin": page_bulletin, "Historique": page_historique}[page](sb, eid)


main()

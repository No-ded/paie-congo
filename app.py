"""Application Paie Congo (MVP) - Streamlit + Supabase."""
from dataclasses import fields
from datetime import date

import requests
import streamlit as st
from supabase import create_client

from absences import (DIVISEUR_JOURS, HEURES_MENSUELLES, TYPES, jours_sur_mois,
                      total_retenues)
from conges import (SEMAINE_OUVRABLE, SEMAINE_OUVREE, jours_acquis,
                    jours_decomptes, solde_conges)
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

    # --- Absences, retards et congés sans solde du mois ---
    diviseur, heures_mens = DIVISEUR_JOURS, HEURES_MENSUELLES
    try:
        ent = sb.table("entreprises").select("diviseur_jours, heures_mensuelles").eq("id", eid).execute().data
        if ent:
            diviseur, heures_mens = float(ent[0]["diviseur_jours"]), float(ent[0]["heures_mensuelles"])
    except Exception:
        st.caption("Paramètres de retenue par défaut (migration des absences non exécutée).")

    fin_mois = date(mois.year + (mois.month == 12), mois.month % 12 + 1, 1)
    lignes, details = [], []
    try:
        for a in (sb.table("absences").select("*").eq("employe_id", e["id"])
                  .gte("date_absence", mois.isoformat()).lt("date_absence", fin_mois.isoformat())
                  .execute().data):
            lignes.append({"duree": a["duree"], "unite": a["unite"], "taux_maintien": a["taux_maintien"]})
            details.append(f"{TYPES.get(a['type'], (a['type'],))[0]} du {a['date_absence']} : "
                           f"{float(a['duree']):g} {a['unite']} (maintien {float(a['taux_maintien']):g} %)")
        for cs in (sb.table("conges").select("*").eq("employe_id", e["id"])
                   .eq("type", "sans_solde").eq("statut", "accepte")
                   .lte("date_debut", fin_mois.isoformat()).gte("date_fin", mois.isoformat())
                   .execute().data):
            nbj = jours_sur_mois(date.fromisoformat(cs["date_debut"]), date.fromisoformat(cs["date_fin"]),
                                 mois.year, mois.month)
            if nbj:
                lignes.append({"duree": nbj, "unite": "jours", "taux_maintien": 0})
                details.append(f"Congé sans solde ({cs['date_debut']} → {cs['date_fin']}) : {nbj} jours dans le mois")
    except Exception:
        st.caption("Absences non prises en compte (migration des absences non exécutée).")

    retenue = total_retenues(brut, lignes, diviseur, heures_mens)
    brut_paye = brut - retenue
    if retenue:
        st.warning(f"Retenue pour absences et retards : {fmt(retenue)}")
        for d in details:
            st.caption("• " + d)

    b = calculer_bulletin(brut_paye, float(e["parts"]), params)
    b["brut_contractuel"] = round(brut)
    b["retenue_absences"] = retenue
    st.subheader("Résultat")
    c1, c2 = st.columns(2)
    c1.metric("Net à payer", fmt(b["net_a_payer"]))
    c2.metric("Coût total employeur", fmt(b["cout_total_employeur"]))
    st.write(
        f"- Brut contractuel : {fmt(b['brut_contractuel'])}\n"
        f"- Retenue absences et retards : {fmt(b['retenue_absences'])}\n"
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


def page_conges(sb, eid):
    st.header("Congés")
    if "flash" in st.session_state:
        niveau, texte = st.session_state.pop("flash")
        getattr(st, niveau)(texte)

    employes = sb.table("employes").select("*").eq("entreprise_id", eid).eq("actif", True).order("nom").execute().data
    if not employes:
        st.info("Ajoute d'abord un employé.")
        return
    choix = {f"{x['prenom']} {x['nom']} ({x['matricule']})": x for x in employes}
    e = choix[st.selectbox("Employé", list(choix), key="conge_employe")]

    # Taux d'acquisition de l'entreprise (1,25 j/mois par défaut)
    taux = 1.25
    try:
        ent = sb.table("entreprises").select("conge_jours_par_mois").eq("id", eid).execute().data
        if ent:
            taux = float(ent[0]["conge_jours_par_mois"])
    except Exception:
        st.warning("Migration des congés non exécutée : taux par défaut de 1,25 j/mois utilisé.")

    contrat = sb.table("contrats").select("date_debut").eq("employe_id", e["id"]).order("date_debut").limit(1).execute().data
    acquis = jours_acquis(date.fromisoformat(contrat[0]["date_debut"]), date.today(), taux) if contrat else 0.0
    if not contrat:
        st.warning("Cet employé n'a pas de contrat : aucun jour acquis.")

    conges = sb.table("conges").select("*").eq("employe_id", e["id"]).order("date_debut", desc=True).execute().data
    annuels = [c for c in conges if c["type"] == "annuel"]
    pris = sum(float(c["nb_jours"] or 0) for c in annuels if c["statut"] == "accepte")
    attente = sum(float(c["nb_jours"] or 0) for c in annuels if c["statut"] == "demande")
    try:
        initial = float(e.get("solde_initial_conges") or 0)
    except (TypeError, ValueError):
        initial = 0.0
    solde = solde_conges(acquis, pris, initial)

    c1, c2, c3 = st.columns(3)
    c1.metric("Acquis", f"{acquis + initial:g} j")
    c2.metric("Pris", f"{pris:g} j")
    c3.metric("Solde", f"{solde:g} j")
    if attente:
        st.caption(f"{attente:g} j en attente de validation.")

    st.subheader("Nouvelle demande")
    with st.form("demande_conge", clear_on_submit=True):
        type_conge = st.selectbox("Type", ["annuel", "maladie", "maternite", "sans_solde", "autre"])
        d1, d2 = st.columns(2)
        debut = d1.date_input("Du", value=date.today())
        fin = d2.date_input("Au", value=date.today())
        samedi = st.checkbox("Compter le samedi comme jour ouvrable", value=True)
        commentaire = st.text_input("Commentaire (facultatif)")
        ok = st.form_submit_button("Envoyer la demande", type="primary")
    if ok:
        if fin < debut:
            st.error("La date de fin est avant la date de début.")
        else:
            nb = jours_decomptes(debut, fin, SEMAINE_OUVRABLE if samedi else SEMAINE_OUVREE)
            if nb == 0:
                st.error("Cette période ne contient aucun jour à décompter.")
            else:
                try:
                    sb.table("conges").insert({
                        "entreprise_id": eid, "employe_id": e["id"], "type": type_conge,
                        "date_debut": debut.isoformat(), "date_fin": fin.isoformat(),
                        "nb_jours": nb, "commentaire": commentaire or None,
                    }).execute()
                    if type_conge == "annuel" and nb > solde:
                        st.session_state.flash = ("warning", f"Demande envoyée ({nb} j), mais elle dépasse le solde de {solde:g} j.")
                    else:
                        st.session_state.flash = ("success", f"Demande envoyée ({nb} j décomptés).")
                    st.rerun()
                except Exception as err:
                    st.error(f"Erreur : {err}")

    st.subheader("Historique")
    if not conges:
        st.info("Aucune demande pour cet employé.")
    peut_valider = st.session_state.get("role") in ("admin", "rh")
    for c in conges:
        with st.container(border=True):
            st.write(f"**{c['type']}** · {c['date_debut']} → {c['date_fin']} · "
                     f"{float(c['nb_jours'] or 0):g} j · *{c['statut']}*")
            if c.get("commentaire"):
                st.caption(c["commentaire"])
            if peut_valider and c["statut"] == "demande":
                b1, b2 = st.columns(2)
                for bouton, valeur, libelle in ((b1, "accepte", "Accepter"), (b2, "refuse", "Refuser")):
                    if bouton.button(libelle, key=f"{valeur}_{c['id']}"):
                        sb.table("conges").update({"statut": valeur}).eq("id", c["id"]).execute()
                        st.rerun()


def page_absences(sb, eid):
    st.header("Absences et retards")
    if "flash" in st.session_state:
        niveau, texte = st.session_state.pop("flash")
        getattr(st, niveau)(texte)

    employes = sb.table("employes").select("*").eq("entreprise_id", eid).eq("actif", True).order("nom").execute().data
    if not employes:
        st.info("Ajoute d'abord un employé.")
        return
    choix = {f"{x['prenom']} {x['nom']} ({x['matricule']})": x for x in employes}
    e = choix[st.selectbox("Employé", list(choix), key="abs_employe")]

    st.subheader("Enregistrer une absence ou un retard")
    code = st.selectbox("Type", list(TYPES), format_func=lambda k: TYPES[k][0], key="abs_type")
    _, unite_def, maintien_def = TYPES[code]
    with st.form(f"abs_{code}", clear_on_submit=True):
        c1, c2 = st.columns(2)
        jour = c1.date_input("Date", value=date.today())
        unite = c2.selectbox("Unité", ["jours", "heures"], index=0 if unite_def == "jours" else 1)
        duree = c1.number_input("Durée", min_value=0.25, value=1.0, step=0.25)
        maintien = c2.number_input("% du salaire maintenu", min_value=0.0, max_value=100.0,
                                   value=float(maintien_def), step=5.0)
        motif = st.text_input("Motif (facultatif)")
        ok = st.form_submit_button("Enregistrer", type="primary")
    if ok:
        try:
            sb.table("absences").insert({
                "entreprise_id": eid, "employe_id": e["id"], "date_absence": jour.isoformat(),
                "type": code, "unite": unite, "duree": duree, "taux_maintien": maintien,
                "motif": motif or None,
            }).execute()
            st.session_state.flash = ("success", "Absence enregistrée.")
            st.rerun()
        except Exception as err:
            st.error(f"Erreur : {err}")

    st.subheader("Historique")
    rows = sb.table("absences").select("*").eq("employe_id", e["id"]).order("date_absence", desc=True).execute().data
    if not rows:
        st.info("Aucune absence enregistrée.")
    for a in rows:
        with st.container(border=True):
            st.write(f"**{TYPES.get(a['type'], (a['type'],))[0]}** · {a['date_absence']} · "
                     f"{float(a['duree']):g} {a['unite']} · maintien {float(a['taux_maintien']):g} %")
            if a.get("motif"):
                st.caption(a["motif"])
            if st.button("Supprimer", key=f"del_{a['id']}"):
                sb.table("absences").delete().eq("id", a["id"]).execute()
                st.rerun()


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
    page = st.sidebar.radio("Menu", ["Employés", "Congés", "Absences", "Bulletin", "Historique"])
    if st.sidebar.button("Se déconnecter"):
        st.session_state.clear()
        st.rerun()
    {"Employés": page_employes, "Congés": page_conges, "Absences": page_absences,
     "Bulletin": page_bulletin, "Historique": page_historique}[page](sb, eid)


main()

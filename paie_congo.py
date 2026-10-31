"""
Moteur de paie - Congo-Brazzaville (MVP)

IMPORTANT : tous les taux, plafonds et tranches ci-dessous sont des
PARAMETRES a faire valider par la DGI / la CNSS / un expert-comptable.
Les tranches du bareme sont des EXEMPLES FICTIFS pour tester le code.
Ne jamais coder un taux en dur dans le calcul : on change les parametres,
pas le programme.
"""
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ParametresPaie:
    date_effet: date
    # Plafonds mensuels (XAF) - a verifier
    plafond_retraite: float = 1_200_000
    plafond_famille_at: float = 600_000
    # Part salarie
    retraite_salarie: float = 0.04
    camu_salarie: float = 0.005  # base et plafond a verifier
    # Part employeur
    retraite_employeur: float = 0.08
    allocations_familiales: float = 0.1003
    accident_travail: float = 0.0225
    tus_employeur: float = 0.075  # non plafonnee
    # Impot sur salaire : 0.20 si regime ITS 2026, 0.0 si ancien IRPP (a verifier)
    abattement_impot: float = 0.20
    # Bareme annuel par part : (plafond_de_tranche, taux). None = sans limite.
    # EXEMPLE FICTIF - a remplacer par le bareme officiel.
    bareme: tuple = (
        (900_000, 0.01),
        (2_000_000, 0.10),
        (4_000_000, 0.25),
        (8_000_000, 0.40),
        (None, 0.45),
    )


def impot_progressif(base: float, bareme: tuple) -> float:
    """Applique un bareme par tranches (calcul cumulatif)."""
    impot, bas = 0.0, 0.0
    for plafond, taux in bareme:
        haut = float("inf") if plafond is None else plafond
        if base > bas:
            impot += (min(base, haut) - bas) * taux
        bas = haut
    return impot


def calculer_bulletin(brut_mensuel: float, parts: float, p: ParametresPaie) -> dict:
    """Calcule le bulletin d'un salarie pour un mois."""
    # --- Cotisations salarie ---
    retraite_sal = min(brut_mensuel, p.plafond_retraite) * p.retraite_salarie
    camu_sal = brut_mensuel * p.camu_salarie

    # --- Impot sur salaire (annualise, quotient familial) ---
    base_annuelle = (brut_mensuel - retraite_sal) * 12 * (1 - p.abattement_impot)
    par_part = base_annuelle / parts
    impot_annuel = impot_progressif(par_part, p.bareme) * parts
    impot_mensuel = impot_annuel / 12

    net = brut_mensuel - retraite_sal - camu_sal - impot_mensuel

    # --- Charges employeur ---
    ch_retraite = min(brut_mensuel, p.plafond_retraite) * p.retraite_employeur
    ch_famille = min(brut_mensuel, p.plafond_famille_at) * p.allocations_familiales
    ch_at = min(brut_mensuel, p.plafond_famille_at) * p.accident_travail
    ch_tus = brut_mensuel * p.tus_employeur
    charges = ch_retraite + ch_famille + ch_at + ch_tus

    return {
        "brut": round(brut_mensuel),
        "retraite_salarie": round(retraite_sal),
        "camu_salarie": round(camu_sal),
        "impot": round(impot_mensuel),
        "net_a_payer": round(net),
        "charges_employeur": round(charges),
        "cout_total_employeur": round(brut_mensuel + charges),
    }


# ---------------- Tests ----------------
def _tests():
    p = ParametresPaie(date_effet=date(2026, 1, 1))

    # 1. Bareme : cas simple a la main
    assert impot_progressif(1_000_000, p.bareme) == 900_000 * 0.01 + 100_000 * 0.10

    # 2. Coherence : brut - retenues = net
    b = calculer_bulletin(500_000, 1, p)
    assert abs(b["brut"] - b["retraite_salarie"] - b["camu_salarie"]
               - b["impot"] - b["net_a_payer"]) <= 1

    # 3. Plus de parts => impot plus faible ou egal
    assert calculer_bulletin(800_000, 3, p)["impot"] <= calculer_bulletin(800_000, 1, p)["impot"]

    # 4. Plafond retraite respecte
    haut = calculer_bulletin(5_000_000, 1, p)
    assert haut["retraite_salarie"] == round(p.plafond_retraite * p.retraite_salarie)

    # 5. Changer un parametre change le resultat, sans toucher au code
    p2 = ParametresPaie(date_effet=date(2027, 1, 1), tus_employeur=0.08)
    assert (calculer_bulletin(500_000, 1, p2)["charges_employeur"]
            > calculer_bulletin(500_000, 1, p)["charges_employeur"])

    print("Tous les tests passent.")


if __name__ == "__main__":
    _tests()
    p = ParametresPaie(date_effet=date(2026, 1, 1))
    for cle, val in calculer_bulletin(500_000, 1, p).items():
        print(f"{cle:>22} : {val:>12,} XAF".replace(",", " "))

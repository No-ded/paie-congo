"""
Absences, retards et retenues sur salaire - Congo-Brazzaville (MVP)

Principe : chaque absence porte un TAUX DE MAINTIEN du salaire (0 % = non payée,
100 % = entièrement payée). La retenue = valeur de l'unité x durée x (100 - maintien) %.

TOUT EST PARAMETRABLE et A VALIDER (Code du travail, convention collective,
règlement intérieur) : taux de maintien par défaut, diviseur journalier,
heures mensuelles. Les valeurs ci-dessous sont des points de départ, pas des règles.
"""
from calendar import monthrange
from datetime import date

from conges import SEMAINE_OUVRABLE, jours_decomptes

# code : (libellé, unité par défaut, taux de maintien par défaut en %)
TYPES = {
    "injustifiee": ("Absence injustifiée", "jours", 0),
    "retard": ("Retard", "heures", 0),
    "autorisee_non_payee": ("Absence autorisée non payée", "jours", 0),
    "autorisee_payee": ("Absence autorisée payée", "jours", 100),
    "maladie": ("Maladie justifiée", "jours", 100),  # à valider selon la loi / convention
    "autre": ("Autre", "jours", 100),
}

# Cohérent avec un décompte lundi-samedi (jours ouvrables). Mettre 30 si
# l'entreprise raisonne en jours calendaires. A DECIDER par entreprise.
DIVISEUR_JOURS = 26
HEURES_MENSUELLES = 173.33  # 40 h x 52 semaines / 12 mois


def valeur_unite(brut, unite, diviseur_jours=DIVISEUR_JOURS, heures_mensuelles=HEURES_MENSUELLES):
    return brut / diviseur_jours if unite == "jours" else brut / heures_mensuelles


def retenue_absence(brut, duree, unite, taux_maintien,
                    diviseur_jours=DIVISEUR_JOURS, heures_mensuelles=HEURES_MENSUELLES):
    part_retenue = max(0.0, min(100.0, 100.0 - float(taux_maintien))) / 100.0
    return valeur_unite(brut, unite, diviseur_jours, heures_mensuelles) * float(duree) * part_retenue


def total_retenues(brut, lignes, diviseur_jours=DIVISEUR_JOURS, heures_mensuelles=HEURES_MENSUELLES):
    """Somme des retenues, plafonnée au brut (jamais de salaire négatif)."""
    total = sum(
        retenue_absence(brut, l["duree"], l["unite"], l["taux_maintien"],
                        diviseur_jours, heures_mensuelles)
        for l in lignes
    )
    return round(min(total, brut))


def jours_sur_mois(debut: date, fin: date, annee: int, mois: int,
                   semaine=SEMAINE_OUVRABLE, feries=()) -> int:
    """Jours d'une période (ex. congé sans solde) qui tombent dans un mois donné."""
    m1 = date(annee, mois, 1)
    m2 = date(annee, mois, monthrange(annee, mois)[1])
    d, f = max(debut, m1), min(fin, m2)
    return 0 if f < d else jours_decomptes(d, f, semaine, feries)


# ---------------- Tests ----------------
def _tests():
    brut = 260_000
    # 1 jour non payé avec diviseur 26 => 10 000
    assert round(retenue_absence(brut, 1, "jours", 0, 26)) == 10_000
    # Même absence, diviseur 30 => 8 667
    assert round(retenue_absence(brut, 1, "jours", 0, 30)) == 8_667
    # Absence entièrement maintenue => aucune retenue
    assert retenue_absence(brut, 3, "jours", 100) == 0
    # Maintien partiel : 2 jours à 50 % => 10 000
    assert round(retenue_absence(brut, 2, "jours", 50, 26)) == 10_000
    # Retard de 2 heures
    assert abs(retenue_absence(173_330, 2, "heures", 0) - 2_000) < 1
    # Plafond : jamais plus que le brut
    assert total_retenues(100_000, [{"duree": 90, "unite": "jours", "taux_maintien": 0}], 26) == 100_000
    # Somme de plusieurs lignes
    lignes = [
        {"duree": 1, "unite": "jours", "taux_maintien": 0},
        {"duree": 2, "unite": "jours", "taux_maintien": 50},
    ]
    assert total_retenues(brut, lignes, 26) == 20_000
    # Congé à cheval sur deux mois (mer. 28 oct -> mar. 3 nov 2026, lun-sam)
    assert jours_sur_mois(date(2026, 10, 28), date(2026, 11, 3), 2026, 10) == 4
    assert jours_sur_mois(date(2026, 10, 28), date(2026, 11, 3), 2026, 11) == 2
    assert jours_sur_mois(date(2026, 10, 28), date(2026, 11, 3), 2026, 12) == 0
    print("Tous les tests d'absences passent.")


if __name__ == "__main__":
    _tests()

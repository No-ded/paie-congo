"""
Calcul des congés - Congo-Brazzaville (MVP)

Règles à valider (Code du travail, convention collective, règlement intérieur) :
- taux d'acquisition : 1,25 jour par mois complet (soit 15 jours par an),
  paramétrable par entreprise ;
- jours décomptés : par défaut lundi-samedi (jours ouvrables), paramétrable ;
- jours fériés : liste vide par défaut, à renseigner.
"""
from datetime import date, timedelta

SEMAINE_OUVRABLE = (0, 1, 2, 3, 4, 5)  # lundi-samedi
SEMAINE_OUVREE = (0, 1, 2, 3, 4)       # lundi-vendredi


def jours_decomptes(debut: date, fin: date, semaine=SEMAINE_OUVRABLE, feries=()) -> int:
    """Nombre de jours à décompter entre deux dates (incluses)."""
    if fin < debut:
        raise ValueError("La date de fin est avant la date de début.")
    n, d = 0, debut
    while d <= fin:
        if d.weekday() in semaine and d not in feries:
            n += 1
        d += timedelta(days=1)
    return n


def mois_complets(depuis: date, jusqua: date) -> int:
    """Nombre de mois complets écoulés entre deux dates."""
    if jusqua < depuis:
        return 0
    m = (jusqua.year - depuis.year) * 12 + (jusqua.month - depuis.month)
    if jusqua.day < depuis.day:
        m -= 1
    return max(m, 0)


def jours_acquis(date_embauche: date, date_calcul: date, jours_par_mois: float = 1.25) -> float:
    return round(mois_complets(date_embauche, date_calcul) * jours_par_mois, 2)


def solde_conges(acquis: float, pris: float, solde_initial: float = 0) -> float:
    return round(solde_initial + acquis - pris, 2)


# ---------------- Tests ----------------
def _tests():
    lun, dim = date(2026, 11, 2), date(2026, 11, 8)
    assert jours_decomptes(lun, dim) == 6                       # lun-sam
    assert jours_decomptes(lun, dim, SEMAINE_OUVREE) == 5       # lun-ven
    assert jours_decomptes(lun, dim, feries=(date(2026, 11, 4),)) == 5
    assert jours_decomptes(lun, lun) == 1

    assert mois_complets(date(2026, 1, 15), date(2026, 11, 14)) == 9
    assert mois_complets(date(2026, 1, 15), date(2026, 11, 15)) == 10
    assert mois_complets(date(2026, 5, 1), date(2026, 1, 1)) == 0

    assert jours_acquis(date(2025, 11, 1), date(2026, 11, 1)) == 15.0
    assert jours_acquis(date(2025, 11, 1), date(2026, 11, 1), 1.5) == 18.0

    assert solde_conges(15, 6, 2) == 11.0

    try:
        jours_decomptes(dim, lun)
        assert False
    except ValueError:
        pass
    print("Tous les tests de congés passent.")


if __name__ == "__main__":
    _tests()

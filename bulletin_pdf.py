"""Génération du bulletin de paie en PDF (A4)."""
from datetime import date
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# --- Identité visuelle : à changer ici quand le nom et les couleurs seront choisis ---
NOM_PRODUIT = "Paie Congo"
COULEUR = colors.HexColor("#1F4E5F")
COULEUR_CLAIRE = colors.HexColor("#E8F0F3")
GRIS = colors.HexColor("#555555")

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]


def _n(x) -> str:
    """Nombre entier avec espaces : 1 234 567."""
    return f"{int(x):,}".replace(",", " ")


def _pct(t) -> str:
    return f"{t * 100:.2f}".replace(".", ",") + " %"


def _date_fr(d) -> str:
    if not d:
        return "-"
    d = date.fromisoformat(str(d)) if not isinstance(d, date) else d
    return d.strftime("%d/%m/%Y")


def generer_bulletin_pdf(entreprise: dict, employe: dict, contrat: dict,
                         mois: date, b: dict, demo: bool = False) -> bytes:
    """Retourne le bulletin en PDF (octets).

    b = résultat de calculer_bulletin(), complété de 'brut_contractuel'
    et 'retenue_absences'.
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=14 * mm, bottomMargin=16 * mm,
        title=f"Bulletin de paie {MOIS[mois.month - 1]} {mois.year}",
        author=NOM_PRODUIT,
    )
    petit = ParagraphStyle("petit", fontName="Helvetica", fontSize=8.5, leading=11, textColor=GRIS)
    normal = ParagraphStyle("normal", fontName="Helvetica", fontSize=9.5, leading=12)
    nom_ent = ParagraphStyle("nom_ent", fontName="Helvetica-Bold", fontSize=14, leading=17, textColor=COULEUR)
    titre = ParagraphStyle("titre", fontName="Helvetica-Bold", fontSize=15, leading=18,
                           alignment=2, textColor=COULEUR)
    periode = ParagraphStyle("periode", fontName="Helvetica", fontSize=10.5, leading=14, alignment=2)
    section = ParagraphStyle("section", fontName="Helvetica-Bold", fontSize=9.5, leading=12,
                             textColor=COULEUR, spaceBefore=8, spaceAfter=3)

    story = []

    # ---- En-tête ----
    ligne_ent = " · ".join(x for x in (
        f"NIF : {entreprise.get('nif')}" if entreprise.get("nif") else "",
        f"N° CNSS : {entreprise.get('numero_cnss')}" if entreprise.get("numero_cnss") else "",
        entreprise.get("ville") or "",
    ) if x)
    gauche = [Paragraph(entreprise.get("nom", ""), nom_ent), Paragraph(ligne_ent, petit)]
    droite = [Paragraph("BULLETIN DE PAIE", titre),
              Paragraph(f"Période : {MOIS[mois.month - 1]} {mois.year}", periode)]
    entete = Table([[gauche, droite]], colWidths=[95 * mm, 85 * mm])
    entete.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 1.2, COULEUR),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story += [entete, Spacer(1, 8)]

    # ---- Salarié ----
    def champ(lib, val):
        return [Paragraph(f"<font color='#555555'>{lib}</font>", petit), Paragraph(str(val or "-"), normal)]

    ident = Table([
        [champ("Nom et prénom", f"{employe.get('prenom', '')} {employe.get('nom', '')}".strip()),
         champ("Matricule", employe.get("matricule")),
         champ("N° CNSS", employe.get("numero_cnss"))],
        [champ("Emploi", contrat.get("poste")),
         champ("Contrat", f"{contrat.get('type', '')} depuis le {_date_fr(contrat.get('date_debut'))}"),
         champ("Nombre de parts", f"{float(employe.get('parts') or 1):g}")],
    ], colWidths=[70 * mm, 65 * mm, 45 * mm])
    ident.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, COULEUR), ("BACKGROUND", (0, 0), (-1, -1), COULEUR_CLAIRE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story += [ident, Spacer(1, 6)]

    # ---- Tableau principal ----
    brut_contrat = b.get("brut_contractuel", b["brut"])
    retenue_abs = b.get("retenue_absences", 0)
    base = round(float(contrat.get("salaire_base") or 0))
    primes = brut_contrat - base

    rows = [["Désignation", "Base", "Taux", "Gains", "Retenues"]]
    style_extra = []

    def ajoute(libelle, base_=None, taux=None, gain=None, ret=None, gras=False, fond=None):
        i = len(rows)
        rows.append([libelle,
                     _n(base_) if base_ is not None else "",
                     _pct(taux) if taux is not None else "",
                     _n(gain) if gain is not None else "",
                     _n(ret) if ret is not None else ""])
        if gras:
            style_extra.append(("FONTNAME", (0, i), (-1, i), "Helvetica-Bold"))
        if fond:
            style_extra.append(("BACKGROUND", (0, i), (-1, i), fond))

    ajoute("Salaire de base", gain=base)
    if primes > 0:
        ajoute("Primes et indemnités", gain=primes)
    if retenue_abs:
        ajoute("Retenue absences et retards", gain=-retenue_abs)
    ajoute("SALAIRE BRUT", gain=b["brut"], gras=True, fond=COULEUR_CLAIRE)
    for l in b["lignes_salarie"]:
        ajoute(l["libelle"], l["base"], l["taux"], ret=l["montant"])
    total_ret = b["brut"] - b["net_a_payer"]
    ajoute("TOTAL DES RETENUES", ret=total_ret, gras=True, fond=COULEUR_CLAIRE)

    table = Table(rows, colWidths=[72 * mm, 28 * mm, 20 * mm, 30 * mm, 30 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"), ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("BACKGROUND", (0, 0), (-1, 0), COULEUR), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#CCCCCC")),
        ("BOX", (0, 0), (-1, -1), 0.6, COULEUR),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ] + style_extra))
    story += [table, Spacer(1, 8)]

    # ---- Net à payer ----
    net = Table([[Paragraph("NET À PAYER", ParagraphStyle("n1", fontName="Helvetica-Bold", fontSize=12,
                                                          textColor=colors.white)),
                  Paragraph(f"{_n(b['net_a_payer'])} XAF", ParagraphStyle("n2", fontName="Helvetica-Bold",
                                                                          fontSize=15, alignment=2,
                                                                          textColor=colors.white))]],
                colWidths=[90 * mm, 90 * mm])
    net.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COULEUR), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story += [net]

    # ---- Charges patronales (information) ----
    story.append(Paragraph("Charges patronales (à titre d'information)", section))
    rows2 = [["Désignation", "Base", "Taux", "Montant"]]
    for l in b["lignes_employeur"]:
        rows2.append([l["libelle"], _n(l["base"]), _pct(l["taux"]), _n(l["montant"])])
    rows2.append(["Total des charges patronales", "", "", _n(b["charges_employeur"])])
    rows2.append(["Coût total employeur (brut + charges)", "", "", _n(b["cout_total_employeur"])])
    t2 = Table(rows2, colWidths=[92 * mm, 30 * mm, 28 * mm, 30 * mm])
    t2.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"), ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), COULEUR_CLAIRE), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -2), (-1, -1), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#CCCCCC")),
        ("BOX", (0, 0), (-1, -1), 0.5, COULEUR),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t2)

    # ---- Pied de page et filigrane de démonstration ----
    def decor(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(GRIS)
        canvas.drawString(15 * mm, 9 * mm,
                          "Bulletin à conserver. Montants en francs CFA (XAF).")
        canvas.drawRightString(195 * mm, 9 * mm, f"Établi avec {NOM_PRODUIT}")
        if demo:
            canvas.setFillColor(colors.Color(0.85, 0.1, 0.1, alpha=0.18))
            canvas.setFont("Helvetica-Bold", 40)
            canvas.translate(105 * mm, 160 * mm)
            canvas.rotate(35)
            canvas.drawCentredString(0, 0, "DÉMO - NON VALABLE")
        canvas.restoreState()

    doc.build(story, onFirstPage=decor, onLaterPages=decor)
    return buf.getvalue()

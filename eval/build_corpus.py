"""Génère eval/corpus/ : documents fictifs de la famille Martin (aucune donnée réelle).

Les fichiers produits sont versionnés ; ce script ne sert qu'à les régénérer :
    .venv/bin/python eval/build_corpus.py

Le corpus contient aussi des documents « distracteurs » (dossier distracteurs/) : sans eux,
l'index ne compterait guère plus d'extraits que `top_k` et la recherche renverrait presque
tout, ce qui masquerait les erreurs de classement. Ils ne contiennent aucun élément de réponse.
"""

import sys
from email.message import EmailMessage
from pathlib import Path

from docx import Document as DocxDocument
from PIL import Image, ImageDraw, ImageFont

CORPUS = Path(__file__).parent / "corpus"


def write_pdf(path: Path, lines: list[str]) -> None:
    """PDF texte d'une page, écrit à la main (police Helvetica, encodage WinAnsi)."""
    def escape(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    content = "BT /F1 12 Tf 72 720 Td 16 TL\n" + "\n".join(f"({escape(line)}) '" for line in lines) + "\nET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    out = "%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    out += "".join(f"{offset:010d} 00000 n \n" for offset in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(out.encode("latin-1"))


# Distracteurs : (dossier, gabarit, éléments). Chaque élément donne un petit document .md.
# Aucun ne doit contenir un élément clé de eval/questions.yaml (vérifié par tests/test_eval.py).
DISTRACTORS = [
    ("courses", "Liste de courses du {0}\n\nÀ acheter : {1}.\nPenser à vérifier les dates limites avant de ranger.",
     [("samedi 3 février", "lentilles, yaourts nature, savon, café"),
      ("samedi 10 février", "riz, courgettes, lessive, jus d'orange"),
      ("samedi 17 février", "pâtes, tomates, liquide vaisselle, fromage râpé"),
      ("samedi 24 février", "carottes, poireaux, papier toilette, miel"),
      ("samedi 2 mars", "semoule, poivrons, éponges, compote"),
      ("samedi 9 mars", "haricots verts, céréales, dentifrice, thé"),
      ("samedi 23 mars", "pois chiches, concombres, sacs poubelle, biscottes"),
      ("samedi 30 mars", "oeufs de Pâques, salade, piles, confiture")]),
    ("ecole", "École primaire - {0}\n\n{1}\nLes parents sont invités à signer le cahier de liaison.",
     [("sortie piscine", "La classe de CE2 ira à la piscine municipale chaque mardi matin du mois d'avril."),
      ("kermesse", "La kermesse de fin d'année aura lieu dans la cour, avec stand de jeux et buvette."),
      ("vacances scolaires", "Les vacances de printemps commencent le samedi 13 avril au soir."),
      ("cantine", "Le menu de la semaine prochaine comprend du poisson le jeudi et des fruits chaque jour."),
      ("photo de classe", "Le photographe passera un matin de la deuxième semaine d'octobre."),
      ("conseil d'école", "Le compte rendu du dernier conseil d'école est affiché près du portail."),
      ("bibliothèque", "Chaque élève peut emprunter deux livres pour quinze jours à la bibliothèque de l'école."),
      ("rentrée", "Les fournitures demandées : un cahier grand format, une trousse complète et une ardoise.")]),
    ("jardin", "Carnet de jardin - {0}\n\n{1}\nNoter ici les observations de la saison.",
     [("rosiers", "Tailler les rosiers à la fin de l'hiver, juste avant le départ de la végétation."),
      ("potager", "Semer les radis et les petits pois dès que la terre est réchauffée."),
      ("compost", "Retourner le tas de compost deux fois par an et l'arroser en cas de sécheresse."),
      ("pelouse", "Tondre haut au printemps, puis semer les zones dégarnies avec un mélange résistant."),
      ("framboisiers", "Supprimer les cannes qui ont déjà donné des fruits et attacher les nouvelles."),
      ("haie", "Tailler la haie de lauriers après la période de nidification des oiseaux."),
      ("tomates", "Repiquer les plants en pleine terre une fois les gelées passées, avec un tuteur."),
      ("arrosage", "Arroser tôt le matin et pailler le pied des plantes pour garder l'humidité.")]),
    ("sante", "Santé - {0}\n\n{1}\nConserver le carnet de santé avec ce document.",
     [("dentiste", "Rendez-vous de contrôle chez le dentiste en début d'année pour toute la famille."),
      ("vaccins", "Le rappel de vaccin des enfants se fait chez le pédiatre, carnet de santé apporté."),
      ("optique", "Les lunettes du cadet sont à vérifier chaque année chez l'opticien du centre-ville."),
      ("pharmacie", "Vérifier le contenu de la pharmacie de la maison avant les départs en vacances."),
      ("allergies", "L'aînée est sensible aux pollens de graminées : prévoir un antihistaminique en mai."),
      ("kiné", "Les séances de rééducation du poignet sont prévues un jeudi sur deux."),
      ("médecin traitant", "Le médecin traitant reçoit sur rendez-vous, le matin uniquement."),
      ("ordonnances", "Garder les anciennes ordonnances dans la pochette bleue du bureau.")]),
    ("voyages", "Projet de voyage - {0}\n\n{1}\nÀ discuter lors du prochain repas de famille.",
     [("Bretagne", "Louer une maison près de la mer pour une semaine, avec vélos et jeux de plage."),
      ("Alpes", "Randonnées faciles autour d'un lac, hébergement en gîte, retour par le train."),
      ("Provence", "Visiter les marchés, les villages perchés et passer un après-midi au bord d'une rivière."),
      ("Alsace", "Découvrir la route des vins en voiture et goûter la tarte flambée."),
      ("Corse", "Réserver la traversée en bateau suffisamment tôt et prévoir un sac à dos par personne."),
      ("Normandie", "Promenade sur les plages du débarquement et visite des falaises d'Étretat."),
      ("Pyrénées", "Séjour en montagne avec baignade dans un lac et balade à dos d'âne pour les petits."),
      ("Vendée", "Camping en bord de mer avec location de vélos et sorties en kayak.")]),
    ("bricolage", "Travaux de la maison - {0}\n\n{1}\nNoter les mesures avant de commander quoi que ce soit.",
     [("peinture du salon", "Choisir un blanc cassé, protéger le parquet et poncer les boiseries au préalable."),
      ("étagères", "Fixer les étagères du couloir avec des chevilles adaptées à la cloison."),
      ("volets", "Huiler les gonds des volets et remplacer les crochets rouillés."),
      ("robinet", "Changer le joint du robinet de la cuisine, fermer l'arrivée d'eau avant de commencer."),
      ("terrasse", "Nettoyer les lames de la terrasse et passer une lasure de protection."),
      ("ampoules", "Remplacer les ampoules du sous-sol par des modèles basse consommation."),
      ("gouttière", "Dégager les feuilles de la gouttière avant l'arrivée de l'automne."),
      ("porte du cellier", "Raboter le bas de la porte du cellier qui frotte sur le carrelage.")]),
]


def build_distractors(target: Path) -> int:
    """Écrit les documents distracteurs sous `target/distracteurs/` ; renvoie leur nombre."""
    count = 0
    for theme, template, items in DISTRACTORS:
        for number, item in enumerate(items, start=1):
            text = template.format(*item)
            path = target / "distracteurs" / f"{theme}_{number:02d}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {text.splitlines()[0]}\n\n" + "\n".join(text.splitlines()[1:]).strip() + "\n",
                            encoding="utf-8")
            count += 1
    return count


def build(target: Path = CORPUS) -> None:
    target.mkdir(parents=True, exist_ok=True)

    write_pdf(target / "assurance" / "contrat_habitation.pdf", [
        "Contrat d'assurance habitation n° HAB-2023-0417",
        "Assuré : famille Martin, 12 rue des Lilas, 69003 Lyon",
        "Assureur : Mutuelle du Rhône",
        "Prime annuelle : 412 euros, payable en deux fois.",
        "Franchise : 250 euros par sinistre (dégât des eaux, vol, incendie).",
        "Date d'effet : 1er janvier 2023.",
        "Échéance du contrat : 31 décembre 2025, reconduction tacite.",
    ])
    write_pdf(target / "edf" / "facture.pdf", [
        "Facture d'électricité EDF - novembre 2024",
        "Client : famille Martin",
        "Consommation : 412 kWh sur la période.",
        "Montant total à payer : 87,40 euros.",
        "Date limite de paiement : 15 décembre 2024.",
    ])
    write_pdf(target / "garage" / "facture.pdf", [
        "Garage Dupuis - Facture de réparation",
        "Client : Marie Martin, véhicule Renault Clio",
        "Révision et remplacement des plaquettes de frein.",
        "Montant total à payer : 342,00 euros.",
        "Date de la facture : 8 mars 2024.",
    ])

    document = DocxDocument()
    document.add_paragraph("Budget familial 2024 - prévisions validées en janvier.")
    table = document.add_table(rows=4, cols=2)
    for row, (poste, montant) in enumerate([
        ("Poste", "Budget annuel (euros)"),
        ("Vacances", "1800"),
        ("Loisirs des enfants", "950"),
        ("Cadeaux de Noël", "600"),
    ]):
        table.cell(row, 0).text = poste
        table.cell(row, 1).text = montant
    document.add_paragraph("Le budget sera révisé en juillet.")
    document.save(target / "budget_2024.docx")

    invitation = EmailMessage()
    invitation["Subject"] = "Invitation anniversaire"
    invitation["From"] = "Marie Martin <marie@example.org>"
    invitation["To"] = "famille@example.org"
    invitation["Date"] = "Mon, 04 Mar 2024 09:00:00 +0000"
    invitation.set_content(
        "Bonjour à tous,\n\nL'anniversaire de Léa aura lieu samedi 16 mars à 15 h 30 à la maison.\n"
        "Tante Claire apporte le gâteau, Hugo s'occupe de la musique.\n"
        "Merci de confirmer votre présence avant jeudi.\n\nMarie\n",
        charset="utf-8",
    )
    (target / "invitation_anniversaire.eml").write_bytes(bytes(invitation))

    # Sujet encodé (RFC 2047) : écrit à la main pour contrôler l'en-tête brut (F23)
    (target / "sujet_encode.eml").write_bytes(
        b"Subject: =?utf-8?q?D=C3=AEner_dimanche?=\r\n"
        b"From: Marie Martin <marie@example.org>\r\n"
        b"To: famille@example.org\r\n"
        b"Date: Wed, 06 Mar 2024 18:00:00 +0000\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n\r\n"
        b"On se retrouve chez mamie pour le d\xc3\xaener de dimanche, vers 19 h.\r\n"
    )

    image = Image.new("RGB", (900, 260), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=34)
    draw.text((30, 30), "Tarte aux pommes de mamie", fill="black", font=font)
    draw.text((30, 100), "Four : 180 degres pendant 35 minutes", fill="black", font=font)
    draw.text((30, 170), "Laisser refroidir avant de servir", fill="black", font=font)
    image.save(target / "recette_scan.png")

    (target / "recettes.md").write_text(
        "# Recettes de famille\n\n## Tarte aux pommes\n\nIngrédients :\n\n"
        "- 6 pommes\n- 250 g de farine\n- 125 g de beurre\n- 80 g de sucre\n\n"
        "Étapes :\n\n1. Préparer la pâte et la laisser reposer.\n2. Disposer les pommes en rosace.\n"
        "3. Cuire au four.\n\n## Crêpes\n\n- 250 g de farine\n- 3 oeufs\n- 50 cl de lait\n",
        encoding="utf-8",
    )
    (target / "menage.md").write_text(
        "# Planning des tâches ménagères\n\n| Jour | Tâche | Responsable |\n|---|---|---|\n"
        "| Lundi | Vaisselle | Léa |\n| Mardi | Sortir les poubelles | Hugo |\n"
        "| Mercredi | Aspirateur | Marie |\n| Jeudi | Courses | Papa |\n",
        encoding="utf-8",
    )
    # Un seul caractère accentué : chardet le classe en ISO-8859-1 (confiance 0,73), voir F24
    (target / "note_courte.txt").write_text(
        "Bonjour à tous, la clef du chalet est dans le tiroir du couloir.\n", encoding="utf-8"
    )

    build_distractors(target)


if __name__ == "__main__":
    build()
    print(f"Corpus écrit dans {CORPUS}", file=sys.stderr)

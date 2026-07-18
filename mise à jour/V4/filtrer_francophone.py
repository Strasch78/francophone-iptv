"""
Filtre les chaînes francophones du dépôt Romaxa (world_ip_tv)
--------------------------------------------------------------
1. Télécharge le M3U global
2. Liste tous les pays/groupes détectés (group-title)
3. Filtre uniquement les pays francophones (liste étendue + normalisation
   des accents/majuscules pour éviter de rater "Côte d'Ivoire", "RDC", etc.)
4. Écrit un fichier M3U propre : liste_francophone.m3u
"""

import re
import unicodedata
import requests

URL_ROMAXA = "https://romaxa55.github.io/world_ip_tv/output/index.m3u"
FICHIER_SORTIE = "liste_francophone.m3u"

# Liste étendue des pays francophones (variantes EN/FR incluses,
# car Romaxa mélange les deux selon les sources agrégées)
PAYS_FRANCOPHONES = {
    "france", "cameroon", "cameroun",
    "ivory coast", "cote d ivoire", "côte d'ivoire", "cote divoire",
    "senegal", "sénégal",
    "gabon",
    "mali",
    "benin", "bénin",
    "chad", "tchad",
    "togo",
    "congo", "republic of the congo", "republique du congo",
    "drc", "dr congo", "rdc", "democratic republic of the congo",
    "republique democratique du congo",
    "niger",
    "burkina faso",
    "guinea", "guinee", "guinée",
    "madagascar",
    "rwanda",
    "burundi",
    "djibouti",
    "belgium", "belgique",
    "switzerland", "suisse",
    "canada", "quebec", "québec",
    "haiti", "haïti",
    "luxembourg",
    "monaco",
    "central african republic", "republique centrafricaine",
    "comoros", "comores",
    "mauritania", "mauritanie",
    "seychelles",
    "vanuatu",
    # Territoires / départements français d'outre-mer (DOM-TOM)
    "reunion", "réunion",
    "guadeloupe",
    "martinique",
    "mayotte",
    "french guiana", "guyane francaise", "guyane",
    "french polynesia", "polynesie francaise",
    "french southern territories",
    "new caledonia", "nouvelle caledonie",
    "saint martin",
    "saint barthelemy", "saint barthélemy",
    "saint pierre and miquelon", "saint pierre et miquelon",
    "wallis and futuna",
}


def normaliser(texte: str) -> str:
    """Minuscule + suppression des accents pour comparaison robuste."""
    texte = texte.strip().lower()
    texte = unicodedata.normalize("NFKD", texte)
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return texte


def telecharger_m3u(url: str) -> list[str]:
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.text.splitlines()


def analyser_pays(lignes: list[str]) -> set[str]:
    pays = set()
    for ligne in lignes:
        if ligne.startswith("#EXTINF"):
            match = re.search(r'group-title="([^"]+)"', ligne)
            if match:
                pays.add(match.group(1))
    return pays


def filtrer_francophone(lignes: list[str]):
    nouvelle_playlist = ["#EXTM3U\n"]
    compteur = 0
    pays_retenus = set()

    for index, ligne in enumerate(lignes):
        if ligne.startswith("#EXTINF"):
            match = re.search(r'group-title="([^"]+)"', ligne)
            if match:
                nom_pays = match.group(1)
                if normaliser(nom_pays) in PAYS_FRANCOPHONES:
                    nouvelle_playlist.append(ligne + "\n")
                    pays_retenus.add(nom_pays)
                    if index + 1 < len(lignes):
                        nouvelle_playlist.append(lignes[index + 1] + "\n")
                    compteur += 1
    return nouvelle_playlist, pays_retenus, compteur


def main():
    print("1. Téléchargement du M3U global Romaxa...")
    lignes = telecharger_m3u(URL_ROMAXA)

    print("2. Détection de tous les pays/groupes couverts...")
    pays_detectes = analyser_pays(lignes)
    print(f"   -> {len(pays_detectes)} pays/groupes trouvés")
    print("   " + ", ".join(sorted(pays_detectes)))
    print("-" * 50)

    print("3. Filtrage des chaînes francophones...")
    playlist, pays_retenus, compteur = filtrer_francophone(lignes)

    with open(FICHIER_SORTIE, "w", encoding="utf-8") as f:
        f.writelines(playlist)

    print("✅ Terminé.")
    print(f"   Pays francophones trouvés : {', '.join(sorted(pays_retenus))}")
    print(f"   Chaînes sauvegardées : {compteur}")
    print(f"   Fichier : {FICHIER_SORTIE}")


if __name__ == "__main__":
    main()

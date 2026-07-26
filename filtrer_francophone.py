"""
Filtre les chaînes francophones du dépôt Romaxa (world_ip_tv)
--------------------------------------------------------------
1. Télécharge le M3U global
2. Filtre uniquement les groupes (pays) francophones
3. Déduplique les chaînes (une même chaîne réapparaît souvent sous
   plusieurs pays dans la source d'origine -> on ne la garde qu'une fois
   par fichier de sortie)
4. Génère :
   - un fichier M3U par pays          -> output/par_pays/<Pays>.m3u
   - un fichier M3U par catégorie     -> output/par_categorie/<Categorie>.m3u
   - un fichier M3U combiné classé
     par catégorie (group-title = catégorie) -> output/toutes_categories.m3u
   - le fichier "à plat" habituel     -> output/francophone.m3u

La catégorie de chaque chaîne n'est PAS déduite uniquement de mots-clés
dans son nom : elle vient d'un dictionnaire construit chaîne par chaîne
à partir de ce que sont réellement ces chaînes (TF1 = généraliste,
Trace Naija = musique, KTO = religieux, TSN1 = sport, etc.). Un
classement heuristique de secours n'intervient que pour une chaîne
totalement inconnue qui n'existerait pas encore dans le dictionnaire.
"""

import os
import re
import time
import unicodedata
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

URL_ROMAXA = "https://romaxa55.github.io/world_ip_tv/output/index.m3u"
URL_IPTV_ORG = "https://iptv-org.github.io/iptv/languages/fra.m3u"
DOSSIER_SORTIE = "output"
FICHIER_SORTIE = f"{DOSSIER_SORTIE}/francophone.m3u"
DOSSIER_PAR_PAYS = f"{DOSSIER_SORTIE}/par_pays"
DOSSIER_PAR_CATEGORIE = f"{DOSSIER_SORTIE}/par_categorie"
FICHIER_TOUTES_CATEGORIES = f"{DOSSIER_SORTIE}/toutes_categories.m3u"
FICHIER_BONUS_IPTVORG = f"{DOSSIER_SORTIE}/bonus_iptv_org.m3u"

# Vérification des flux : activée par défaut pour les chaînes iptv-org
# (bonus) uniquement -- Romaxa est déjà vérifiée toutes les 6h côté source,
# inutile de la revérifier ici. Peut être désactivée via la variable
# d'environnement VERIFIER_FLUX_BONUS=0 (utile si tu exécutes le script
# depuis un environnement dont l'IP est fréquemment bloquée par les
# fournisseurs, ce qui fausserait le résultat).
VERIFIER_FLUX_BONUS = os.environ.get("VERIFIER_FLUX_BONUS", "1") != "0"

# Pays par défaut attribué aux chaînes bonus iptv-org dont le group-title
# d'origine ne correspond à aucun pays francophone reconnu (ex: iptv-org
# n'indique parfois qu'une catégorie, pas un pays).
PAYS_PAR_DEFAUT_IPTVORG = "Francophonie (iptv-org)"

# ---------------------------------------------------------------------------
# 1. Pays francophones retenus
# ---------------------------------------------------------------------------

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
    "wallis and futuna",
    "saint pierre and miquelon",
}

# ---------------------------------------------------------------------------
# 2. Catégories
# ---------------------------------------------------------------------------

# code interne -> libellé affiché / nom de fichier
CATEGORIES = {
    "info":      "Actualites-Info",
    "sport":     "Sport",
    "cine":      "Cinema-Series",
    "divert":    "Divertissement",
    "jeunesse":  "Jeunesse",
    "musique":   "Musique",
    "doc":       "Documentaire-Decouverte",
    "religion":  "Religieux-Spiritualite",
    "lifestyle": "Lifestyle-Mode",
    "diaspora":  "Communautaire-Diaspora",
    "regional":  "Regional-Locale",
    "general":   "Generaliste",
}

# Dictionnaire chaîne -> catégorie, construit à partir de la connaissance
# réelle de chaque chaîne (identité, éditeur, type de programmes), et non
# d'une simple recherche de mots-clés dans le nom.
# Clé = nom de la chaîne "nettoyé" (sans résolution ni tag [..]).
CHAINE_CATEGORIE = {
    "20 Minutes TV": "info",
    "3ABN Canada": "religion",
    "3ABN International": "religion",
    "3sat HD": "doc",
    "5AAB TV": "diaspora",
    "6ter": "divert",
    "7 Info": "info",
    "A&E": "doc",
    "A12 TV": "general",
    "A2i Music": "musique",
    "A2i Religion": "religion",
    "A2i TV": "general",
    "AB1": "divert",
    "ABC News": "info",
    "ABN Africa": "info",
    "Abu Dhabi Sports 1": "sport",
    "Acerfi TV": "general",
    "ACN TV": "diaspora",
    "ACTV": "diaspora",
    "ADN TV+": "general",
    "ADO TV": "general",
    "Aflam": "cine",
    "Africa 24": "info",
    "Africa 24 English": "info",
    "Africa 24 Sport": "sport",
    "Africanews English": "info",
    "Africanews French": "info",
    "Afro Magic Channel": "cine",
    "Afroculture TV": "diaspora",
    "Afroturk TV": "diaspora",
    "Al Arabiya": "info",
    "Al Arabiya Al Hadath": "info",
    "Al Arabiya Business": "info",
    "Al Arabiya Programs": "divert",
    "Al Araby TV": "info",
    "Al Araby TV 2": "info",
    "Al Hayat TV": "religion",
    "Al Jazeera": "info",
    "Al Jazeera Documentary": "doc",
    "Al Jazeera Mubasher": "info",
    "Al Jazeera Mubasher 24": "info",
    "Al Jazeera Mubasher Broadcast 2": "info",
    "Al Qamar TV": "religion",
    "Allo Cine": "cine",
    "Alpe d’Huez TV": "regional",
    "Amazing Discoveries TV": "religion",
    "Animation+": "jeunesse",
    "Antenne Réunion": "regional",
    "apart TV": "general",
    "Arirang TV UN": "general",
    "arte": "doc",
    "Asharq Discovery": "doc",
    "Asharq Documentary": "doc",
    "ATV": "diaspora",
    "Autentic History": "doc",
    "Autentic Travel": "doc",
    "Ayaz TV": "diaspora",
    "Azan TV": "religion",
    "Azstar TV HD": "diaspora",
    "B+ TV": "general",
    "Bab Al Hara": "cine",
    "BabyTV France HD": "jeunesse",
    "Bahrain International": "general",
    "BAM-TV": "diaspora",
    "Banijay Mr Bean Animé": "jeunesse",
    "BBC Arabic": "info",
    "BBC News": "info",
    "BBC News (North America)": "info",
    "BBC News Asia Pacific": "info",
    "Benie TV": "religion",
    "BFM2": "info",
    "Bloomberg TV Asia": "info",
    "Bloomberg TV Asia Live Event": "info",
    "Bloomberg TV EMEA Live Event": "info",
    "Bouke": "jeunesse",
    "BPX TV Radio": "musique",
    "Brionnais TV": "regional",
    "BVN": "general",
    "BX1": "regional",
    "C Malayalam TV": "diaspora",
    "C Star": "divert",
    "Caillou": "jeunesse",
    "CAM 10 TV": "general",
    "Canaf54 TV": "diaspora",
    "Canal 2 International": "general",
    "Canal Alpha Jura": "regional",
    "Canal Alpha Neuchatel": "regional",
    "Canal J HD": "jeunesse",
    "Canal Savoir": "doc",
    "Cannes Lérins TV": "regional",
    "Cap Terre": "doc",
    "Carac 1": "general",
    "Carac 2": "general",
    "Carac 3": "general",
    "Carac 4": "general",
    "Carac 5": "general",
    "Caribbean Advantage TV": "diaspora",
    "CBC News": "info",
    "CCPV TV": "religion",
    "CCTV-4 America": "info",
    "CFTO-DT": "regional",
    "CGTN": "info",
    "CGTN Arabic": "info",
    "CGTN Documentary": "doc",
    "CGTN Français": "info",
    "Chamber TV": "general",
    "Chandel TV": "diaspora",
    "Channel Y": "general",
    "CHCO-TV": "regional",
    "Cine+ Emotion": "cine",
    "CityNews Calgary": "regional",
    "CityNews Edmonton": "regional",
    "CityNews Toronto": "regional",
    "CityNews Vancouver": "regional",
    "Classic Arts Showcase": "doc",
    "CNBC Arabiya": "info",
    "CNews": "info",
    "CNEWS PRIME": "info",
    "Compassion TV": "religion",
    "Couleur 3": "musique",
    "Cowboy Channel": "sport",
    "CRTV": "general",
    "CRTV News": "info",
    "CTV 2 Atlantic": "regional",
    "D3 TV": "general",
    "DBM TV": "religion",
    "DesheBideshe TV": "diaspora",
    "Deshi TV": "diaspora",
    "Diaspora 24": "diaspora",
    "Die Neue Zeit": "info",
    "Disney Jr.": "jeunesse",
    "Doyel TV": "diaspora",
    "Dubai One": "divert",
    "Dudelange TV": "regional",
    "Dukh Nivaran": "religion",
    "DW Arabic": "info",
    "Eawaz TV": "diaspora",
    "Eden TV": "religion",
    "EET TV": "general",
    "eldo.TV": "general",
    "EnerGeek": "info",
    "EnerGeek Radio": "info",
    "Equidia": "sport",
    "Erfan Halgheh TV": "religion",
    "Espace TV": "divert",
    "ETB Basque": "regional",
    "ETV": "general",
    "Euro Indie Music Chart TV": "musique",
    "Euronews French": "info",
    "Ev-tele": "religion",
    "EVI TV": "diaspora",
    "EWTN Africa Asia": "religion",
    "EWTN Asia-Pacific": "religion",
    "EWTN Canada": "religion",
    "FashionTV Paris L'Original": "lifestyle",
    "FashionTV Secrets": "lifestyle",
    "FIFA+ French": "sport",
    "FIFA+ German": "sport",
    "FIFA+ United States": "sport",
    "Filinfo TV": "info",
    "FilmRise Anime": "jeunesse",
    "Foot+": "sport",
    "For You TV": "divert",
    "France 24 Arabic": "info",
    "France 24 French": "info",
    "France 4": "jeunesse",
    "Francophonie24": "info",
    "FUEL TV": "sport",
    "Fun Vision": "musique",
    "FUSION TV": "divert",
    "Gabon 1ere": "general",
    "Game+": "divert",
    "Garage TV Latin America": "sport",
    "Gaunda Punjab TV": "diaspora",
    "GMS TV": "general",
    "GO-TV Canale 163": "general",
    "Gong": "divert",
    "GTN Canada": "diaspora",
    "Guide Love TV": "divert",
    "Gulli HD": "jeunesse",
    "GurSikh Sabha TV": "religion",
    "Géopolis TV": "doc",
    "Haiti News Channel": "info",
    "HANDICAP TV France": "general",
    "HC2 TV": "divert",
    "Hesper TV": "diaspora",
    "HMI PROMZ NEWS": "info",
    "Home Network": "lifestyle",
    "Hyder TV": "diaspora",
    "I24 News English": "info",
    "IBN TV Africa": "info",
    "ICI Montreal": "general",
    "ICI RDI": "info",
    "icnet 1": "general",
    "ICONE TV": "divert",
    "Identité Télé Caraïbes": "diaspora",
    "IIPC TV": "religion",
    "Immaculata TV": "religion",
    "INWILD": "doc",
    "Isango TV": "general",
    "Isibo TV": "general",
    "Ivoire Channel": "general",
    "Japanim TV": "jeunesse",
    "Kajou TV": "general",
    "Kalac TV": "general",
    "Kanade": "musique",
    "KassouaTV": "general",
    "KC2": "general",
    "Kidoodle.TV": "jeunesse",
    "Knowledge Network": "doc",
    "Kozoom TV": "sport",
    "KTO": "religion",
    "La Trois": "general",
    "La Une": "general",
    "Laura Dave Media TV": "divert",
    "LCI HD": "info",
    "Le Figaro IDF": "info",
    "Le Nouveau Manager TV": "divert",
    "Legislative Assembly of Ontario": "general",
    "Legislative Assembly TV Nunavut": "general",
    "Littoral FM": "musique",
    "LMTV French": "general",
    "Lollywood HD TV": "cine",
    "Louga TV": "regional",
    "Love Nature": "doc",
    "Love Nature 4K": "doc",
    "M6 Music": "musique",
    "Madras FM TV": "musique",
    "Majid": "jeunesse",
    "Mamer TV": "regional",
    "MaTele": "regional",
    "MaxTV/Dieu TV": "religion",
    "MBC 1": "divert",
    "MBC 4": "divert",
    "MBC 5": "divert",
    "MBC Bollywood": "cine",
    "MBC Drama KSA": "cine",
    "MBC FM": "musique",
    "MDL": "general",
    "Medi 1 TV Afrique": "info",
    "Medi 1 TV Arabic": "info",
    "Meteonews": "info",
    "Mezzo": "musique",
    "MHZ": "cine",
    "MierschTV": "regional",
    "Miracle TV+": "religion",
    "Monte Carlo Digital Television": "general",
    "More Than Sports TV": "sport",
    "Movies Action": "cine",
    "Movies Thriller": "cine",
    "Mr. Bean Animated": "jeunesse",
    "MTV": "musique",
    "Much": "musique",
    "My Cinema Europe": "cine",
    "My Gospel TV": "religion",
    "My TV Channel": "general",
    "MyZen TV": "lifestyle",
    "Nachrichten 360": "info",
    "NACTV": "general",
    "Nash Bridges Channel": "cine",
    "National Geographic Wild": "doc",
    "Nature Time France": "doc",
    "NDR Fernsehen International": "general",
    "Newfoundland Television": "regional",
    "NHK World-Japan": "info",
    "Nickelodeon": "jeunesse",
    "Nickelodeon Junior": "jeunesse",
    "Nollywood TV": "cine",
    "Notele": "regional",
    "Now TV 102.3FM Edmonton (CKNO-FM)": "musique",
    "NTD TV Canada": "info",
    "NTD TV Canada West": "info",
    "NTV Afrique": "info",
    "NTV+": "general",
    "Numerica TV": "general",
    "NW Sport 1": "sport",
    "Ontario Parliamentary Network": "general",
    "Outdoor Channel": "sport",
    "Outdoor Channel HD": "sport",
    "P2M TV": "general",
    "Pamir TV": "diaspora",
    "Paramount Network": "cine",
    "Pardesi TV": "diaspora",
    "Passion Novelas": "cine",
    "PBC Tapesh TV": "divert",
    "PBS Travel": "doc",
    "Peace TV English": "religion",
    "Play TV": "divert",
    "PLEX TV": "divert",
    "PMC Royale": "general",
    "PRIDEtv LATAM": "diaspora",
    "Prime Asia TV": "diaspora",
    "Probashi TV News": "info",
    "Puissance TV": "religion",
    "Pétange Info TV": "regional",
    "Qello Concerts by Stingray": "musique",
    "Quo Vadis TV": "religion",
    "Qwest TV": "musique",
    "Qwest TV Jazz & Beyond": "musique",
    "Radio 3i": "musique",
    "Radio Tele Evangile Sans Limite": "religion",
    "Radio Tele Full Gospel": "religion",
    "Radio Tele Ginen": "general",
    "Radio Tele Planet Compas": "musique",
    "Radio Tele Puissance": "religion",
    "Radio Tele Sentinel": "religion",
    "Radio TV Basse-Terre": "regional",
    "Radio Télé 4VEH": "religion",
    "Radio Télé Hit": "musique",
    "Ramez": "divert",
    "Red Bull TV": "sport",
    "Red Bull TV DE": "sport",
    "Red Bull TV US": "sport",
    "REFLET TV": "general",
    "Rema TV": "general",
    "RFM TV": "musique",
    "RHT Guadeloupe": "regional",
    "RMC Decouverte": "doc",
    "RMC Life": "divert",
    "RMC Story": "cine",
    "Roya Kids": "jeunesse",
    "Roya Kids Originals": "jeunesse",
    "RT Arabic": "info",
    "RT France": "info",
    "RT JVA": "info",
    "RTB 3": "general",
    "RTH-TV1": "general",
    "RTH-TV2 Gospel": "religion",
    "RTL Gold": "musique",
    "RTL Radio Web TV": "musique",
    "RTL Today Radio": "musique",
    "RTL Télé Lëtzebuerg": "general",
    "RTL Zwee": "general",
    "RTNB TV": "general",
    "RTS 1": "general",
    "RTS 3": "general",
    "RTS Info": "info",
    "RTV Pendimi": "general",
    "RTV Rwanda": "general",
    "RTVC": "general",
    "Savane TV": "general",
    "Seneweb TV": "info",
    "SenJeunes TV": "jeunesse",
    "Serie Club": "cine",
    "Sikh Spiritual Centre Rexdale": "religion",
    "Sivan TV": "diaspora",
    "Sky News Arabia": "info",
    "Sky News Arabia (Portrait)": "info",
    "Slice": "divert",
    "Sony One Blacklist": "cine",
    "Sony One Favoris": "cine",
    "Sony One Hits Action": "cine",
    "Sony One Hits Comedie": "cine",
    "Sooriyan TV": "diaspora",
    "Spacetoon Arabic": "jeunesse",
    "Speedline TV": "sport",
    "STAR International": "divert",
    "Sterk TV": "religion",
    "Stingray Classic Rock": "musique",
    "Stingray Classica": "musique",
    "Stingray CMusic": "musique",
    "Stingray DJAZZ": "musique",
    "Stingray Easy Listening": "musique",
    "Stingray Euro Hits": "musique",
    "Stingray Flashback 70s": "musique",
    "Stingray Hit List": "musique",
    "Stingray Holidayscapes": "musique",
    "Stingray Hot Country": "musique",
    "Stingray iConcerts HD": "musique",
    "Stingray Jukebox Oldies": "musique",
    "Stingray Karaoke": "musique",
    "Stingray Naturescape": "musique",
    "Stingray Nothin' But 90s": "musique",
    "Stingray Pop Adult": "musique",
    "Stingray Remember the 80s": "musique",
    "Stingray Rock Alternative": "musique",
    "Stingray Romance Latino": "musique",
    "Stingray Smooth Jazz": "musique",
    "Stingray Soul Storm": "musique",
    "Stingray The Spa": "musique",
    "Stingray Today's KPOP": "musique",
    "Stingray Today's Latin Pop": "musique",
    "Stingray Urban Beat": "musique",
    "StoryChannel TV": "cine",
    "Sun+ TV": "diaspora",
    "Super Channel Vault": "cine",
    "Superyacht TV": "lifestyle",
    "SVBC 2": "religion",
    "SVBC 3": "religion",
    "SVBC 4": "religion",
    "SVBC Sri Venkateswara Bhakti Channel": "religion",
    "T18": "general",
    "TAG TV": "general",
    "Tal TV": "general",
    "TamilVision-TV": "diaspora",
    "Tele Louange": "religion",
    "Tele Pam": "general",
    "Tele Sahel": "general",
    "Tele Tchad": "general",
    "Tele Zoukla": "musique",
    "Telenova": "cine",
    "Telesambre": "regional",
    "TeleTicino": "regional",
    "Television Espoir 47": "religion",
    "Tempo Afric TV": "general",
    "Terra Mater WILD": "doc",
    "Teva": "divert",
    "TFX": "divert",
    "The Conners": "cine",
    "The Graham Norton Show": "divert",
    "TiJi HD": "jeunesse",
    "Tipik": "divert",
    "TMA": "general",
    "TNTV": "general",
    "Today's Shopping Choice (TSC)": "divert",
    "Toronto 360 TV": "regional",
    "Total Crime": "cine",
    "TR24": "regional",
    "Trace Africa": "musique",
    "Trace Ayiti": "musique",
    "Trace Brasil": "musique",
    "TRACE Brazuca": "musique",
    "Trace Caribbean": "musique",
    "Trace Gospel Africa Franco": "musique",
    "Trace Ivoire": "musique",
    "Trace Jama": "musique",
    "Trace Kitoko": "musique",
    "Trace Latina": "musique",
    "Trace Mboa": "musique",
    "Trace Muzika": "musique",
    "Trace Mziki": "musique",
    "Trace Naija": "musique",
    "Trace Sport Stars (Australia)": "sport",
    "Trace Teranga": "musique",
    "Trace Urban (Australia)": "musique",
    "Trace Urban France": "musique",
    "Trace Vanilla Islands": "musique",
    "TRT Arabi": "info",
    "TSN The Ocho": "sport",
    "TSN1": "sport",
    "TSN2": "sport",
    "TSN3": "sport",
    "TSN4": "sport",
    "TSN5": "sport",
    "TV Breizh": "cine",
    "TV BRICS Africa": "info",
    "TV Centrafricaine": "general",
    "TV Famille": "general",
    "TV Monaco": "general",
    "TV Panou": "general",
    "TV Punjab": "diaspora",
    "TV10": "general",
    "TV3V": "general",
    "TV5 Quebec Canada": "general",
    "TV5Monde Style": "lifestyle",
    "TV7 Colmar": "regional",
    "TVC Bénin": "general",
    "TVE Internacional America": "general",
    "TVE Internacional America HD": "general",
    "TVI África": "general",
    "TVM Internacional": "general",
    "TVOKids": "jeunesse",
    "Télé Péyi": "general",
    "UN Web TV": "info",
    "ViàMatélé": "regional",
    "viàTéléPaese": "regional",
    "Vosges Télévision": "regional",
    "Wanasah": "divert",
    "Watan-e-Maa TV": "diaspora",
    "WaterBear": "doc",
    "Wild TV": "sport",
    "Willow Sports": "sport",
    "WION": "info",
    "WTV": "general",
    "XITE 90's Throwback": "musique",
    "XITE Nuevo Latino": "musique",
    "XITE Siempre Latino": "musique",
    "Zee One Français": "cine",
    "Zee One German": "cine",
    "zenith": "general",
    "Zitata TV": "general",
    "Zoo Moo (Australia)": "jeunesse",
    "Zylo Ciné Nanar": "cine",
    "Zylo Ciné Western": "cine",
    "Zylo Emotion' L": "cine",
    "Zylo Fréquence Novelas": "cine",
    "Zylo Into Crime": "cine",
    "Zylo ScreamIN": "cine",
    "СТС International": "divert",
}

# Classement de secours, utilisé UNIQUEMENT si une chaîne n'est pas dans
# CHAINE_CATEGORIE ci-dessus (nouvelle chaîne ajoutée par la source après
# la constitution de ce dictionnaire). Ce n'est qu'un filet de sécurité,
# pas la méthode principale de classement.
INDICES_SECOURS = [
    (["news", "info", "actualit", "nouvelles"], "info"),
    (["sport", "foot", "basket", "rugby", "tennis", "f1", "moto"], "sport"),
    (["cine", "cinema", "movie", "film", "serie", "drama", "novela"], "cine"),
    (["kids", "junior", "jeunesse", "enfant", "cartoon", "anime", "toon"], "jeunesse"),
    (["music", "musique", "radio", "fm ", "hits", "hit "], "musique"),
    (["doc", "discovery", "nature", "wild", "geo"], "doc"),
    (["gospel", "eglise", "evangile", "religio", "islam",
      "coran", "bible", "chretien", "catholi", "priere"], "religion"),
    (["mode", "fashion", "style", "beaute"], "lifestyle"),
    (["diaspora", "communaut"], "diaspora"),
    (["region", "regional", "local"], "regional"),
]


def normaliser(texte: str) -> str:
    """Minuscule + suppression des accents pour comparaison robuste."""
    texte = texte.strip().lower()
    texte = unicodedata.normalize("NFKD", texte)
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return texte


def nettoyer_nom_chaine(nom: str) -> str:
    """Retire les suffixes de résolution '(720p)' et les tags '[Not 24/7]'
    etc. pour obtenir le nom "propre" utilisé comme clé de catégorisation."""
    nom = re.sub(r"\s*\[[^\]]*\]", "", nom)
    nom = re.sub(r"\s*\((?:\d+p|\d+i|\d+K)\)", "", nom)
    return nom.strip()


_MOTS_QUALITE = {"hd", "fhd", "uhd", "shd", "4k", "hq", "sd", "tv"}


def cle_correspondance(nom: str) -> str:
    """Clé de rapprochement entre les DEUX sources (Romaxa / iptv-org) pour
    savoir si deux entrées désignent la même chaîne. Plus agressive que
    nettoyer_nom_chaine (utilisée pour l'affichage/la catégorisation) :
    on retire aussi les mentions de qualité (HD, 4K...) et la ponctuation,
    car les deux sources n'orthographient pas toujours les noms à
    l'identique (ex: "France 24" vs "France24 (1080p)")."""
    n = nettoyer_nom_chaine(nom)
    n = normaliser(n)
    n = re.sub(r"[^\w\s]", " ", n)  # ponctuation -> espace
    mots = [m for m in n.split() if m not in _MOTS_QUALITE]
    return " ".join(mots)


def categoriser_chaine(nom: str) -> str:
    """Retourne le code de catégorie d'une chaîne à partir de son nom
    complet (avec résolution/tags éventuels)."""
    nom_propre = nettoyer_nom_chaine(nom)

    if nom_propre in CHAINE_CATEGORIE:
        return CHAINE_CATEGORIE[nom_propre]

    # Filet de sécurité heuristique pour une chaîne totalement inconnue
    nom_norm = normaliser(nom_propre)
    for mots_cles, code in INDICES_SECOURS:
        if any(mot in nom_norm for mot in mots_cles):
            return code

    return "general"


def nom_fichier_valide(texte: str) -> str:
    """Transforme un nom de pays/catégorie en nom de fichier sûr."""
    texte = texte.strip().replace(" ", "_")
    texte = re.sub(r"[^\w\-\.]", "", texte, flags=re.UNICODE)
    return texte


# ---------------------------------------------------------------------------
# 3. Téléchargement et extraction des chaînes
# ---------------------------------------------------------------------------

def telecharger_m3u(url: str, tentatives: int = 3) -> list[str]:
    """Télécharge le M3U source avec un timeout généreux et des tentatives
    automatiques en cas de coupure/lenteur réseau (le fichier source est
    volumineux, un simple aléa réseau ne doit pas faire planter le
    rafraîchissement)."""
    derniere_erreur = None
    for tentative in range(1, tentatives + 1):
        try:
            r = requests.get(url, timeout=(10, 60))  # (connexion, lecture)
            r.raise_for_status()
            return r.text.splitlines()
        except requests.exceptions.RequestException as e:
            derniere_erreur = e
            print(f"[telecharger_m3u] Tentative {tentative}/{tentatives} échouée : {e}")
            if tentative < tentatives:
                time.sleep(3 * tentative)  # backoff : 3s, 6s, ...
    raise derniere_erreur


def telecharger_source(nom_source: str, url: str, tentatives: int = 3) -> list[str] | None:
    """Comme telecharger_m3u, mais NE LÈVE JAMAIS d'exception : renvoie
    None si la source est injoignable après toutes les tentatives, pour
    permettre au reste du programme de basculer automatiquement sur
    l'autre source plutôt que de tout faire planter."""
    try:
        return telecharger_m3u(url, tentatives=tentatives)
    except requests.exceptions.RequestException as e:
        print(f"[{nom_source}] ❌ Source injoignable après {tentatives} tentatives : {e}")
        return None


def extraire_chaines(lignes: list[str]) -> list[dict]:
    """Parcourt le M3U source Romaxa et renvoie la liste des chaînes des
    pays francophones, sous forme de dicts {pays, nom, logo, url,
    source}."""
    chaines = []
    for index, ligne in enumerate(lignes):
        if not ligne.startswith("#EXTINF"):
            continue
        match_pays = re.search(r'group-title="([^"]+)"', ligne)
        if not match_pays:
            continue
        pays = match_pays.group(1)
        if normaliser(pays) not in PAYS_FRANCOPHONES:
            continue
        if index + 1 >= len(lignes):
            continue
        url = lignes[index + 1].strip()
        if not url or url.startswith("#"):
            continue
        nom = ligne.split(",", 1)[-1].strip()
        match_logo = re.search(r'tvg-logo="([^"]*)"', ligne)
        logo = match_logo.group(1) if match_logo else ""
        chaines.append({"pays": pays, "nom": nom, "logo": logo, "url": url, "source": "romaxa"})
    return chaines


def extraire_chaines_iptvorg(lignes: list[str]) -> list[dict]:
    """Parcourt le M3U iptv-org (déjà filtré par langue française à la
    source -> https://iptv-org.github.io/iptv/languages/fra.m3u), sans
    filtrage supplémentaire par pays. Le pays affiché est celui du
    group-title d'origine s'il correspond à un pays francophone reconnu,
    sinon un pays générique "Francophonie (iptv-org)" est utilisé, afin
    que la chaîne ne soit pas perdue faute de correspondance exacte."""
    chaines = []
    for index, ligne in enumerate(lignes):
        if not ligne.startswith("#EXTINF"):
            continue
        if index + 1 >= len(lignes):
            continue
        url = lignes[index + 1].strip()
        if not url or url.startswith("#"):
            continue

        match_groupe = re.search(r'group-title="([^"]*)"', ligne)
        groupe_origine = match_groupe.group(1) if match_groupe else ""
        pays = groupe_origine if normaliser(groupe_origine) in PAYS_FRANCOPHONES else PAYS_PAR_DEFAUT_IPTVORG

        nom = ligne.split(",", 1)[-1].strip()
        if not nom:
            continue
        match_logo = re.search(r'tvg-logo="([^"]*)"', ligne)
        logo = match_logo.group(1) if match_logo else ""
        chaines.append({
            "pays": pays, "nom": nom, "logo": logo, "url": url,
            "source": "iptv-org",
        })
    return chaines


def fusionner_sources(chaines_romaxa: list[dict], chaines_iptvorg: list[dict]) -> tuple[list[dict], list[dict]]:
    """Fusionne les deux sources : Romaxa est prioritaire (vérifiée toutes
    les 6h côté source), donc en cas de même chaîne des deux côtés on garde
    la version Romaxa et on jette le doublon iptv-org. Les chaînes
    présentes UNIQUEMENT chez iptv-org sont ajoutées en bonus.

    Renvoie (chaines_fusionnees, chaines_bonus_ajoutees)."""
    cles_romaxa = {cle_correspondance(c["nom"]) for c in chaines_romaxa}

    bonus = []
    cles_bonus_vues = set()
    for c in chaines_iptvorg:
        cle = cle_correspondance(c["nom"])
        if not cle or cle in cles_romaxa or cle in cles_bonus_vues:
            continue
        cles_bonus_vues.add(cle)
        bonus.append(c)

    for c in chaines_romaxa:
        c.setdefault("source", "romaxa")

    return chaines_romaxa + bonus, bonus


# ---------------------------------------------------------------------------
# Vérification des flux (chaînes réellement accessibles)
# ---------------------------------------------------------------------------
#
# ATTENTION à un piège classique : le résultat de cette vérification dépend
# ÉNORMÉMENT d'où elle est exécutée. Beaucoup de fournisseurs IPTV bloquent
# les IP de datacenter (AWS, Azure, GCP...) même quand le flux fonctionne
# très bien pour un vrai spectateur sur une connexion résidentielle. Or les
# runners GitHub Actions tournent sur Azure. Exécuter cette vérification
# depuis le workflow risque donc de supprimer des chaînes qui marchent en
# réalité, juste parce que l'IP du runner est bloquée.
#
# -> Il est recommandé d'exécuter `python filtrer_francophone.py` avec la
#    vérification activée depuis une connexion "normale" (ta machine, ta
#    box), pas uniquement depuis GitHub Actions.

def verifier_flux(url: str, timeout: float = 6.0) -> bool:
    """Teste si un flux répond, sans télécharger tout le flux (juste les
    en-têtes + un petit bout du corps). Renvoie True si le flux semble
    accessible."""
    try:
        with requests.get(
            url, timeout=timeout, stream=True,
            headers={"User-Agent": "Mozilla/5.0"},
            allow_redirects=True,
        ) as r:
            if r.status_code >= 400:
                return False
            # On lit un tout petit peu pour confirmer qu'il y a bien des
            # données qui arrivent (certains serveurs renvoient 200 puis
            # ne renvoient jamais rien).
            next(r.iter_content(chunk_size=512), None)
            return True
    except requests.exceptions.RequestException:
        return False
    except StopIteration:
        return True  # flux vide mais connexion OK (rare, on ne pénalise pas)


def filtrer_chaines_actives(chaines: list[dict], max_threads: int = 30, timeout: float = 6.0) -> tuple[list[dict], list[dict]]:
    """Vérifie en parallèle chaque chaîne et ne garde que celles qui
    répondent. Renvoie (chaines_actives, chaines_mortes_retirees)."""
    actives, mortes = [], []
    total = len(chaines)
    print(f"   Vérification de {total} flux (jusqu'à {max_threads} en parallèle, "
          f"timeout {timeout}s)...")
    debut = time.time()

    with ThreadPoolExecutor(max_workers=max_threads) as executeur:
        futur_vers_chaine = {
            executeur.submit(verifier_flux, c["url"], timeout): c for c in chaines
        }
        traitees = 0
        for futur in as_completed(futur_vers_chaine):
            c = futur_vers_chaine[futur]
            traitees += 1
            if futur.result():
                actives.append(c)
            else:
                mortes.append(c)
            if traitees % 100 == 0 or traitees == total:
                print(f"      ... {traitees}/{total} vérifiées "
                      f"({len(actives)} actives, {len(mortes)} mortes)")

    duree = time.time() - debut
    print(f"   -> {len(actives)}/{total} chaînes actives "
          f"({len(mortes)} retirées) en {duree:.0f}s")
    return actives, mortes





# ---------------------------------------------------------------------------
# 4. Déduplication
# ---------------------------------------------------------------------------

def dedupliquer(chaines: list[dict], cle=lambda c: c["url"]) -> list[dict]:
    """Ne garde que la première occurrence de chaque clé (par défaut : URL
    du flux, ce qui est le seul identifiant vraiment fiable puisqu'une même
    chaîne peut être listée sous plusieurs pays)."""
    vus = set()
    resultat = []
    for c in chaines:
        k = cle(c)
        if k in vus:
            continue
        vus.add(k)
        resultat.append(c)
    return resultat


# ---------------------------------------------------------------------------
# 5. Écriture des fichiers M3U
# ---------------------------------------------------------------------------

def ligne_extinf(chaine: dict, group_title: str) -> str:
    return f'#EXTINF:-1 tvg-logo="{chaine["logo"]}" group-title="{group_title}",{chaine["nom"]}\n'


def ecrire_m3u(chemin: str, chaines: list[dict], group_title_fn) -> None:
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    with open(chemin, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for c in chaines:
            f.write(ligne_extinf(c, group_title_fn(c)))
            f.write(c["url"] + "\n")


def generer_par_pays(chaines: list[dict]) -> dict:
    """Un fichier M3U par pays, dédupliqué (par URL) à l'intérieur de
    chaque pays. Renvoie {pays: nb_chaines}."""
    par_pays: dict[str, list[dict]] = {}
    for c in chaines:
        par_pays.setdefault(c["pays"], []).append(c)

    stats = {}
    for pays, liste in par_pays.items():
        liste_dedup = dedupliquer(liste)
        chemin = f"{DOSSIER_PAR_PAYS}/{nom_fichier_valide(pays)}.m3u"
        ecrire_m3u(chemin, liste_dedup, lambda c: c["pays"])
        stats[pays] = len(liste_dedup)
    return stats


def generer_par_categorie(chaines_uniques: list[dict]) -> dict:
    """Un fichier M3U par catégorie (à partir de la liste déjà
    dédupliquée globalement). Renvoie {categorie: nb_chaines}."""
    par_categorie: dict[str, list[dict]] = {}
    for c in chaines_uniques:
        code = categoriser_chaine(c["nom"])
        libelle = CATEGORIES[code]
        par_categorie.setdefault(libelle, []).append(c)

    stats = {}
    for libelle, liste in par_categorie.items():
        liste_triee = sorted(liste, key=lambda c: c["nom"].lower())
        chemin = f"{DOSSIER_PAR_CATEGORIE}/{nom_fichier_valide(libelle)}.m3u"
        ecrire_m3u(chemin, liste_triee, lambda c: libelle)
        stats[libelle] = len(liste_triee)

    # Fichier combiné unique, group-title = catégorie (pratique pour les
    # applis IPTV qui affichent les groupes comme des catégories/dossiers)
    toutes = []
    for libelle in sorted(par_categorie.keys()):
        toutes.extend(sorted(par_categorie[libelle], key=lambda c: c["nom"].lower()))
    ecrire_m3u(
        FICHIER_TOUTES_CATEGORIES,
        toutes,
        lambda c: CATEGORIES[categoriser_chaine(c["nom"])],
    )
    return stats


def ecrire_bonus_iptvorg(bonus: list[dict]) -> None:
    """Fichier d'audit listant UNIQUEMENT les chaînes ajoutées par la
    source secondaire iptv-org (absentes de Romaxa), pour que tu puisses
    vérifier facilement ce qui a été ajouté à chaque mise à jour."""
    ecrire_m3u(FICHIER_BONUS_IPTVORG, sorted(bonus, key=lambda c: c["nom"].lower()), lambda c: c["pays"])


def main():
    print("1. Téléchargement des sources...")
    lignes_romaxa = telecharger_source("romaxa", URL_ROMAXA)
    lignes_iptvorg = telecharger_source("iptv-org", URL_IPTV_ORG)

    if lignes_romaxa is None and lignes_iptvorg is None:
        print("❌ Les DEUX sources sont injoignables. Abandon : les fichiers de")
        print("   sortie existants ne sont PAS modifiés (on garde la dernière")
        print("   version connue plutôt que de publier une playlist vide).")
        raise SystemExit(1)

    print("2. Extraction des chaînes francophones...")
    chaines_romaxa = extraire_chaines(lignes_romaxa) if lignes_romaxa is not None else []
    chaines_iptvorg = extraire_chaines_iptvorg(lignes_iptvorg) if lignes_iptvorg is not None else []
    print(f"   -> Romaxa   : {len(chaines_romaxa)} entrées"
          + (" (source indisponible, ignorée)" if lignes_romaxa is None else ""))
    print(f"   -> iptv-org : {len(chaines_iptvorg)} entrées"
          + (" (source indisponible, ignorée)" if lignes_iptvorg is None else ""))

    print("3. Fusion des deux sources (Romaxa prioritaire en cas de doublon)...")
    chaines, bonus = fusionner_sources(chaines_romaxa, chaines_iptvorg)
    print(f"   -> {len(bonus)} chaînes ajoutées en bonus depuis iptv-org")

    if VERIFIER_FLUX_BONUS and bonus:
        print("3bis. Vérification des flux bonus iptv-org (Romaxa déjà vérifiée "
              "à la source)...")
        bonus_actifs, bonus_morts = filtrer_chaines_actives(bonus)
        if bonus_morts:
            print(f"    Chaînes bonus retirées (flux injoignable) : "
                  f"{', '.join(c['nom'] for c in bonus_morts[:15])}"
                  + (f", ... (+{len(bonus_morts) - 15})" if len(bonus_morts) > 15 else ""))
        chaines = chaines_romaxa + bonus_actifs
        bonus = bonus_actifs

    print("4. Génération des fichiers par pays...")
    stats_pays = generer_par_pays(chaines)
    total_pays = sum(stats_pays.values())
    print(f"   -> {len(stats_pays)} pays, {total_pays} chaînes au total")
    for pays in sorted(stats_pays):
        print(f"      - {pays}: {stats_pays[pays]} chaînes")

    print("5. Déduplication globale (par URL) pour le classement par catégorie...")
    chaines_uniques = dedupliquer(chaines)
    print(f"   -> {len(chaines_uniques)} chaînes uniques (sur {len(chaines)} entrées)")

    print("6. Génération des fichiers par catégorie...")
    stats_cat = generer_par_categorie(chaines_uniques)
    for cat in sorted(stats_cat):
        print(f"      - {cat}: {stats_cat[cat]} chaînes")

    print("7. Génération du fichier plat classique (rétrocompatibilité)...")
    ecrire_m3u(FICHIER_SORTIE, chaines_uniques, lambda c: c["pays"])

    print("8. Génération du fichier d'audit des chaînes bonus iptv-org...")
    ecrire_bonus_iptvorg(bonus)

    print("✅ Terminé.")
    print(f"   Fichiers par pays      : {DOSSIER_PAR_PAYS}/")
    print(f"   Fichiers par catégorie : {DOSSIER_PAR_CATEGORIE}/")
    print(f"   Fichier combiné        : {FICHIER_TOUTES_CATEGORIES}")
    print(f"   Fichier plat           : {FICHIER_SORTIE}")
    print(f"   Audit bonus iptv-org   : {FICHIER_BONUS_IPTVORG}")


if __name__ == "__main__":
    main()
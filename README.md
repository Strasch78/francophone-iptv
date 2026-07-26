# Francophone IPTV

Ce projet extrait, dédoublonne et classe les chaînes **francophones** (France,
Belgique, Suisse, Canada/Québec, DOM-TOM, et pays d'Afrique/Caraïbes
francophones) à partir de **deux sources fusionnées** :

- **[romaxa55/world_ip_tv](https://github.com/romaxa55/world_ip_tv)** — source
  principale, vérifiée toutes les 6h côté source (chaînes mortes retirées
  automatiquement).
- **[iptv-org (langue française)](https://iptv-org.github.io/iptv/languages/fra.m3u)**
  — source secondaire, utilisée en complément.

À partir de cette fusion, deux jeux de playlists sont générés :

- **Par pays** — une playlist par pays francophone.
- **Par catégorie** — les mêmes chaînes, mais rangées par thème (Sport,
  Musique, Actualités, Jeunesse, etc.).

Les deux versions sont **dédupliquées** : dans la source Romaxa, une même
chaîne (même flux) est souvent listée sous plusieurs pays à la fois (ex. KTO
apparaît sous France, Belgique ET Suisse). Le script ne garde qu'une seule
occurrence de chaque chaîne, en se basant sur l'URL du flux, qui est le seul
identifiant réellement fiable.

## Fusion des deux sources

Romaxa est **prioritaire** : elle est vérifiée toutes les 6h (chaînes mortes
retirées), donc en cas de doublon entre les deux sources, c'est toujours la
version Romaxa qui est conservée. Le rapprochement entre les deux sources se
fait par une clé de nom normalisée (`cle_correspondance()` dans
`filtrer_francophone.py`) qui ignore les accents, la casse, la ponctuation et
les mentions de qualité (HD, 4K...), pour repérer qu'une même chaîne est
désignée différemment d'une source à l'autre.

Les chaînes présentes **uniquement** chez iptv-org sont ajoutées en bonus aux
playlists par pays/catégorie, ET listées séparément dans
`output/bonus_iptv_org.m3u` pour audit — pratique pour vérifier rapidement ce
que la seconde source a apporté à chaque mise à jour.

**Bascule automatique** : si une des deux sources est injoignable au moment
de la génération, le script continue avec l'autre source seule (avec un
message clair dans les logs). Si les **deux** sources sont injoignables, le
script s'arrête sans rien modifier — les fichiers déjà publiés (dernière
version connue) restent en place plutôt que de publier une playlist vide.

## Comment les chaînes sont classées par catégorie

Le classement par catégorie **ne se base pas sur une simple recherche de
mots-clés** dans le nom de la chaîne. Chaque chaîne a été identifiée
individuellement (éditeur, type de contenu réel) et associée à sa catégorie
dans le dictionnaire `CHAINE_CATEGORIE` de `filtrer_francophone.py` — par
exemple `Trace Naija` → Musique (chaîne du label musical Trace), `KTO` →
Religieux (chaîne catholique française), `TSN1` → Sport, `MHZ` → Cinéma &
Séries.

Une recherche par mots-clés (`INDICES_SECOURS`) n'intervient qu'en filet de
sécurité, pour une chaîne totalement nouvelle qui n'existerait pas encore
dans le dictionnaire.

Catégories utilisées :

| Code        | Libellé                     |
|-------------|------------------------------|
| `info`      | Actualités & Info             |
| `sport`     | Sport                         |
| `cine`      | Cinéma & Séries                |
| `divert`    | Divertissement                 |
| `jeunesse`  | Jeunesse                       |
| `musique`   | Musique                        |
| `doc`       | Documentaire & Découverte      |
| `religion`  | Religieux & Spiritualité       |
| `lifestyle` | Lifestyle & Mode                |
| `diaspora`  | Communautaire & Diaspora        |
| `regional`  | Régional & Locale               |
| `general`   | Généraliste                    |

## Structure du dépôt

```
.
├── app.py                    # Serveur Flask qui sert les playlists
├── filtrer_francophone.py    # Script de génération des playlists
├── output/                   # Playlists générées (par le workflow ou en local)
│   ├── francophone.m3u                    # Toutes les chaînes, group-title = pays
│   ├── toutes_categories.m3u              # Toutes les chaînes, group-title = catégorie
│   ├── bonus_iptv_org.m3u                 # Audit : chaînes ajoutées par iptv-org uniquement
│   ├── par_pays/
│   │   ├── France.m3u
│   │   ├── Cameroon.m3u
│   │   └── ...
│   └── par_categorie/
│       ├── Sport.m3u
│       ├── Musique.m3u
│       └── ...
└── .github/workflows/update.yml   # Regénère les playlists toutes les 6h + GitHub Pages
```

## Utilisation en local

```bash
pip install flask requests
python filtrer_francophone.py   # génère les fichiers dans output/
python app.py                   # démarre le serveur sur http://localhost:5000
```

Expose ensuite ton serveur (ex. avec `ngrok http 5000`) et colle l'URL dans
ton application IPTV.

### Endpoints du serveur Flask

| Endpoint                              | Description                                   |
|----------------------------------------|------------------------------------------------|
| `/francophone.m3u`                     | Toutes les chaînes, classées par pays          |
| `/toutes_categories.m3u`               | Toutes les chaînes, classées par catégorie     |
| `/pays/<Pays>.m3u`                     | Chaînes d'un seul pays (ex. `/pays/France.m3u`) |
| `/categorie/<Categorie>.m3u`           | Chaînes d'une seule catégorie (ex. `/categorie/Sport.m3u`) |
| `/refresh`                             | Force le re-téléchargement de la source        |
| `/`                                    | Page d'accueil avec tous les liens disponibles |

Les noms de fichiers utilisent des tirets bas à la place des espaces et sont
débarrassés des accents/apostrophes (ex. `Ivory_Coast.m3u`,
`Actualites-Info.m3u`) — la page d'accueil (`/`) liste tous les liens exacts,
pas besoin de les deviner.

## Automatisation (GitHub Actions + Pages)

Le workflow `.github/workflows/update.yml` :

1. Tourne toutes les 6 heures (et peut être lancé manuellement).
2. Exécute `filtrer_francophone.py` pour régénérer tous les fichiers dans
   `output/`.
3. Commit et pousse les fichiers mis à jour (`output/francophone.m3u`,
   `output/toutes_categories.m3u`, `output/par_pays/`,
   `output/par_categorie/`).
4. Publie le contenu de `output/` sur GitHub Pages, ce qui permet d'utiliser
   des URLs stables comme :
   `https://<utilisateur>.github.io/<depot>/francophone.m3u`
   `https://<utilisateur>.github.io/<depot>/par_pays/France.m3u`
   `https://<utilisateur>.github.io/<depot>/par_categorie/Sport.m3u`

Pour activer GitHub Pages : Settings → Pages → Source = "GitHub Actions".

## Modifier ou corriger une catégorie

Si une chaîne te semble mal classée, ouvre `filtrer_francophone.py` et
modifie sa ligne dans le dictionnaire `CHAINE_CATEGORIE` (recherche le nom
de la chaîne, sans la résolution `(720p)` ni les tags `[Not 24/7]`).
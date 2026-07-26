"""
Serveur Flask qui expose les flux M3U filtrés (chaînes francophones)
------------------------------------------------------------------------------
Usage local :
    pip install flask requests
    python app.py
    # puis dans un autre terminal :
    ngrok http 5000
    # colle l'URL ngrok + "/francophone.m3u" (ou /pays/... ou /categorie/...)
    # dans ton appli IPTV
"""

import traceback
from flask import Flask, Response, abort
from filtrer_francophone import (
    URL_ROMAXA,
    CATEGORIES,
    telecharger_m3u,
    extraire_chaines,
    dedupliquer,
    categoriser_chaine,
    nom_fichier_valide,
)

app = Flask(__name__)

# Cache en mémoire : chaines brutes (avec doublons inter-pays), et
# la version dédupliquée globalement (utilisée pour les catégories et le
# flux "toutes chaines")
_cache = {
    "chaines": None,          # liste de dicts {pays, nom, logo, url} - par pays
    "chaines_uniques": None,  # dédupliquées par URL - pour catégories
    "erreur": None,
}


def rafraichir(force_refresh: bool = False) -> None:
    """Télécharge + extrait, stocke le résultat (ou l'erreur) dans _cache.
    Ne relance JAMAIS d'exception : toute erreur est capturée et loggée
    clairement dans le terminal."""
    if _cache["chaines"] is not None and not force_refresh:
        return

    try:
        print("[refresh] Téléchargement du M3U source...")
        lignes = telecharger_m3u(URL_ROMAXA)
        print(f"[refresh] {len(lignes)} lignes reçues, extraction en cours...")
        chaines = extraire_chaines(lignes)
        _cache["chaines"] = chaines
        _cache["chaines_uniques"] = dedupliquer(chaines)
        _cache["erreur"] = None
        print(
            f"[refresh] OK -> {len(chaines)} entrées, "
            f"{len(_cache['chaines_uniques'])} chaînes uniques"
        )
    except Exception as e:
        _cache["erreur"] = str(e)
        print("[refresh] ❌ ERREUR pendant la génération de la playlist :")
        traceback.print_exc()


def _m3u_texte(chaines, group_title_fn) -> str:
    lignes = ["#EXTM3U\n"]
    for c in chaines:
        lignes.append(
            f'#EXTINF:-1 tvg-logo="{c["logo"]}" '
            f'group-title="{group_title_fn(c)}",{c["nom"]}\n'
        )
        lignes.append(c["url"] + "\n")
    return "".join(lignes)


def _reponse_erreur():
    return Response(
        f"#EXTM3U\n# ERREUR: {_cache['erreur']}\n",
        mimetype="audio/x-mpegurl",
        status=503,
    )


@app.route("/francophone.m3u")
def francophone_m3u():
    """Toutes les chaînes francophones, dédupliquées, group-title = pays."""
    if _cache["chaines_uniques"] is None:
        rafraichir()
    if _cache["chaines_uniques"] is None:
        return _reponse_erreur()
    texte = _m3u_texte(_cache["chaines_uniques"], lambda c: c["pays"])
    return Response(texte, mimetype="audio/x-mpegurl")


@app.route("/pays/<nom_pays>.m3u")
def pays_m3u(nom_pays):
    """Playlist d'un seul pays (dédupliquée), ex: /pays/France.m3u"""
    if _cache["chaines"] is None:
        rafraichir()
    if _cache["chaines"] is None:
        return _reponse_erreur()

    correspondances = [
        c for c in _cache["chaines"]
        if nom_fichier_valide(c["pays"]) == nom_pays
    ]
    if not correspondances:
        abort(404, description=f"Pays inconnu ou sans chaîne : {nom_pays}")

    correspondances = dedupliquer(correspondances)
    texte = _m3u_texte(correspondances, lambda c: c["pays"])
    return Response(texte, mimetype="audio/x-mpegurl")


@app.route("/categorie/<nom_categorie>.m3u")
def categorie_m3u(nom_categorie):
    """Playlist d'une seule catégorie (dédupliquée globalement),
    ex: /categorie/Sport.m3u"""
    if _cache["chaines_uniques"] is None:
        rafraichir()
    if _cache["chaines_uniques"] is None:
        return _reponse_erreur()

    correspondances = [
        c for c in _cache["chaines_uniques"]
        if nom_fichier_valide(CATEGORIES[categoriser_chaine(c["nom"])]) == nom_categorie
    ]
    if not correspondances:
        abort(404, description=f"Catégorie inconnue ou sans chaîne : {nom_categorie}")

    correspondances = sorted(correspondances, key=lambda c: c["nom"].lower())
    texte = _m3u_texte(correspondances, lambda c: nom_categorie)
    return Response(texte, mimetype="audio/x-mpegurl")


@app.route("/toutes_categories.m3u")
def toutes_categories_m3u():
    """Toutes les chaînes, dédupliquées, group-title = catégorie."""
    if _cache["chaines_uniques"] is None:
        rafraichir()
    if _cache["chaines_uniques"] is None:
        return _reponse_erreur()

    def libelle(c):
        return CATEGORIES[categoriser_chaine(c["nom"])]

    triees = sorted(_cache["chaines_uniques"], key=lambda c: (libelle(c), c["nom"].lower()))
    texte = _m3u_texte(triees, libelle)
    return Response(texte, mimetype="audio/x-mpegurl")


@app.route("/refresh")
def refresh():
    rafraichir(force_refresh=True)
    if _cache["erreur"]:
        return {"status": "erreur", "detail": _cache["erreur"]}, 500
    return {"status": "ok"}


@app.route("/")
def index():
    if _cache["erreur"]:
        etat = f"erreur: {_cache['erreur']}"
    elif _cache["chaines_uniques"]:
        etat = f"prête ({len(_cache['chaines_uniques'])} chaînes uniques)"
    else:
        etat = "non générée"

    liens_pays = ""
    liens_categorie = ""
    if _cache["chaines"]:
        pays_tries = sorted({c["pays"] for c in _cache["chaines"]})
        liens_pays = "<br>".join(
            f'<a href="/pays/{nom_fichier_valide(p)}.m3u">{p}</a>' for p in pays_tries
        )
    if _cache["chaines_uniques"]:
        cats_triees = sorted(set(CATEGORIES.values()))
        liens_categorie = "<br>".join(
            f'<a href="/categorie/{nom_fichier_valide(c)}.m3u">{c}</a>' for c in cats_triees
        )

    return (
        f"Serveur M3U francophone actif. Playlist : {etat}<br>"
        "Toutes les chaînes (par pays) : <a href='/francophone.m3u'>/francophone.m3u</a><br>"
        "Toutes les chaînes (par catégorie) : "
        "<a href='/toutes_categories.m3u'>/toutes_categories.m3u</a><br>"
        "Forcer la mise à jour : <a href='/refresh'>/refresh</a><br><br>"
        f"<b>Par pays :</b><br>{liens_pays}<br><br>"
        f"<b>Par catégorie :</b><br>{liens_categorie}"
    )


if __name__ == "__main__":
    # On génère la playlist AU DEMARRAGE, pas à la première requête.
    # Si ça plante, tu le vois tout de suite dans ce terminal, avant
    # même de tester depuis l'appli IPTV.
    print("=== Génération initiale de la playlist francophone ===")
    rafraichir()
    print("=== Démarrage du serveur Flask ===")
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
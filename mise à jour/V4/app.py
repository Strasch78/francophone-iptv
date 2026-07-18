"""
Serveur Flask qui expose un flux M3U filtré (chaînes francophones uniquement)
------------------------------------------------------------------------------
Usage local :
    pip install flask requests
    python app.py
    # puis dans un autre terminal :
    ngrok http 5000
    # colle l'URL ngrok + "/francophone.m3u" dans ton appli IPTV
"""

import traceback
from flask import Flask, Response
from filtrer_francophone import (
    URL_ROMAXA,
    telecharger_m3u,
    filtrer_francophone,
)

app = Flask(__name__)

_cache = {"contenu": None, "erreur": None}


def generer_playlist(force_refresh: bool = False) -> None:
    """Télécharge + filtre, stocke le résultat (ou l'erreur) dans _cache.
    Ne relance JAMAIS d'exception : toute erreur est capturée et loggée
    clairement dans le terminal."""
    if _cache["contenu"] is not None and not force_refresh:
        return

    try:
        print("[refresh] Téléchargement du M3U source...")
        lignes = telecharger_m3u(URL_ROMAXA)
        print(f"[refresh] {len(lignes)} lignes reçues, filtrage en cours...")
        playlist, pays_retenus, compteur = filtrer_francophone(lignes)
        _cache["contenu"] = "".join(playlist)
        _cache["erreur"] = None
        print(f"[refresh] OK -> {compteur} chaînes, {len(pays_retenus)} pays")
    except Exception as e:
        _cache["erreur"] = str(e)
        print("[refresh] ❌ ERREUR pendant la génération de la playlist :")
        traceback.print_exc()


@app.route("/francophone.m3u")
def francophone_m3u():
    if _cache["contenu"] is None:
        generer_playlist()

    if _cache["contenu"] is None:
        # Toujours rien après tentative -> on renvoie un message clair
        # au lieu de laisser Flask planter avec un 500 muet.
        return Response(
            f"#EXTM3U\n# ERREUR: {_cache['erreur']}\n",
            mimetype="audio/x-mpegurl",
            status=503,
        )

    return Response(_cache["contenu"], mimetype="audio/x-mpegurl")


@app.route("/refresh")
def refresh():
    generer_playlist(force_refresh=True)
    if _cache["erreur"]:
        return {"status": "erreur", "detail": _cache["erreur"]}, 500
    return {"status": "ok"}


@app.route("/")
def index():
    etat = "prête" if _cache["contenu"] else f"erreur: {_cache['erreur']}"
    return (
        f"Serveur M3U francophone actif. Playlist : {etat}<br>"
        "Playlist : <a href='/francophone.m3u'>/francophone.m3u</a><br>"
        "Forcer la mise à jour : <a href='/refresh'>/refresh</a>"
    )


if __name__ == "__main__":
    # On génère la playlist AU DEMARRAGE, pas à la première requête.
    # Si ça plante, tu le vois tout de suite dans ce terminal, avant
    # même de tester depuis l'appli IPTV.
    print("=== Génération initiale de la playlist francophone ===")
    generer_playlist()
    print("=== Démarrage du serveur Flask ===")
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)

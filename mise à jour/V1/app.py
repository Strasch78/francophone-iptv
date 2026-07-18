"""
Serveur Flask qui expose un flux M3U filtré (chaînes francophones uniquement)
------------------------------------------------------------------------------
Usage local :
    pip install flask requests
    python app.py
    # puis dans un autre terminal :
    ngrok http 5000
    # colle l'URL ngrok + "/francophone.m3u" dans ton appli IPTV

Le filtrage est refait à la demande (ou tu peux ajouter un cache si tu veux
limiter les appels au dépôt source).
"""

from flask import Flask, Response
from filtrer_francophone import (
    URL_ROMAXA,
    telecharger_m3u,
    filtrer_francophone,
)

app = Flask(__name__)

# --- cache simple en mémoire (évite de retélécharger à chaque requête) ---
_cache = {"contenu": None}


def generer_playlist(force_refresh: bool = False) -> str:
    if _cache["contenu"] is not None and not force_refresh:
        return _cache["contenu"]

    lignes = telecharger_m3u(URL_ROMAXA)
    playlist, pays_retenus, compteur = filtrer_francophone(lignes)
    contenu = "".join(playlist)

    _cache["contenu"] = contenu
    print(f"[refresh] {compteur} chaînes, pays: {sorted(pays_retenus)}")
    return contenu


@app.route("/francophone.m3u")
def francophone_m3u():
    contenu = generer_playlist()
    return Response(contenu, mimetype="audio/x-mpegurl")


@app.route("/refresh")
def refresh():
    """Force le re-téléchargement + re-filtrage (appelle-le manuellement
    ou programme un cron qui tape cette route toutes les X heures)."""
    generer_playlist(force_refresh=True)
    return {"status": "ok"}


@app.route("/")
def index():
    return (
        "Serveur M3U francophone actif.<br>"
        "Playlist : <a href='/francophone.m3u'>/francophone.m3u</a><br>"
        "Forcer la mise à jour : <a href='/refresh'>/refresh</a>"
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

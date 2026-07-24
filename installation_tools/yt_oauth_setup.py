#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ottiene il refresh token OAuth necessario a zeroCam per gestire la
diretta YouTube (creazione automatica del broadcast).

Va eseguito UNA VOLTA SOLA, su una macchina con un browser (anche il
proprio PC: serve solo Python + requests, non la camera). Il refresh
token stampato va incollato nella pagina di configurazione di zeroCam.

Prerequisiti sulla Google Cloud Console:
  1. crea un progetto e abilita "YouTube Data API v3"
  2. configura la schermata di consenso OAuth (tipo "Esterno" va bene);
     aggiungi il tuo account come utente di test
  3. crea credenziali OAuth di tipo "Applicazione desktop"
  4. annota Client ID e Client Secret

Uso:
    python3 yt_oauth_setup.py
"""

import http.server
import json
import socket
import sys
import threading
import urllib.parse
import webbrowser

try:
    import requests
except ImportError:
    sys.exit("Modulo 'requests' mancante. Installalo con: pip install requests")

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/youtube"
PORT = 8765
REDIRECT_URI = f"http://localhost:{PORT}/"

PAGE_OK = b"""<html><body style="font-family:sans-serif;padding:2rem">
<h2>Autorizzazione completata</h2>
<p>Puoi chiudere questa scheda e tornare al terminale.</p>
</body></html>"""

PAGE_KO = b"""<html><body style="font-family:sans-serif;padding:2rem">
<h2>Autorizzazione fallita</h2>
<p>Controlla il terminale per i dettagli.</p>
</body></html>"""


done = threading.Event()


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Riceve il redirect di Google e memorizza il code."""

    code = None
    error = None

    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)

        code = params.get("code", [None])[0]
        error = params.get("error", [None])[0]

        # Il browser chiede anche /favicon.ico subito dopo il redirect:
        # va ignorata, altrimenti sovrascriverebbe il code appena ricevuto.
        if not code and not error:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        CallbackHandler.code = code
        CallbackHandler.error = error

        body = PAGE_OK if code else PAGE_KO
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        done.set()

    def log_message(self, *args):
        pass  # silenzia il log di default di BaseHTTPRequestHandler


def port_is_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def main():
    print("=== zeroCam - setup OAuth YouTube Live ===\n")

    client_id = input("Client ID: ").strip()
    client_secret = input("Client Secret: ").strip()
    if not client_id or not client_secret:
        sys.exit("Client ID e Client Secret sono obbligatori.")

    if not port_is_free(PORT):
        sys.exit(f"La porta {PORT} e' occupata. Chiudi il processo che la usa e riprova.")

    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        # offline + consent garantiscono che Google restituisca il refresh token
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    print("\nApri questo indirizzo nel browser (se non si apre da solo):\n")
    print(auth_url + "\n")

    server = http.server.HTTPServer(("127.0.0.1", PORT), CallbackHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    print("In attesa dell'autorizzazione...")
    try:
        done.wait()
    except KeyboardInterrupt:
        sys.exit("\nAnnullato.")
    finally:
        server.shutdown()

    if CallbackHandler.error:
        sys.exit(f"Autorizzazione rifiutata: {CallbackHandler.error}")

    print("Codice ricevuto, richiedo i token...")
    r = requests.post(TOKEN_URL, data={
        "code": CallbackHandler.code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }, timeout=30)

    if r.status_code != 200:
        sys.exit(f"Scambio del codice fallito ({r.status_code}): {r.text}")

    payload = r.json()
    refresh_token = payload.get("refresh_token")
    if not refresh_token:
        sys.exit(
            "Google non ha restituito un refresh token.\n"
            "Revoca l'accesso dell'app da https://myaccount.google.com/permissions "
            "e riesegui lo script."
        )

    print("\n=== Valori da inserire in zeroCam (Config -> YouTube Live) ===\n")
    print(json.dumps({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }, indent=2))
    print("\nConserva il refresh token: e' una credenziale permanente.")


if __name__ == "__main__":
    main()

"""Parcours J3 de bout en bout, contre l'API **reelle** et le jeu de demonstration complet.

A lancer avec l'API demarree (`uv run uvicorn apex.main:app --port 8001`) et une base
seedee. Ce n'est pas un test unitaire et il n'a pas sa place dans `pytest` : il touche la
base de developpement, il depend d'un serveur, et c'est precisement ce qui fait sa valeur.

Les tests fabriquent chacun leurs medias — avec un fichier haute definition. Ce script,
lui, joue sur les donnees que la demonstration utilisera vraiment : c'est ainsi qu'il a
trouve que le generateur de demo ne posait aucun `storage_key_hd`, donc qu'aucune
collection du jeu n'etait livrable. Aucun test unitaire ne pouvait voir ce trou.

Usage :
    python scripts/verify_j3_flow.py

Studio : se connecter, composer une collection, la publier, creer un lien de partage.
Client : ouvrir le lien, voir ses photos, en choisir, commenter, valider.
Studio : drainer la file, verifier la livraison et la facture, emettre.
Client : telecharger l'archive et verifier qu'elle est un vrai ZIP.
"""

import io
import json
import sys
import urllib.error
import urllib.request
import zipfile

BASE = "http://localhost:8001/api/v1"
OK = []
KO = []


def call(method, path, token=None, body=None, raw=False, extra_headers=None):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    headers.update(extra_headers or {})
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request) as response:
            payload = response.read()
            if raw:
                return response.status, payload
            return response.status, (json.loads(payload) if payload else None)
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        try:
            return exc.code, json.loads(payload)
        except Exception:
            return exc.code, payload


def check(label, condition, detail=""):
    (OK if condition else KO).append(label)
    mark = "OK  " if condition else "ECHEC"
    print(f"  {mark} {label}{(' — ' + str(detail)) if detail and not condition else ''}")


print("== Studio ==")
status, body = call(
    "POST",
    "/auth/login",
    body={"email": "dirigeant@studio-chicane.dev", "password": "changeme-owner"},
)
check("connexion dirigeant", status == 200, body)
owner = body["access_token"]

status, media_page = call("GET", "/search?limit=8&status=engagement_attached", token=owner)
check("recherche de medias rattaches", status == 200 and media_page["items"], media_page)
media_ids = [item["id"] for item in media_page["items"][:6]]
client_id = None
for item in media_page["items"]:
    if item.get("client_id"):
        client_id = item["client_id"]
        break
if client_id is None:
    status, clients = call("GET", "/clients?limit=1", token=owner)
    client_id = clients["items"][0]["id"]

status, collection = call(
    "POST",
    "/collections",
    token=owner,
    body={"client_id": client_id, "title": "Parcours J3 — verification"},
)
check("creation de collection", status == 201, collection)
collection_id = collection["id"]

status, added = call(
    "POST", f"/collections/{collection_id}/items", token=owner, body={"media_ids": media_ids}
)
check("ajout de medias", status in (200, 201), added)

status, published = call("POST", f"/collections/{collection_id}/publish", token=owner)
check("publication", status == 200 and published["status"] == "published", published)

status, link = call(
    "POST", f"/collections/{collection_id}/share-links", token=owner, body={"expires_in_days": 7}
)
check("creation du lien de partage", status == 201, link)
token_clair = link["token"]
check("le lien contient le jeton", token_clair in link["url"])

status, links = call("GET", f"/collections/{collection_id}/share-links", token=owner)
check(
    "le jeton n'apparait jamais dans la liste",
    status == 200 and all(token_clair not in entry["url_masked"] for entry in links),
    links,
)

print("== Client ==")
status, session = call("POST", "/public/session", body={"token": token_clair})
check("ouverture de session client", status == 200, session)
client_token = session["access_token"]
check(
    "la collection est decrite au client",
    session["collection"]["item_count"] == len(media_ids),
    session["collection"],
)

status, gallery = call("GET", "/public/collection", token=client_token)
check("galerie visible", status == 200 and len(gallery["items"]) == len(media_ids), gallery)

status, thumb = call(
    "GET", f"/public/media/{media_ids[0]}/file/thumb", token=client_token, raw=True
)
check("vignette filigranee servie", status == 200 and thumb[:4] == b"RIFF", status)

status, forbidden = call("GET", "/public/media/999999/file/preview", token=client_token)
check("media hors perimetre introuvable", status == 404, status)

chosen = media_ids[:3]
for index, media_id in enumerate(chosen):
    status, _ = call(
        "PUT",
        f"/public/selection/items/{media_id}",
        token=client_token,
        body={"comment": "celle-ci" if index == 0 else None},
    )
    check(f"selection du media {media_id}", status == 200, status)

status, selection = call("GET", "/public/selection", token=client_token)
check("sélection relue", status == 200 and selection["count"] == len(chosen), selection)

status, archive_refusee = call("GET", "/public/delivery/archive", token=client_token)
check("le HD ne sort pas avant validation", status == 403, status)

status, validated = call("POST", "/public/selection/validate", token=client_token)
check("validation", status == 200 and validated["status"] == "validated", validated)

status, locked = call("PUT", f"/public/selection/items/{media_ids[4]}", token=client_token, body={})
check("la selection validee est figee", status == 409, status)

print("== Worker ==")
status, tick = call("POST", "/jobs/tick", extra_headers={"X-Worker-Secret": "dev-worker-secret"})
check("drainage de la file", status == 200, tick)
print(
    f"       claimed={tick.get('claimed')} done={tick.get('done')} "
    f"failed={tick.get('failed')} deferred={tick.get('deferred')}"
)

status, delivery = call("GET", "/public/delivery", token=client_token)
check("livraison prete", status == 200 and delivery["ready"] is True, delivery)
check("le nombre de photos livrees correspond", delivery["item_count"] == len(chosen), delivery)

status, archive = call("GET", "/public/delivery/archive", token=client_token, raw=True)
check("archive telechargeable", status == 200, status)
if status == 200:
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        names = zf.namelist()
        check(
            "archive lisible et complete", zf.testzip() is None and len(names) == len(chosen), names
        )
        check("noms d'entree tries", names == sorted(names), names)

print("== Facturation ==")
status, invoices = call("GET", "/invoices", token=owner)
check("facture brouillon creee", status == 200 and invoices["items"], invoices)
invoice = invoices["items"][0]
check(
    "la facture porte les photos choisies",
    invoice["lines"] and invoice["lines"][0]["quantity"] == len(chosen),
    invoice,
)
check("une facture brouillon n'a pas de numero", invoice["number"] is None, invoice)

status, issued = call("POST", f"/invoices/{invoice['id']}/issue", token=owner)
check("emission", status == 200 and issued["number"], issued)

status, refused = call("PATCH", f"/invoices/{invoice['id']}", token=owner, body={"vat_rate": 0.1})
check(
    "une facture emise refuse toute modification",
    status == 409 and refused.get("code") == "invoice_issued",
    refused,
)

print("== Revocation ==")
status, _ = call("DELETE", f"/share-links/{link['id']}", token=owner)
check("revocation du lien", status == 204, status)
status, after = call("GET", "/public/collection", token=client_token)
check(
    "la session client est coupee immediatement",
    status == 410 and after.get("code") == "link_expired",
    after,
)

print("== Tableau de bord ==")
status, dashboard = call("GET", "/dashboard", token=owner)
check("tableau de bord", status == 200, dashboard)
if status == 200:
    print(
        f"       CA={dashboard['revenue_cents']} centimes · "
        f"shootings={dashboard['shootings_done']}/{dashboard['shootings_upcoming']} · "
        f"medias={dashboard['media_ingested']} · taux={dashboard['auto_attach_rate']}"
    )

print()
print(f"{len(OK)} verifications passees, {len(KO)} en echec")
if KO:
    for label in KO:
        print(f"  - {label}")
    sys.exit(1)

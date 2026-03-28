# Deploying on unRAID

## Step 1 — Copy files to your unRAID share

Copy the entire `role_evaluation` folder to a share on your unRAID server.
A good spot is `/mnt/user/appdata/role-evaluation/`.

You can do this from your Mac:
```
# In Finder: Go → Connect to Server → smb://your-unraid-ip
# Then drag the role_evaluation folder into appdata
```

Or via Terminal:
```bash
scp -r ~/Desktop/Cowork/role_evaluation root@your-unraid-ip:/mnt/user/appdata/role-evaluation
```

---

## Step 2 — Build the Docker image on unRAID

SSH into your unRAID server, then:
```bash
cd /mnt/user/appdata/role-evaluation
docker build -t role-evaluation:latest .
```

This takes ~60 seconds the first time (downloading Python base image).

---

## Step 3 — Add the container in unRAID

In the unRAID web UI:

1. Go to **Docker** tab → **Add Container**
2. Fill in:

| Field | Value |
|-------|-------|
| Name | `role-evaluation` |
| Repository | `role-evaluation:latest` |
| Network Type | `bridge` |
| Port Mapping — Host Port | `7860` |
| Port Mapping — Container Port | `7860` |

3. Click **Apply**

---

## Step 4 — Use it

**Browser UI:**
```
http://your-unraid-ip:7860
```

**JSON API (for DealEval):**
```
GET http://your-unraid-ip:7860/api/lookup?municipality=saint-sauveur&query=125+chemin+des+Coureurs
```

Returns:
```json
{
  "matricule": "5283-91-2643",
  "matricule_complet": "5283-91-2643-0-000-0000",
  "lot": "2313704",
  "registre_foncier_url": "https://www.registrefoncier.gouv.qc.ca/..."
}
```

---

## Updating the code later

If you edit `role_eval.py` (e.g. to add a new municipality):

```bash
# SSH into unRAID
cd /mnt/user/appdata/role-evaluation
docker build -t role-evaluation:latest .
docker restart role-evaluation
```

---

## Auto-start on unRAID boot

In the Docker container settings, set **Autostart** to `Yes`.
unRAID will start the container automatically whenever the array comes online.

---

## Tip — Prettier local URL

If you have a reverse proxy (Nginx Proxy Manager, Swag, etc.) on unRAID,
you can give it a friendly local domain like `http://role-eval.local`
instead of using the IP and port directly.

# Deploy this Git repo on Railway

The ERPNext v16 template is a *different* image. This folder deploys **this repository** (ERPNext 17 develop) as `erpnext-docker`.

## 1. Push these files

```bash
git add Dockerfile .dockerignore railway.toml docker/railway
git commit -m "Add Railway deploy for this ERPNext repo"
git push origin develop
```

## 2. Point only the app service at this repo

In the Railway project you already created from the template:

1. Click **`erpnext-docker`** (leave `mariadb`, `redis-cache`, `redis-queue` as they are).
2. **Settings → Source**.
3. Disconnect `thspacecode/erpnext-docker` if it is still connected.
4. **Connect GitHub** → `miraj-sarkar/erpnext` → branch **`develop`**.
5. Root directory: **repo root** (empty / `.`).
6. Dockerfile path: **`Dockerfile`**.
7. **Start command: empty**.
8. **Networking:** generate a public domain if missing. Port **80**.
9. **Volume** still mounted at `/home/frappe/frappe-bench/sites`.

## 3. Keep these variables on `erpnext-docker`

They should already exist from the template. Do not delete them.

| Variable | Value |
|---|---|
| `FRAPPE_DB_HOST` | `${{mariadb.RAILWAY_PRIVATE_DOMAIN}}` |
| `FRAPPE_DB_PASSWORD` | `${{mariadb.MARIADB_ROOT_PASSWORD}}` |
| `FRAPPE_REDIS_CACHE` | `redis://${{redis-cache.RAILWAY_PRIVATE_DOMAIN}}:6379` |
| `FRAPPE_REDIS_QUEUE` | `redis://${{redis-queue.RAILWAY_PRIVATE_DOMAIN}}:6379` |
| `RFP_SITE_ADMIN_PASSWORD` | generated secret |
| `RAILWAY_HEALTHCHECK_TIMEOUT_SEC` | `900` |

`RFP_DOMAIN_NAME` is optional now. The site is always named `frontend`, so the Railway URL can change without recreating the site.

Give **`erpnext-docker` 8 GB RAM**. First build from this Git repo is 15–25 minutes.

## 4. Log in

Open the **`erpnext-docker`** public URL.

- Email: `Administrator`
- Password: `RFP_SITE_ADMIN_PASSWORD`

Complete the Welcome wizard.

After a successful first boot you can remove `RAILWAY_HEALTHCHECK_TIMEOUT_SEC`.

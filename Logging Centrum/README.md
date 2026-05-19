# Logging Centrum (Simplified)

## Wat dit doet
- Ontvangt logs via `POST /api/log`
- Slaat logs op in `Database/logs.xlsx`
- Biedt simpele zoekpagina via `GET /search`

## Docker starten
Vanuit `Logging Centrum`:

```powershell
docker compose up -d --build
```

Stoppen:

```powershell
docker compose down
```

Of gebruik:
- `docker-start.bat`
- `docker-stop.bat`

## API voorbeeld

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:5001/api/log" -ContentType "application/json" -Body '{"what":"Ping uitgevoerd","module":"Server","where":"/api/ping"}'
```

Zoekpagina:
- `http://localhost:5001/search`

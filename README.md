# AcarreApp

AcarreApp is a Django application for route, service, cash, receivables and browser push notification management.

## Local setup on Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open `http://127.0.0.1:8000/`.

## Push notifications

Generate VAPID keys outside the repository and put them in `.env`.
Do not commit real private keys. Browser push requires HTTPS in production; localhost is accepted by modern browsers for development.

## Project shape

The canonical Django project is the repository root:

- `manage.py`
- `acarreapp/`
- `empresa/`
- `usuarios/`
- `rutas/`
- `servicios/`
- `cartera/`
- `dashboard/`
- `notificaciones/`
- `templates/`
- `static/`

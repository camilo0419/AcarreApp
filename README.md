# AcarreApp – Skeleton v1

## Requisitos
- Python 3.12
- pip

## Instalación rápida (Windows PowerShell)
```powershell
cd AcarreApp_skeleton_v1
copy .env.example .env
py -3.12 -m venv .venv
.\.venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Abre http://127.0.0.1:8000 y entra a /admin para crear tu primera Empresa.

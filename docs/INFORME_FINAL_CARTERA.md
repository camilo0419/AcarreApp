# Informe final - Modulo de cartera AcarreApp

Fecha de cierre: 2026-07-14

## Alcance implementado

Se formalizo el modulo de cartera como parte nativa de AcarreApp, sin acoplarlo a CarterApp ni a repositorios externos. La ruta principal del modulo queda en `/cartera/` y el menu de gerencia ahora incluye acceso directo a Cartera.

## Decisiones de arquitectura

- `PagoServicio` es la fuente formal de pagos, historial y anulaciones.
- `Servicio.anticipo` se conserva como total pagado sincronizado para no romper cierres, listados y calculos existentes.
- Los anticipos historicos se migran a pagos legacy con `impacta_caja=False`, evitando duplicar caja.
- Los pagos de rutas activas crean `MovimientoCaja` de tipo `INGRESO` y quedan enlazados al pago.
- Los pagos de rutas cerradas actualizan cartera, pero no modifican caja ni `CierreRuta`, para no desbalancear cierres ya emitidos.
- Las anulaciones de pagos con caja solo se permiten si la ruta sigue activa; generan un movimiento de reversion tipo `GASTO`.
- La cuenta de cobro es 1:1 por servicio y conserva un consecutivo estable por empresa.

## Modelos nuevos

- `CarteraEmpresaConfig`: datos del emisor, logo estatico, notas PDF, prefijo y proximo consecutivo por empresa.
- `PagoServicio`: pago auditable por servicio, cliente, ruta y empresa, con medio, referencia, usuario, caja y anulacion.
- `CuentaCobro`: consecutivo y numero estable por empresa/servicio.

## Rutas principales

- `/cartera/`: dashboard de cartera.
- `/cartera/clientes/`: clientes con saldo.
- `/cartera/clientes/<id>/`: detalle de cartera por cliente.
- `/cartera/servicios/`: servicios pendientes filtrables.
- `/cartera/servicios/<id>/pagar/`: registro formal de pagos.
- `/cartera/pagos/`: historial y anulaciones.
- `/cartera/configuracion/`: configuracion por empresa.
- `/cartera/clientes/<id>/estado-cuenta.pdf`: estado de cuenta PDF.
- `/cartera/servicios/<id>/cuenta-cobro.pdf`: cuenta de cobro PDF.

Se conservaron aliases antiguos:

- `/cartera/pendientes/`
- `/cartera/cliente/<id>/`

## Seguridad y multiempresa

- Todas las vistas de cartera requieren usuario autenticado con rol `GERENTE`, staff o superuser.
- Conductores reciben 403 en el modulo de cartera.
- Todas las consultas filtran por `get_current_empresa()`.
- Los pagos validan empresa, servicio, cliente y ruta en backend.
- Los pagos y anulaciones mutan solo por POST o por formularios POST; las descargas PDF y vistas GET no modifican saldos, salvo la emision idempotente de cuenta de cobro.

## PDFs

Se implementaron PDFs con WeasyPrint:

- Estado de cuenta por cliente.
- Cuenta de cobro por servicio.

El logo se toma desde `CarteraEmpresaConfig.logo_static_path`, por defecto `static/icons/Logo.png`, y se renderiza con dimensiones fijas y `object-fit: contain` para evitar deformacion.

Se genero y reviso visualmente una muestra de cada PDF:

- `tmp/pdfs/estado_cuenta_muestra.pdf`
- `tmp/pdfs/cuenta_cobro_muestra.pdf`
- PNGs renderizados en `tmp/pdfs/rendered/`

Resultado visual: una pagina Letter por PDF, tablas legibles, logo sin deformacion, encabezados y pies alineados.

## Dependencias

Se agregaron `WeasyPrint>=62.3` y `brotlicffi>=1.2.0.1` a `requirements.txt`.

Para validar localmente se instalo WeasyPrint 69.0 en `.venv`. En OneDrive aparecio un problema de permisos con `brotli.py`; se resolvio usando `brotlicffi` y ejecutando validaciones con `PYTHONDONTWRITEBYTECODE=1`.

## Pruebas agregadas

Archivo: `cartera/tests.py`

Cobertura incluida:

- Acceso gerente vs conductor.
- Aislamiento multiempresa en dashboard.
- Pago parcial con historial y movimiento de caja.
- Rechazo de sobrepago sin mutar saldos.
- Pago posterior a cierre sin tocar caja ni `CierreRuta`.
- Endpoints mutantes sin GET.
- Consecutivo idempotente de cuenta de cobro.
- PDFs reales con bytes `%PDF`.

## Validaciones ejecutadas

- `manage.py migrate`: OK.
- `manage.py check`: OK.
- `manage.py makemigrations --check --dry-run`: OK, sin cambios.
- `manage.py collectstatic --noinput --dry-run`: OK.
- `manage.py test cartera -v 2`: 6 tests OK.
- `manage.py test -v 2`: 16 tests OK.
- `manage.py check --deploy`: 6 warnings esperadas de entorno local (`DEBUG`, HTTPS/cookies seguras, `SECRET_KEY`), no atribuibles al modulo de cartera.

## Archivos principales tocados

- `cartera/models.py`
- `cartera/services.py`
- `cartera/views.py`
- `cartera/forms.py`
- `cartera/pdf.py`
- `cartera/admin.py`
- `cartera/urls.py`
- `cartera/migrations/0001_initial.py`
- `cartera/migrations/0002_migrar_anticipos_a_pagos.py`
- `cartera/tests.py`
- `servicios/models.py`
- `servicios/views.py`
- `templates/cartera/*`
- `templates/cartera/pdf/*`
- `templates/servicios/detail.html`
- `templates/includes/navbar.html`
- `requirements.txt`

## Estado final

Modulo de cartera integrado, migrado, probado y validado. No se hizo commit, push ni deploy.

# Informe final - Modulo de cartera AcarreApp

Fecha de cierre: 2026-07-14

## Veredicto

El modulo de cartera queda apto para primer commit local. No se hizo commit, push ni deploy.

La correccion principal de esta auditoria fue retirar la doble fuente financiera: `Servicio` ya no persiste `anticipo` ni `estado_pago`. El saldo, el total pagado y el estado se derivan exclusivamente de pagos activos en `PagoServicio`.

## Fuente de verdad financiera

- `PagoServicio` es la unica fuente persistida para pagos, anulaciones, caja asociada, total pagado, saldo y estado de cartera.
- `Servicio.total_pagado`, `Servicio.saldo_cartera`, `Servicio.estado_pago` y `Servicio.anticipo` son propiedades derivadas de lectura. `anticipo` queda solo como compatibilidad temporal y retorna el total pagado, sin campo de base de datos ni escritura manual.
- La migracion `cartera.0002_migrar_anticipos_a_pagos` migra anticipos historicos a pagos legacy con `impacta_caja=False`.
- La migracion `servicios.0009_remove_servicio_anticipo_remove_servicio_estado_pago_and_more` elimina fisicamente las columnas antiguas despues de esa migracion de datos.
- Los pagos con valor cero, negativo o superior al saldo se rechazan antes de crear historial o movimiento de caja.
- Las anulaciones no borran pagos: marcan `anulado=True` y, si hubo caja activa, generan movimiento de reversion.

## GET sin mutaciones

- La cuenta de cobro ya no se emite desde `GET /cartera/servicios/<id>/cuenta-cobro.pdf`.
- La emision vive en `POST /cartera/servicios/<id>/cuenta-cobro/emitir/`.
- El GET del PDF solo descarga una cuenta previamente emitida; si no existe, responde 404 y no incrementa consecutivo.
- Se actualizaron templates para usar formulario POST en vez de enlace directo de emision.

## PDFs

- Estado de cuenta y cuenta de cobro usan `@page { size: A4; }`.
- WeasyPrint queda fijado en `WeasyPrint==69.0`.
- PDFs de auditoria generados:
  - `tmp/pdfs/estado_cuenta_a4_audit.pdf`
  - `tmp/pdfs/cuenta_cobro_a4_audit.pdf`
- Verificacion Poppler:
  - Estado de cuenta: `595.276 x 841.89 pts (A4)`, 1 pagina.
  - Cuenta de cobro: `595.276 x 841.89 pts (A4)`, 1 pagina.
- Ambos PDFs renderizaron a PNG no vacio:
  - `tmp/pdfs/estado_cuenta_a4_audit.png`
  - `tmp/pdfs/cuenta_cobro_a4_audit.png`

## Dependencias

`requirements.txt` queda con versiones fijadas:

- `Django==5.0.7`
- `django-filter==24.2`
- `openpyxl==3.1.5`
- `psycopg[binary]==3.1.19`
- `python-dotenv==1.0.1`
- `pywebpush==1.14.0`
- `cryptography==49.0.0`
- `brotlicffi==1.2.0.1`
- `WeasyPrint==69.0`

## Auditoria operativa

Se agrego el comando read-only:

```powershell
python manage.py auditar_cartera
```

Detecta:

- servicios sobrepagados;
- pagos cruzados de empresa, ruta, cliente o servicio;
- pagos que debian impactar caja y no tienen movimiento;
- pagos con movimiento de caja inesperado;
- movimientos o reversiones con valor, tipo, empresa o ruta inconsistentes;
- pagos anulados sin reversion cuando corresponde;
- cuentas de cobro fuera del scope de empresa/cliente.

Por defecto no modifica datos y retorna 0 aunque reporte hallazgos. Para CI existe `--fail-on-issues`.

Resultado local ejecutado: 0 inconsistencias.

## Pruebas cubiertas

Archivo principal: `cartera/tests.py`

Cobertura nueva o reforzada:

- ausencia de campos persistidos `Servicio.anticipo` y `Servicio.estado_pago`;
- estados derivables: sin pagos, parcial y pagado;
- pago parcial con historial y movimiento de caja;
- rechazo de sobrepago, pago cero y pago negativo;
- anulacion de pago y reversion de caja;
- pago posterior a cierre sin mutar caja ni `CierreRuta`;
- GET de pago/anulacion sin mutacion;
- GET de cuenta de cobro sin emision ni incremento de consecutivo;
- POST de cuenta de cobro idempotente;
- PDFs reales con bytes `%PDF`;
- aislamiento multiempresa en dashboard.

Tambien se actualizaron pruebas de cierre/rutas para que el cobrado y saldo se calculen desde `PagoServicio`.

## Validaciones ejecutadas

- `manage.py check`: OK.
- `manage.py migrate`: OK, aplico `servicios.0009`.
- `manage.py showmigrations servicios cartera`: `cartera.0002` y `servicios.0009` aplicadas.
- `manage.py makemigrations --check --dry-run`: OK, `No changes detected`.
- `manage.py test cartera rutas -v 2`: 18 tests OK.
- `manage.py test -v 2`: 20 tests OK.
- `manage.py collectstatic --dry-run --noinput`: OK, 138 static files.
- `manage.py auditar_cartera`: OK, 0 inconsistencias.
- `manage.py check --deploy`: 6 warnings esperadas de entorno local (`DEBUG`, HTTPS/cookies seguras, HSTS y `SECRET_KEY`), no atribuibles al modulo de cartera.

## Archivos principales tocados

- `acarreapp/views.py`
- `cartera/management/commands/auditar_cartera.py`
- `cartera/queries.py`
- `cartera/services.py`
- `cartera/tests.py`
- `cartera/urls.py`
- `cartera/views.py`
- `dashboard/views.py`
- `docs/INFORME_FINAL_ACARREAPP.md`
- `docs/INFORME_FINAL_CARTERA.md`
- `requirements.txt`
- `rutas/services.py`
- `rutas/tests.py`
- `rutas/views.py`
- `servicios/forms.py`
- `servicios/migrations/0009_remove_servicio_anticipo_remove_servicio_estado_pago_and_more.py`
- `servicios/models.py`
- `servicios/views.py`
- `templates/cartera/*`
- `templates/cartera/pdf/*`
- `templates/rutas/*`
- `templates/servicios/*`

## Estado final

Cartera queda con una sola fuente de verdad financiera, PDFs A4 verificados, cuenta de cobro sin mutacion por GET, dependencias fijadas, auditor read-only y pruebas/migraciones completas. No se hizo commit, push ni deploy.

# Informe final AcarreApp

## 1. Veredicto ejecutivo

| Item | Resultado |
|---|---|
| Estado inicial | Proyecto Django funcional en raiz, pero con otro proyecto Django anidado dentro de `cartera/`, templates/static duplicados, endpoints modificadores por GET, cartera que ignoraba anticipos, y service worker registrado bajo `/static/`. |
| Estado final | Un solo proyecto Django en raiz; copia anidada retirada; endpoints criticos endurecidos; notificaciones conservadas; PWA basica corregida; pruebas criticas agregadas. |
| Funcional local | Si. `manage.py check`, migraciones, pruebas y `collectstatic --dry-run` pasan. |
| Apta para pruebas locales | Si: **APTA PARA PRUEBAS LOCALES**. |
| Apta para staging | Con advertencias: faltan variables reales de entorno, HTTPS, QA visual en navegador/dispositivos y secretos productivos. |
| Apta para produccion | No. `check --deploy` reporta 6 advertencias esperadas para entorno local. |
| Riesgos pendientes | QA movil real, hardening final de settings productivos, politica formal de reapertura/cierre, idempotencia avanzada de pagos/caja, integracion Veltrix aun no ejecutada. |

Clasificacion final: **APTA PARA PRUEBAS LOCALES**.

## 2. Estructura encontrada

| Area | Hallazgo |
|---|---|
| Proyecto principal | `manage.py` en raiz usando `acarreapp.settings`. |
| Copia duplicada | `cartera/manage.py`, `cartera/acarreapp/`, `cartera/rutas/`, `cartera/servicios/`, `cartera/empresa/`, `cartera/usuarios/`, `cartera/dashboard/`, `cartera/templates/`, `cartera/static/`. |
| Apps vigentes | `empresa`, `usuarios`, `rutas`, `servicios`, `cartera`, `dashboard`, `notificaciones`. |
| Base de datos | SQLite local `db.sqlite3`, trackeada previamente y con datos. Conteos previos: 1 empresa, 3 clientes, 1 vehiculo, 23 rutas, 56 servicios, 4 push subscriptions. |
| Dependencias | Dos requirements; se conservo uno en raiz en UTF-8. |
| Codigo abandonado | Copia anidada mas vieja, sin notificaciones completas y con warning de namespace `cartera` duplicado. |
| Temporales | `__pycache__` y `staticfiles/` generados localmente. |

## 3. Decision de consolidacion

| Decision | Detalle |
|---|---|
| Version conservada | Proyecto raiz. Tenia settings mas completo, dashboard, notificaciones, service worker, templates responsive y migraciones mas recientes. |
| Version descartada | Proyecto anidado en `cartera/`. Era skeleton/legacy parcial y duplicaba apps completas. |
| Funcionalidad trasladada | `cartera/templates/servicios/mis_servicios.html` se traslado a `templates/servicios/mis_servicios.html`. |
| Migraciones validas | Se conservaron migraciones de raiz y se agrego `notificaciones.0002_pushsubscription_empresa`. |
| Static/templates vigentes | `static/` y `templates/` de raiz. |
| Riesgos | La SQLite contenia datos; no se borro. Se aplico solo migracion nullable. |

## 4. Archivos eliminados

| Archivo o carpeta | Motivo | Evidencia | Funcionalidad trasladada |
|---|---|---|---|
| `cartera/manage.py` | Segundo proyecto Django | `manage.py` duplicado y settings propio | Ninguna |
| `cartera/acarreapp/` | Config Django anidada | `check` anidado daba warning namespace `cartera` duplicado | Ninguna |
| `cartera/empresa/` | App duplicada antigua | Menos vistas/forms que raiz | Ninguna |
| `cartera/rutas/` | App duplicada antigua | Menos validaciones y vistas que raiz | Ninguna |
| `cartera/servicios/` | App duplicada antigua | Menos migraciones; sin cantidad reciente | Ninguna |
| `cartera/usuarios/` | App duplicada | Igual/antigua frente a raiz | Ninguna |
| `cartera/dashboard/` | Dashboard antiguo | Casi vacio frente a raiz | Ninguna |
| `cartera/templates/` | Templates anidados | Sombreaban templates raiz | `mis_servicios.html` |
| `cartera/static/` | Static duplicado | Generaba conflicto `img/favicon.png` en collectstatic | Ninguna |
| `__pycache__/` | Cache Python | Artefacto generado | Ninguna |

## 5. Archivos modificados

| Archivo | Cambio | Motivo | Riesgo | Prueba |
|---|---|---|---|---|
| `rutas/views.py` | Reescritura ordenada de vistas, permisos, cierre/export | Evitar IDOR y GET modificador | Medio | `rutas.tests` |
| `rutas/services.py` | Calculo canonico de cierre | Anticipos y saldos correctos | Medio | `test_cerrar_ruta...` |
| `servicios/views.py` | Endpoints POST, tenant fail closed, conductor asignado | Seguridad multiempresa/RBAC | Medio | `rutas.tests` |
| `servicios/models.py` | Validacion tolerante de coordenadas | Evitar 500 por GPS invalido | Bajo | `test_conductor_can_mark...` |
| `cartera/queries.py` | Cartera con servicios `PEND` y `ANT` | No ignorar anticipos | Bajo | `test_cartera...` |
| `notificaciones/*` | Empresa en suscripcion, POST para test/delete, URL delete | Aislamiento y CSRF | Medio | `notificaciones.tests` |
| `static/js/push.js`, `static/sw.js`, `acarreapp/views.py`, `acarreapp/urls.py` | SW en `/sw.js` con scope raiz | PWA/push movil | Bajo | `check`, collectstatic |
| `dashboard/views.py` | APIs restringidas a gerente y empresa | IDOR dashboard | Bajo | `check` |
| `templates/*` | Formularios POST y UI conductor/gerente | Coherencia UI/backend | Bajo | tests + check |
| `requirements.txt`, `.env.example`, `.gitignore`, `README.md` | Limpieza UTF-8 y documentacion | Ejecucion local segura | Bajo | lectura/check |

## 6. Funcionalidades verificadas

| Funcionalidad | Estado inicial | Estado final | Prueba realizada | Resultado |
|---|---|---|---|---|
| Unico proyecto Django | Duplicado | Unico en raiz | `Get-ChildItem -Recurse manage.py` | 1 manage.py |
| `check` | Pasaba raiz | Pasa | `manage.py check` | OK |
| Migraciones | Coherentes, faltaba nueva | Todas aplicadas | `showmigrations` | OK |
| Tests | 0 tests | 10 tests | `manage.py test` | OK |
| Servicios:mis | Roto | Existe | reverse test | OK |
| IDOR gerente | Riesgo | 404 cross-company | test | OK |
| IDOR conductor | Riesgo | 404 ruta ajena | test | OK |
| Cierre | Ignoraba anticipos | Anticipos cuentan | test | OK |
| Export Excel | Podia cerrar implicitamente | No muta estado | test | OK |
| Push | Faltaba delete URL; GET side-effect | POST + CSRF | test | OK |

## 7. Seguridad

| Tema | Resultado |
|---|---|
| Multiempresa | Querysets por `get_current_empresa`; fail closed cuando no hay empresa. |
| IDOR | Rutas/servicios/dashboard filtrados por empresa y conductor asignado. |
| Roles | Gerente/staff/superuser gestionan; conductor opera solo ruta propia. |
| CSRF | Mutaciones principales usan POST y middleware CSRF. |
| Metodos HTTP | Borrar, cerrar, pagos, marcas operativas y push side-effect no aceptan GET. |
| Formularios manipulados | Cliente/ruta se validan contra empresa. |
| Notificaciones | Suscripcion queda ligada a usuario y empresa; envios por empresa filtran suscripciones. |
| Variables de entorno | `.env.example` seguro creado; `.env` real no versionado. |
| Secretos | No se copio llave privada a docs; `check --deploy` aun advierte SECRET_KEY local debil. |
| Exportaciones | Se mitiga formula injection prefijando strings peligrosos. |

## 8. Integridad de negocio

| Tema | Resultado |
|---|---|
| Rutas | Cierre usa transaccion y `select_for_update`; borrar/cerrar solo POST. |
| Servicios | No se crean/editan servicios fuera de empresa; ruta cerrada bloquea cambios. |
| Pagos | Pagos parciales suman a anticipo; sobrepago se recorta al saldo con aviso. |
| Anticipos | Cartera y cierre usan saldo `valor - anticipo`. |
| Cartera | Incluye `PEND` y `ANT`. |
| Caja | Pagos crean ingreso; gastos/ingresos solo positivos. |
| Cierre | Persistido por POST; export/resumen no cierran. |
| Reordenamiento | Valida empresa, gerente, ruta activa, IDs exactos y duplicados. |
| Concurrencia | Cierre usa `transaction.atomic()` y `select_for_update()`. |

## 9. Notificaciones

| Tema | Resultado |
|---|---|
| Arquitectura encontrada | Modelo `PushSubscription`, endpoints `/push/`, `static/js/push.js`, `static/sw.js`. |
| Cambios | Campo `empresa`, endpoint delete, test/delete por POST, SW raiz `/sw.js`, iconos existentes. |
| VAPID | Solo por variables de entorno; `.env.example` sin secretos. |
| Service worker | Servido en `/sw.js` con `Service-Worker-Allowed: /`. |
| Escritorio | Compatible con navegadores Chromium/Edge/Chrome bajo HTTPS o localhost. |
| Android | Preparado para Chrome/Chromium con HTTPS. |
| iPhone | Limitado a Safari moderno con app instalada en pantalla de inicio y soporte del sistema. |
| Limitaciones | No hay compatibilidad universal; requiere permisos, HTTPS, VAPID real y navegador compatible. |
| Pasos de prueba | Login, abrir `/push/debug/`, suscribirse, enviar ping, resetear si se rotan llaves. |
| HTTPS | Obligatorio fuera de localhost. |

## 10. Responsive y movil

| Tema | Resultado |
|---|---|
| Pantallas revisadas estaticamente | Login/base, rutas, hoja de ruta, servicios, detalle, cierre, dashboard, push debug. |
| Problemas encontrados | Tabla/lista dependia de templates anidados; botones de conductor incoherentes; SW scope limitado. |
| Cambios | Template `mis_servicios` canonico; lista permite operar al conductor asignado; tablas mantienen scroll/card responsive existente. |
| Limitaciones | No se realizo QA visual con navegador real a 360/390/412/768 px en esta pasada. |
| Resoluciones probadas | Validacion estatica y tests Django; queda pendiente inspeccion visual manual/browser. |

## 11. Pruebas

| Comando | Resultado |
|---|---|
| `python manage.py check` | `System check identified no issues (0 silenced).` |
| `python manage.py showmigrations` | Todas aplicadas, incluida `notificaciones.0002_pushsubscription_empresa`. |
| `python manage.py makemigrations --check --dry-run` | `No changes detected`. |
| `python manage.py test` | `Ran 10 tests ... OK`. |
| `python manage.py collectstatic --dry-run --noinput` | OK, 138 static files, sin warning de favicon duplicado. |
| `python manage.py check --deploy` | 6 warnings esperados: HSTS, SSL redirect, SECRET_KEY debil, secure cookies, CSRF secure, DEBUG true. |

Fallas previas: 0 tests existentes, `servicios:mis` no reversible, copia anidada con namespace duplicado, GET modificador.  
Fallas introducidas: ninguna detectada por pruebas.  
Fallas pendientes: warnings de deploy y QA browser movil.

## 12. Ejecucion local

```powershell
cd "C:\Users\camil\OneDrive\Escritorio\Python Scripts\AcarreApp"
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Probar notificaciones:

```powershell
# Con el servidor arriba, entrar al navegador:
# http://127.0.0.1:8000/push/debug/
# 1. Iniciar sesion.
# 2. Presionar Suscribirme.
# 3. Presionar Probar ping.
# 4. Usar Reset suscripcion si se cambian llaves VAPID.
```

## 13. Preparacion para Veltrix

| Categoria | Componentes |
|---|---|
| Reutilizables | Modelos operativos de rutas, servicios, movimientos, cierres; forms; templates operativos; JS push; exportaciones; calculos de cierre/cartera. |
| A adaptar | Relaciones `Empresa` y `User`, roles, URLs, base template, navegacion, permisos, static paths, variables de entorno, notificaciones. |
| A descartar | `manage.py`, `settings.py`, `wsgi.py`, `asgi.py`, login propio, middleware propio de empresa, modelo `Empresa` propio, dashboard global paralelo. |
| Riesgos | Migracion de datos, mapeo de usuarios/conductores, permisos por app habilitable, coexistencia con CarterApp, URLs bajo `/apps/acarreapp/`. |
| Modelos a empresa central | `Ruta`, `Cliente`, `Vehiculo`, `MovimientoCaja`, `CierreRuta`, `PushSubscription` o equivalente. |
| Modelos a usuarios centrales | `Ruta.conductor`, `MovimientoCaja.usuario`, `CierreRuta.generado_por`, `ServicioComentario.autor`, `PushSubscription.user`. |
| Roles | Reemplazar `UserProfile.rol` local por RBAC Veltrix. |
| URLs | Prefijar bajo `/apps/acarreapp/`. |
| Templates | Extender base Veltrix y menu central. |
| Notificaciones | Reusar servicio central si existe; si no, namespacing por app/empresa. |

## 14. Plan de integracion a Veltrix

| Fase | Objetivo | Archivos probables | Migraciones | Pruebas | Riesgos | Aceptacion | Rollback |
|---|---|---|---|---|---|---|---|
| 0 | Auditar repo Veltrix | settings, urls, apps, RBAC | No | check/test Veltrix | Suposiciones | Mapa real | Sin cambios |
| 1 | Crear app y registro | `apps/acarreapp/`, catalogo | Minima | app visible | Navegacion | App habilitable | Desregistrar |
| 2 | Modelos multiempresa | models | Si | IDOR | Datos | Tenant central | revert migration |
| 3 | Rutas/vehiculos/servicios | views/forms/templates | Si | CRUD | FK empresa | CRUD aislado | feature flag |
| 4 | Operacion conductor | views/templates | No/Si | conductor own route | permisos | conductor opera propia | desactivar urls |
| 5 | Pagos/caja/cierre | services/views | Si | cierre/caja | saldos | cierre exacto | restore backup |
| 6 | Cartera/reportes | queries/dashboard | Si/No | reportes | CarterApp | cartera local ok | ocultar menu |
| 7 | Notificaciones/PWA | push/sw/static | Si/No | subscribe/ping | HTTPS/iOS | push por empresa | desactivar push |
| 8 | Migracion datos | scripts/commands | Si | conteos | perdida datos | conciliacion | backup restore |
| 9 | Staging/prod | settings/deploy | No | smoke/e2e | seguridad | checklist deploy | rollback release |

## 15. Pendientes

| Prioridad | Pendiente |
|---|---|
| CRITICO | Configurar settings productivos: `DEBUG=false`, `SECRET_KEY` fuerte, HTTPS, secure cookies, HSTS segun dominio. |
| ALTO | QA visual real en movil 360/390/412/768 y escritorio. |
| ALTO | Definir politica de cierre: inmutable, recalculable o versionado. |
| ALTO | Revisar idempotencia avanzada de pagos y movimientos de caja. |
| MEDIO | Mejorar UI de permisos bloqueados y navegador push incompatible. |
| MEDIO | Agregar mas pruebas de formularios manipulados y exportaciones completas. |
| MEDIO | Evaluar integracion opcional con CarterApp sin acoplar esta fase. |
| BAJO | Limpiar mojibake restante en textos visibles antiguos. |

## 16. Recomendacion final

Conviene **integrar el codigo adaptandolo**, no reescribir toda la app. La logica operativa de rutas, servicios, pagos, cartera, cierre, reportes y push ya es recuperable y ahora esta mas consolidada. Para Veltrix deben descartarse la infraestructura Django independiente y los modelos centrales duplicados, adaptando la app a empresa/usuario/RBAC centrales. Reescribir solo modulos especificos si en la fase Veltrix aparecen reglas de negocio incompatibles, especialmente cierre, caja y cartera.

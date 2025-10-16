// sw.js (notificaciones mejoradas)

self.addEventListener("push", (event) => {
  if (!event.data) return;

  let payload = {};
  try { payload = event.data.json(); }
  catch { payload = { title: "AcarreApp", body: event.data.text() }; }

  const {
    title = "AcarreApp",
    body = "",
    data = {},
    icon = "/static/icons/pwa-192.png",
    badge = "/static/icons/badge.png",
    tag = "acarreapp",
    requireInteraction = false,
    actions = [],       // [{action:'ver', title:'Ver detalle'}]
  } = payload;

  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon,
      badge,
      tag,
      requireInteraction,   // permanece hasta que el usuario la cierre
      data,                 // ej: {url:'/rutas/123/detalle/'}
      actions,
      vibrate: [80, 30, 80],
    })
  );
});

// En click: intenta enfocar una pestaña abierta; si no, abre una nueva.
self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  const url = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil((async () => {
    const allClients = await clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const client of allClients) {
      // Si ya hay una pestaña en el mismo origen, la enfocamos y navegamos
      try {
        await client.focus();
        await client.navigate(url);
        return;
      } catch (_) { /* noop */ }
    }
    await clients.openWindow(url);
  })());
});

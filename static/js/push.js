async function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return null;
  return await navigator.serviceWorker.register("/static/sw.js");
}

async function askPermission() {
  if (!("Notification" in window)) return "denied";
  if (Notification.permission === "granted") return "granted";
  if (Notification.permission === "denied") return "denied";
  return await Notification.requestPermission();
}

async function subscribePush(publicKeyBase64Url) {
  const reg = await registerServiceWorker();
  if (!reg) return null;
  const perm = await askPermission();
  if (perm !== "granted") return null;

  const applicationServerKey = urlBase64ToUint8Array(publicKeyBase64Url);
  return await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey });
}

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) outputArray[i] = rawData.charCodeAt(i);
  return outputArray;
}

window.initAcarrePush = async function (publicKey) {
  try {
    const sub = await subscribePush(publicKey);
    if (!sub) return;

    await fetch("/push/subscribe/", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCookie("csrftoken") },
      body: JSON.stringify({ subscription: sub }),
      credentials: "include",
    });
  } catch (e) { console.warn("Push init failed:", e); }
};

function getCookie(name) {
  const cookieValue = document.cookie.split("; ").find(row => row.startsWith(name + "="));
  return cookieValue ? decodeURIComponent(cookieValue.split("=")[1]) : "";
}

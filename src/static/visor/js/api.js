// Llamadas a /visor/api/ con CSRF y manejo de errores uniforme.

const BASE = window.VISOR.api;

function csrf() {
  return document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
}

function armarUrl(ruta, params = {}) {
  const url = new URL(ruta.startsWith("/") ? ruta : BASE + ruta, location.origin);
  Object.entries(params).forEach(([clave, valor]) => {
    if (valor !== "" && valor !== null && valor !== undefined) url.searchParams.set(clave, valor);
  });
  return url;
}

async function leer(respuesta) {
  // Sesión vencida: el servidor redirige al login (HTML), no a JSON.
  if (respuesta.redirected && respuesta.url.includes("/ingresar/")) {
    location.reload();
    throw new Error("La sesión venció.");
  }
  let datos = null;
  try {
    datos = await respuesta.json();
  } catch {
    // respuesta sin JSON
  }
  if (!respuesta.ok) {
    const error = new Error(datos?.error || `Error ${respuesta.status}`);
    error.detalle = datos?.detalle;
    error.status = respuesta.status;
    throw error;
  }
  return datos;
}

export async function get(ruta, params) {
  return leer(await fetch(armarUrl(ruta, params), { headers: { Accept: "application/json" } }));
}

export async function enviar(metodo, ruta, cuerpo) {
  return leer(await fetch(armarUrl(ruta), {
    method: metodo,
    headers: { "Content-Type": "application/json", Accept: "application/json", "X-CSRFToken": csrf() },
    body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
  }));
}

// Convierte el detalle de validación de Django en un texto legible.
export function textoError(error) {
  if (!error.detalle) return error.message;
  return Object.values(error.detalle).flat().join(" ");
}

// Sistemas de coordenadas usados en Cochabamba y "Ir a coordenada".
// El departamento cruza las zonas UTM 19S y 20S (límite en el meridiano -66).

import { getMapa } from "./mapa.js";
import { aviso, nodo, panel } from "./ui.js";

proj4.defs("EPSG:32719", "+proj=utm +zone=19 +south +datum=WGS84 +units=m +no_defs");
proj4.defs("EPSG:32720", "+proj=utm +zone=20 +south +datum=WGS84 +units=m +no_defs");

export const SISTEMAS = [
  { id: "WGS84", nombre: "Geográficas WGS84 (lat, lon)" },
  { id: "EPSG:32719", nombre: "UTM 19S (este, norte)" },
  { id: "EPSG:32720", nombre: "UTM 20S (este, norte)" },
];

export function zonaUtm(lon) {
  return lon < -66 ? "EPSG:32719" : "EPSG:32720";
}

export function aUtm(lat, lon) {
  const zona = zonaUtm(lon);
  const [este, norte] = proj4("EPSG:4326", zona, [lon, lat]);
  return { zona: zona === "EPSG:32719" ? "19S" : "20S", este, norte };
}

// Convierte lo que escribió el usuario a [lat, lon]. Lanza Error si no es válido.
export function aLatLng(sistema, x, y) {
  const a = Number(String(x).replace(",", "."));
  const b = Number(String(y).replace(",", "."));
  if (!Number.isFinite(a) || !Number.isFinite(b)) throw new Error("Las coordenadas deben ser números.");
  if (sistema === "WGS84") {
    if (Math.abs(a) > 90 || Math.abs(b) > 180) throw new Error("Latitud o longitud fuera de rango.");
    return [a, b];
  }
  const [lon, lat] = proj4(sistema, "EPSG:4326", [a, b]);
  return [lat, lon];
}

export function camposCoordenadas() {
  return `
    <label>Sistema de coordenadas
      <select name="sistema">${SISTEMAS.map((s) => `<option value="${s.id}">${s.nombre}</option>`).join("")}</select>
    </label>
    <label><span data-eje="x">Latitud</span><input name="x" inputmode="decimal" required></label>
    <label><span data-eje="y">Longitud</span><input name="y" inputmode="decimal" required></label>`;
}

// Cambia las etiquetas Latitud/Longitud ↔ Este/Norte según el sistema elegido.
export function enlazarEtiquetas(formulario) {
  const actualizar = () => {
    const wgs = formulario.sistema.value === "WGS84";
    formulario.querySelector('[data-eje="x"]').textContent = wgs ? "Latitud" : "Este (m)";
    formulario.querySelector('[data-eje="y"]').textContent = wgs ? "Longitud" : "Norte (m)";
  };
  formulario.sistema.addEventListener("change", actualizar);
  actualizar();
}

let marcador = null;

export function irACoordenada() {
  const formulario = nodo(`<form class="formulario">${camposCoordenadas()}
    <div class="acciones"><button class="boton">Ir</button></div></form>`);
  enlazarEtiquetas(formulario);
  formulario.addEventListener("submit", (e) => {
    e.preventDefault();
    try {
      const latlng = aLatLng(formulario.sistema.value, formulario.x.value, formulario.y.value);
      const mapa = getMapa();
      marcador?.remove();
      marcador = L.marker(latlng).addTo(mapa).bindPopup(`${latlng[0].toFixed(6)}, ${latlng[1].toFixed(6)}`).openPopup();
      mapa.setView(latlng, Math.max(mapa.getZoom(), 14));
    } catch (error) {
      aviso(error.message, "error");
    }
  });
  panel.abrir("Ir a coordenada", formulario, { alCerrar: () => { marcador?.remove(); marcador = null; } });
}

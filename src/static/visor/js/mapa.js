// Mapa Leaflet: mapas base, vista anterior/siguiente, marcadores espaciales y barra de estado.

import { emitir, estado, on } from "./estado.js";
import { aUtm } from "./coordenadas.js";
import { aviso } from "./ui.js";

let mapa = null;
let capaBase = null;
const historial = [];
let posicion = -1;
let navegando = false;

export const getMapa = () => mapa;

export function crearMapa() {
  mapa = L.map("mapa", { zoomControl: true, boxZoom: false });
  mapa.createPane("limites").style.zIndex = 350;
  mapa.createPane("proyectos").style.zIndex = 450;
  mapa.createPane("puntos").style.zIndex = 460; // puntos siempre encima de polígonos: si no, quedan tapados y no se pueden pinchar
  L.control.scale({ imperial: false, position: "bottomleft" }).addTo(mapa);
  mapa.pm.setLang("es");
  mapa.pm.setGlobalOptions({ snappable: true, snapDistance: 15, allowSelfIntersection: false });

  setMapaBase(estado.config.mapas_base[0].id);
  irExtensionTotal();

  mapa.on("moveend", registrarVista);
  mapa.on("mousemove", (e) => mostrarCoordenadas(e.latlng));
  mapa.on("zoomend moveend", mostrarEscala);
  on("distribucion", () => setTimeout(() => mapa.invalidateSize(), 50));
  return mapa;
}

export function setMapaBase(id) {
  const base = estado.config.mapas_base.find((b) => b.id === id);
  if (!base) return;
  capaBase?.remove();
  capaBase = L.tileLayer(base.url, { attribution: base.atribucion, maxZoom: base.max_zoom, subdomains: "abc" }).addTo(mapa);
  capaBase.bringToBack();
  estado.mapaBase = id;
  document.getElementById("estado-mapa-base").textContent = `Mapa base: ${base.nombre}`;
}

export function irExtensionTotal() {
  const e = estado.config.extension;
  if (e) mapa.fitBounds([[e[1], e[0]], [e[3], e[2]]]);
  else mapa.setView([-17.39, -66.16], 8);
}

// ---------------------------------------------------------------- vista anterior / siguiente

function registrarVista() {
  if (navegando) {
    navegando = false;
    return;
  }
  historial.splice(posicion + 1);
  historial.push({ centro: mapa.getCenter(), zoom: mapa.getZoom() });
  posicion = historial.length - 1;
  emitir("vista");
}

function irAVista(i) {
  if (i < 0 || i >= historial.length) return;
  posicion = i;
  navegando = true;
  mapa.setView(historial[i].centro, historial[i].zoom);
  emitir("vista");
}

export const vistaAnterior = () => irAVista(posicion - 1);
export const vistaSiguiente = () => irAVista(posicion + 1);
export const hayAnterior = () => posicion > 0;
export const haySiguiente = () => posicion < historial.length - 1;

// ---------------------------------------------------------------- marcadores espaciales (por usuario, en este navegador)

const claveMarcadores = () => `visor:marcadores:${window.VISOR.usuario}`;

export function marcadores() {
  try {
    return JSON.parse(localStorage.getItem(claveMarcadores())) || [];
  } catch {
    return [];
  }
}

function guardarMarcadores(lista) {
  try {
    localStorage.setItem(claveMarcadores(), JSON.stringify(lista));
  } catch {
    aviso("No se pudo guardar el marcador en este navegador.", "error");
  }
}

export function agregarMarcador() {
  const nombre = prompt("Nombre del marcador:");
  if (!nombre) return;
  const c = mapa.getCenter();
  guardarMarcadores([...marcadores(), { nombre, lat: c.lat, lng: c.lng, zoom: mapa.getZoom() }]);
  aviso(`Marcador «${nombre}» guardado.`, "ok");
}

export function irAMarcador(m) {
  mapa.setView([m.lat, m.lng], m.zoom);
}

export function borrarMarcador(indice) {
  const lista = marcadores();
  lista.splice(indice, 1);
  guardarMarcadores(lista);
}

// ---------------------------------------------------------------- barra de estado

function mostrarCoordenadas(latlng) {
  const utm = aUtm(latlng.lat, latlng.lng);
  document.getElementById("estado-coordenadas").innerHTML =
    `${latlng.lat.toFixed(5)}, ${latlng.lng.toFixed(5)} &nbsp;|&nbsp; UTM ${utm.zona}: ${utm.este.toFixed(0)} E, ${utm.norte.toFixed(0)} N`;
}

function mostrarEscala() {
  const lat = mapa.getCenter().lat;
  const metrosPorPixel = (40075016.686 * Math.cos((lat * Math.PI) / 180)) / 2 ** (mapa.getZoom() + 8);
  const escala = Math.round((metrosPorPixel * 96) / 0.0254);
  document.getElementById("estado-escala").textContent = `Escala ≈ 1:${escala.toLocaleString("es-BO")}`;
}

export function ajustarA(capas) {
  const grupo = L.featureGroup(capas);
  if (grupo.getLayers().length) mapa.fitBounds(grupo.getBounds(), { maxZoom: 16, padding: [30, 30] });
}


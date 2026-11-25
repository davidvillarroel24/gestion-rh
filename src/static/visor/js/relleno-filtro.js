// «Relleno transparente» de los filtros: rellena los municipios donde están los proyectos
// filtrados. Sin filtros no rellena nada (todos los municipios tienen proyectos y el mapa
// quedaría tapado). Se actualiza con cada filtro y con el zoom; se recuerda en el navegador.

import { estado, on } from "./estado.js";
import { getMapa } from "./mapa.js";

const CLAVE = "visor.rellenoFiltro";
const COLOR = "#0b6e4f";
const nivelDeZoom = (z) => (z <= 7 ? 7 : z <= 9 ? 9 : z <= 11 ? 11 : z <= 13 ? 13 : 15);

let activo = false;
let capa = null;
let datos = null;    // municipios del nivel de zoom actual
let nivel = null;
let casilla = null;

const hayFiltros = () => Object.keys(estado.filtros).length > 0;

function leer() {
  try {
    return localStorage.getItem(CLAVE) === "1";
  } catch {
    return false;
  }
}

function guardar() {
  try {
    localStorage.setItem(CLAVE, activo ? "1" : "0");
  } catch {
    // almacenamiento bloqueado: vale solo para esta sesión
  }
}

async function actualizar() {
  if (casilla) casilla.closest("label").classList.toggle("sin-efecto", activo && !hayFiltros());
  capa.clearLayers();
  if (!activo || !hayFiltros()) return;
  const mapa = getMapa();
  const nuevo = nivelDeZoom(mapa.getZoom());
  if (nuevo !== nivel || !datos) {
    nivel = nuevo;
    datos = await fetch(`${window.VISOR.territorio.replace("CAPA", "municipios")}?z=${nivel}`).then((r) => r.json());
  }
  const ids = new Set(estado.filas.flatMap((f) => f.municipio_ids || []));
  capa.clearLayers();
  capa.addData({ ...datos, features: datos.features.filter((f) => ids.has(f.properties.id)) });
}

export function iniciarRellenoFiltro(elemento) {
  const mapa = getMapa();
  if (!mapa.getPane("relleno")) mapa.createPane("relleno").style.zIndex = 340; // bajo los límites y los proyectos
  capa = L.geoJSON(null, {
    pane: "relleno", interactive: false,
    style: { color: COLOR, weight: 1.5, opacity: 0.7, fillColor: COLOR, fillOpacity: 0.22 },
  }).addTo(mapa);
  casilla = elemento;
  activo = leer();
  casilla.checked = activo;
  casilla.addEventListener("change", () => {
    activo = casilla.checked;
    guardar();
    actualizar();
  });
  on("filas", actualizar); // la tabla terminó de cargar los proyectos filtrados
  mapa.on("zoomend", () => activo && hayFiltros() && nivelDeZoom(mapa.getZoom()) !== nivel && actualizar());
  actualizar();
}

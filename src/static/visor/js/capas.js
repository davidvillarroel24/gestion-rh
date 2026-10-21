// Capas del mapa y su tabla de contenidos (TOC):
// - Proyectos: una capa por unidad, con las geometrías filtradas.
// - Límites: departamento, regiones, provincias y municipios (simplificados según el zoom).

import { emitir, estado, on } from "./estado.js";
import { get } from "./api.js";
import { ajustarA, getMapa } from "./mapa.js";
import { aviso, esc } from "./ui.js";

const COLORES = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#8c564b", "#e377c2", "#17becf"];
const COLOR_SELECCION = "#f5c400";

const LIMITES = [
  { id: "departamento", nombre: "Departamento", visible: true, estilo: { color: "#111", weight: 2.5, fill: false } },
  { id: "regiones", nombre: "Regiones", visible: false, estilo: { color: "#7b3294", weight: 2, fillOpacity: 0.04 } },
  { id: "provincias", nombre: "Provincias", visible: false, estilo: { color: "#9c6ad1", weight: 1.5, dashArray: "6 4", fillOpacity: 0 } },
  { id: "municipios", nombre: "Municipios", visible: true, estilo: { color: "#555", weight: 0.8, fillOpacity: 0 } },
];

const proyectos = {}; // unidadId -> { unidad, color, grupo, visible, opacidad, cantidad }
const limites = {};   // id -> { def, grupo, visible, opacidad, nivel }

export const colorUnidad = (unidadId) => proyectos[unidadId]?.color || "#555";

// ---------------------------------------------------------------- proyectos

function estilo(feature, opacidad) {
  const p = feature.properties;
  const seleccionado = estado.seleccion.has(p.proyecto_id);
  const color = seleccionado ? COLOR_SELECCION : colorUnidad(p.unidad_id);
  return { color: seleccionado ? "#7a5c00" : color, fillColor: color, weight: seleccionado ? 4 : 2.5,
           opacity: opacidad, fillOpacity: 0.35 * opacidad };
}

function crearGrupoProyectos(info) {
  return L.geoJSON(null, {
    pane: "proyectos",
    style: (f) => estilo(f, info.opacidad),
    pointToLayer: (f, latlng) => L.circleMarker(latlng, { radius: 7, pane: "puntos" }),
    onEachFeature: (feature, capa) => {
      capa.bindTooltip(`${esc(feature.properties.codigo)} – ${esc(feature.properties.tipo_elemento)}`, { sticky: true });
      capa.on("click", (e) => {
        L.DomEvent.stopPropagation(e);
        emitir("clic-geometria", { feature, capa, latlng: e.latlng, original: e.originalEvent });
      });
    },
  });
}

export async function recargarProyectos() {
  const mapa = getMapa();
  try {
    const datos = await get("geometrias/", estado.filtros);
    Object.values(proyectos).forEach((info) => {
      info.grupo.clearLayers();
      info.cantidad = 0;
    });
    datos.features.forEach((f) => {
      const info = proyectos[f.properties.unidad_id];
      if (!info) return;
      info.grupo.addData(f);
      info.cantidad += 1;
    });
    Object.values(proyectos).forEach((info) => {
      if (info.visible) info.grupo.addTo(mapa);
    });
  } catch (error) {
    aviso(`No se pudieron cargar los proyectos: ${error.message}`, "error");
  }
  dibujarToc();
}

export function actualizarEstilos() {
  Object.values(proyectos).forEach((info) => info.grupo.setStyle((f) => estilo(f, info.opacidad)));
}

// Todas las capas (geometrías) de los proyectos indicados.
export function capasDeProyectos(ids) {
  const resultado = [];
  Object.values(proyectos).forEach((info) =>
    info.grupo.eachLayer((capa) => {
      if (ids.has(capa.feature.properties.proyecto_id)) resultado.push(capa);
    }));
  return resultado;
}

export function capaDeGeometria(id) {
  for (const info of Object.values(proyectos)) {
    const capa = info.grupo.getLayers().find((c) => c.feature.properties.id === id);
    if (capa) return capa;
  }
  return null;
}

// Geometrías visibles en el mapa (para seleccionar por rectángulo).
export function geometriasVisibles() {
  return Object.values(proyectos).filter((i) => i.visible).flatMap((i) => i.grupo.getLayers());
}

// ---------------------------------------------------------------- límites

const nivelDeZoom = (z) => (z <= 7 ? 7 : z <= 9 ? 9 : z <= 11 ? 11 : z <= 13 ? 13 : 15);

async function cargarLimite(info) {
  const nivel = nivelDeZoom(getMapa().getZoom());
  if (info.nivel === nivel) return;
  info.nivel = nivel;
  try {
    const url = `${window.VISOR.territorio.replace("CAPA", info.def.id)}?z=${nivel}`;
    const datos = await fetch(url).then((r) => r.json());
    info.grupo.clearLayers();
    info.grupo.addData(datos);
  } catch {
    info.nivel = null;
    aviso(`No se pudo cargar la capa ${info.def.nombre}.`, "error");
  }
}

function crearLimites() {
  const mapa = getMapa();
  LIMITES.forEach((def) => {
    const info = { def, visible: def.visible, opacidad: 1, nivel: null };
    info.grupo = L.geoJSON(null, {
      pane: "limites",
      style: () => ({ ...def.estilo, opacity: info.opacidad }),
      interactive: def.id !== "departamento",
      onEachFeature: (feature, capa) => {
        const p = feature.properties;
        capa.on("click", (e) => emitir("clic-limite", { capa: def.id, propiedades: p, latlng: e.latlng }));
        if (def.id !== "departamento") capa.bindTooltip(esc(p.nombre), { sticky: true });
      },
    });
    limites[def.id] = info;
    if (info.visible) {
      info.grupo.addTo(mapa);
      cargarLimite(info);
    }
  });
  mapa.on("zoomend", () => Object.values(limites).filter((i) => i.visible).forEach(cargarLimite));
}

// ---------------------------------------------------------------- tabla de contenidos

function filaCapa({ simbolo, nombre, visible, opacidad, alternar, cambiarOpacidad, zoom }) {
  const fila = document.createElement("div");
  fila.className = "capa";
  fila.innerHTML = `
    <input type="checkbox" ${visible ? "checked" : ""} title="Mostrar u ocultar">
    <span>${simbolo}${esc(nombre)}</span>
    <input type="range" min="0.1" max="1" step="0.1" value="${opacidad}" title="Opacidad">
    <button type="button" class="boton-icono" title="Acercar a la capa"><i class="bi bi-zoom-in"></i></button>`;
  fila.querySelector("[type=checkbox]").addEventListener("change", (e) => alternar(e.target.checked));
  fila.querySelector("[type=range]").addEventListener("input", (e) => cambiarOpacidad(Number(e.target.value)));
  fila.querySelector("button").addEventListener("click", zoom);
  return fila;
}

export function dibujarToc() {
  const mapa = getMapa();
  const toc = document.getElementById("capas");
  toc.replaceChildren();

  const tituloProyectos = document.createElement("div");
  tituloProyectos.className = "capa-grupo";
  tituloProyectos.textContent = "Proyectos";
  toc.append(tituloProyectos);
  Object.values(proyectos).forEach((info) => {
    toc.append(filaCapa({
      simbolo: `<span class="capa-simbolo" style="display:inline-block;vertical-align:middle;margin-right:6px;border-color:${info.color};background:${info.color}55"></span>`,
      nombre: `${info.unidad.nombre} (${info.cantidad})`,
      visible: info.visible,
      opacidad: info.opacidad,
      alternar: (v) => {
        info.visible = v;
        v ? info.grupo.addTo(mapa) : info.grupo.remove();
      },
      cambiarOpacidad: (o) => {
        info.opacidad = o;
        info.grupo.setStyle((f) => estilo(f, o));
      },
      zoom: () => ajustarA(info.grupo.getLayers()),
    }));
  });

  const tituloLimites = document.createElement("div");
  tituloLimites.className = "capa-grupo";
  tituloLimites.textContent = "Límites";
  toc.append(tituloLimites);
  Object.values(limites).forEach((info) => {
    toc.append(filaCapa({
      simbolo: `<span class="capa-simbolo" style="display:inline-block;vertical-align:middle;margin-right:6px;border-color:${info.def.estilo.color}"></span>`,
      nombre: info.def.nombre,
      visible: info.visible,
      opacidad: info.opacidad,
      alternar: (v) => {
        info.visible = v;
        if (v) {
          info.grupo.addTo(mapa);
          cargarLimite(info);
        } else {
          info.grupo.remove();
        }
      },
      cambiarOpacidad: (o) => {
        info.opacidad = o;
        info.grupo.setStyle({ opacity: o });
      },
      zoom: () => info.grupo.getLayers().length && mapa.fitBounds(info.grupo.getBounds()),
    }));
  });
}

export function iniciarCapas() {
  estado.config.unidades.forEach((unidad, i) => {
    const info = { unidad, color: COLORES[i % COLORES.length], visible: true, opacidad: 1, cantidad: 0 };
    info.grupo = crearGrupoProyectos(info);
    proyectos[unidad.id] = info;
  });
  crearLimites();
  dibujarToc();
  on("seleccion", actualizarEstilos);
  on("filtros", recargarProyectos);
  recargarProyectos();
}

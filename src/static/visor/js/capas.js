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
  { id: "departamento", nombre: "Departamento", visible: true, color: "#111111", relleno: false, estilo: { weight: 4.5 } },
  { id: "regiones", nombre: "Regiones", visible: false, color: "#7b3294", relleno: false, estilo: { weight: 4 } },
  { id: "provincias", nombre: "Provincias", visible: false, color: "#9c6ad1", relleno: false, estilo: { weight: 3.5, dashArray: "6 4" } },
  { id: "municipios", nombre: "Municipios", visible: true, color: "#555555", relleno: false, estilo: { weight: 2.8 } },
];
// Paleta para elegir el color de cada capa (además de «Otro color…»).
const PALETA = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#8c564b", "#e377c2", "#17becf",
                "#bcbd22", "#7f7f7f", "#111111", "#0b6e4f", "#f5c400", "#00a6ed", "#c2185b", "#5d4037"];
const RELLENO = 0.2; // opacidad del relleno transparente (por la opacidad de la capa)

// Colores, relleno y opacidad elegidos: se recuerdan en este navegador (si no se puede, se usan los de fábrica).
const CLAVE_ESTILOS = "visor.estilosCapas";
function leerEstilos() {
  try {
    return JSON.parse(localStorage.getItem(CLAVE_ESTILOS)) || {};
  } catch {
    return {};
  }
}
function guardarEstilo(clave, estiloCapa) {
  try {
    const todos = leerEstilos();
    todos[clave] = estiloCapa;
    localStorage.setItem(CLAVE_ESTILOS, JSON.stringify(todos));
  } catch {
    // modo privado o almacenamiento bloqueado: el cambio vale solo para esta sesión
  }
}

const proyectos = {}; // unidadId -> { unidad, color, grupo, visible, opacidad, cantidad }
const limites = {};   // id -> { def, grupo, visible, opacidad, nivel }

export const colorUnidad = (unidadId) => proyectos[unidadId]?.color || "#555";

// ---------------------------------------------------------------- proyectos

function estilo(feature, opacidad) {
  const p = feature.properties;
  const seleccionado = estado.seleccion.has(p.proyecto_id);
  const color = seleccionado ? COLOR_SELECCION : colorUnidad(p.unidad_id);
  const relleno = proyectos[p.unidad_id]?.relleno ?? true;
  return { color: seleccionado ? "#7a5c00" : color, fillColor: color, weight: seleccionado ? 4 : 2.5,
           opacity: opacidad, fill: relleno || seleccionado, fillOpacity: (relleno ? 0.35 : 0.1) * opacidad };
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
    emitir("proyectos-cargados");
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
    info.datos = await fetch(url).then((r) => r.json());
    dibujarLimite(info);
  } catch {
    info.nivel = null;
    aviso(`No se pudo cargar la capa ${info.def.nombre}.`, "error");
  }
}

// Dibuja el límite sin las partes que el usuario ocultó (ej. solo algunos municipios).
function dibujarLimite(info) {
  if (!info.datos) return;
  info.grupo.clearLayers();
  info.grupo.addData(info.ocultos.size
    ? { ...info.datos, features: info.datos.features.filter((f) => !info.ocultos.has(f.properties.id)) }
    : info.datos);
}

// Lista de partes de cada límite (para elegir cuáles se ven). El departamento es uno solo.
function partesDe(id) {
  const c = estado.config;
  return { regiones: c.regiones, provincias: c.provincias, municipios: c.municipios }[id] || null;
}

function crearLimites() {
  const mapa = getMapa();
  LIMITES.forEach((def) => {
    const guardado = leerEstilos()[`limites:${def.id}`] || {};
    const info = { def, visible: def.visible, nivel: null, color: guardado.color || def.color,
                   relleno: guardado.relleno ?? def.relleno, opacidad: guardado.opacidad ?? 1,
                   ocultos: new Set(guardado.ocultos || []) };
    info.estilo = () => ({ ...def.estilo, color: info.color, opacity: info.opacidad, fill: info.relleno,
                           fillColor: info.color, fillOpacity: info.relleno ? RELLENO * info.opacidad : 0 });
    info.grupo = L.geoJSON(null, {
      pane: "limites",
      style: () => info.estilo(),
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

function simbolo(color, relleno) {
  return `background:${relleno ? `${color}55` : "transparent"};border-color:${color}`;
}

// Ventana con la paleta de colores y la opción de relleno de una capa.
let paletaAbierta = null;
const sinTildes = (t) => String(t).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

function abrirPaleta(ancla, { color, relleno, partes = null, ocultos = new Set(), alCambiar }) {
  paletaAbierta?.remove();
  ocultos = new Set(ocultos);
  const caja = document.createElement("div");
  caja.className = "paleta-capa" + (partes ? " con-partes" : "");
  caja.innerHTML = `
    <div class="paleta-colores">${PALETA.map((c) => `<button type="button" data-color="${c}" title="${c}"
      style="background:${c}" class="${c.toLowerCase() === color.toLowerCase() ? "elegido" : ""}"></button>`).join("")}</div>
    <label class="paleta-otro">Otro color… <input type="color" value="${color}"></label>
    <label class="paleta-relleno"><input type="checkbox" ${relleno ? "checked" : ""}> Relleno transparente</label>
    ${partes ? `<div class="paleta-partes">
      <div class="pp-titulo">Mostrar <span data-cuenta></span></div>
      <input type="search" placeholder="Buscar…" aria-label="Buscar">
      <div class="pp-acciones"><button type="button" data-todos>Todos</button><button type="button" data-ninguno>Ninguno</button>
        <button type="button" data-buscados title="Muestra solo los que coinciden con la búsqueda">Solo buscados</button></div>
      <div class="pp-lista"></div>
    </div>` : ""}`;
  const avisar = () => alCambiar({ color, relleno, ocultos: [...ocultos] });
  const elegir = (nuevo) => {
    color = nuevo;
    caja.querySelectorAll("[data-color]").forEach((b) => b.classList.toggle("elegido", b.dataset.color === nuevo));
    caja.querySelector("[type=color]").value = nuevo;
    avisar();
  };
  caja.querySelectorAll("[data-color]").forEach((b) => b.addEventListener("click", () => elegir(b.dataset.color)));
  caja.querySelector("[type=color]").addEventListener("input", (e) => elegir(e.target.value));
  caja.querySelector(".paleta-relleno input").addEventListener("change", (e) => {
    relleno = e.target.checked;
    avisar();
  });
  if (partes) {
    const buscar = caja.querySelector(".paleta-partes input[type=search]");
    const lista = caja.querySelector(".pp-lista");
    const coinciden = () => partes.filter((x) => sinTildes(x.nombre).includes(sinTildes(buscar.value.trim())));
    const dibujar = () => {
      lista.innerHTML = coinciden().map((x) => `<label><input type="checkbox" value="${x.id}" ${ocultos.has(x.id) ? "" : "checked"}> ${esc(x.nombre)}</label>`).join("")
        || '<p class="tenue">Sin coincidencias</p>';
      caja.querySelector("[data-cuenta]").textContent = ocultos.size ? `(${partes.length - ocultos.size} de ${partes.length})` : "(todos)";
    };
    lista.addEventListener("change", (e) => {
      const id = Number(e.target.value);
      e.target.checked ? ocultos.delete(id) : ocultos.add(id);
      dibujar();
      avisar();
    });
    buscar.addEventListener("input", dibujar);
    caja.querySelector("[data-todos]").addEventListener("click", () => { ocultos.clear(); dibujar(); avisar(); });
    caja.querySelector("[data-ninguno]").addEventListener("click", () => { ocultos = new Set(partes.map((x) => x.id)); dibujar(); avisar(); });
    caja.querySelector("[data-buscados]").addEventListener("click", () => {
      const ver = new Set(coinciden().map((x) => x.id));
      ocultos = new Set(partes.filter((x) => !ver.has(x.id)).map((x) => x.id));
      dibujar();
      avisar();
    });
    dibujar();
  }
  document.body.append(caja);
  const r = ancla.getBoundingClientRect();
  caja.style.left = `${Math.min(r.left, window.innerWidth - caja.offsetWidth - 8)}px`;
  caja.style.top = `${Math.min(r.bottom + 4, window.innerHeight - caja.offsetHeight - 8)}px`;
  paletaAbierta = caja;
  setTimeout(() => document.addEventListener("click", function cerrar(e) {
    if (caja.contains(e.target) || e.target === ancla) return;
    caja.remove();
    if (paletaAbierta === caja) paletaAbierta = null;
    document.removeEventListener("click", cerrar);
  }), 0);
}

function filaCapa({ color, relleno, nombre, visible, opacidad, alternar, cambiarOpacidad, cambiarEstilo, zoom,
                   partes = null, ocultos = new Set(), nombreCon = null }) {
  const fila = document.createElement("div");
  fila.className = "capa";
  fila.innerHTML = `
    <input type="checkbox" ${visible ? "checked" : ""} title="Mostrar u ocultar">
    <span><button type="button" class="capa-simbolo" title="${partes ? "Color, relleno y qué se muestra" : "Color y relleno"}" style="${simbolo(color, relleno)}"></button><span class="capa-nombre">${esc(nombre)}</span></span>
    <input type="range" min="0.1" max="1" step="0.1" value="${opacidad}" title="Opacidad">
    <button type="button" class="boton-icono" data-zoom title="Acercar a la capa"><i class="bi bi-zoom-in"></i></button>`;
  fila.querySelector("[type=checkbox]").addEventListener("change", (e) => alternar(e.target.checked));
  fila.querySelector("[type=range]").addEventListener("input", (e) => cambiarOpacidad(Number(e.target.value)));
  fila.querySelector("[data-zoom]").addEventListener("click", zoom);
  const boton = fila.querySelector(".capa-simbolo");
  boton.addEventListener("click", () => abrirPaleta(boton, {
    color, relleno, partes, ocultos,
    alCambiar: (nuevo) => {
      ({ color, relleno } = nuevo);
      ocultos = new Set(nuevo.ocultos);
      boton.setAttribute("style", simbolo(color, relleno));
      cambiarEstilo(nuevo);
      if (nombreCon) fila.querySelector(".capa-nombre").textContent = nombreCon(ocultos);
    },
  }));
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
    const guardar = () => guardarEstilo(`proyectos:${info.unidad.id}`, { color: info.color, relleno: info.relleno, opacidad: info.opacidad });
    toc.append(filaCapa({
      color: info.color,
      relleno: info.relleno,
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
        guardar();
      },
      cambiarEstilo: ({ color, relleno }) => {
        Object.assign(info, { color, relleno });
        info.grupo.setStyle((f) => estilo(f, info.opacidad));
        guardar();
      },
      zoom: () => ajustarA(info.grupo.getLayers()),
    }));
  });

  const tituloLimites = document.createElement("div");
  tituloLimites.className = "capa-grupo";
  tituloLimites.textContent = "Límites";
  toc.append(tituloLimites);
  Object.values(limites).forEach((info) => {
    const guardar = () => guardarEstilo(`limites:${info.def.id}`, { color: info.color, relleno: info.relleno,
                                                                     opacidad: info.opacidad, ocultos: [...info.ocultos] });
    const partes = partesDe(info.def.id);
    const nombreCon = (ocultos) => (partes && ocultos.size ? `${info.def.nombre} (${partes.length - ocultos.size} de ${partes.length})` : info.def.nombre);
    toc.append(filaCapa({
      color: info.color,
      relleno: info.relleno,
      partes,
      ocultos: info.ocultos,
      nombreCon,
      nombre: nombreCon(info.ocultos),
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
        info.grupo.setStyle(info.estilo());
        guardar();
      },
      cambiarEstilo: ({ color, relleno, ocultos }) => {
        Object.assign(info, { color, relleno, ocultos: new Set(ocultos) });
        dibujarLimite(info);
        guardar();
      },
      zoom: () => info.grupo.getLayers().length && mapa.fitBounds(info.grupo.getBounds()),
    }));
  });
}

export function iniciarCapas() {
  estado.config.unidades.forEach((unidad, i) => {
    const guardado = leerEstilos()[`proyectos:${unidad.id}`] || {};
    const info = { unidad, color: guardado.color || COLORES[i % COLORES.length], relleno: guardado.relleno ?? true,
                   visible: true, opacidad: guardado.opacidad ?? 1, cantidad: 0 };
    info.grupo = crearGrupoProyectos(info);
    proyectos[unidad.id] = info;
  });
  crearLimites();
  dibujarToc();
  on("seleccion", actualizarEstilos);
  on("filtros", recargarProyectos);
  recargarProyectos();
}

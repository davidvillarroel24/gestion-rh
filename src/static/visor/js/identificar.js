// Identificar: ficha del proyecto (o del límite) sobre el que se hace clic.

import { estado, on, seleccionar } from "./estado.js";
import { get } from "./api.js";
import { aUtm } from "./coordenadas.js";
import { abrirEditor } from "./editor-proyecto.js";
import { editarGeometria } from "./edicion.js";
import { getMapa } from "./mapa.js";
import { aviso, bs, esc, mensaje, panel, pct } from "./ui.js";

const fecha = (f) => (f ? new Date(`${f}T00:00:00`).toLocaleDateString("es-BO") : "—");

function barra(valor) {
  const v = Math.max(0, Math.min(100, Number(valor) || 0));
  return `<div class="barra" title="${pct(valor)}"><span style="width:${v}%"></span></div>`;
}

function filas(lista, columnas) {
  if (!lista.length) return '<p class="tenue">Sin registros.</p>';
  return `<table>${lista.map((x) => `<tr>${columnas.map((c) => `<td>${c(x)}</td>`).join("")}</tr>`).join("")}</table>`;
}

export async function mostrarFicha(id) {
  let p;
  try {
    p = await get(`proyectos/${id}/`);
  } catch (error) {
    aviso(error.message, "error");
    return;
  }
  seleccionar([id]);
  const html = `
    <div class="ficha">
      <div class="codigo">${esc(p.codigo)} · ${esc(p.unidad)}</div>
      <h3>${esc(p.nombre)}</h3>
      <dl>
        <dt>Estado</dt><dd>${esc(p.estado || "—")}</dd>
        <dt>Programa</dt><dd>${esc(p.programa || "—")}</dd>
        <dt>Tipo</dt><dd>${esc(p.tipo || "—")}</dd>
        <dt>Gestión</dt><dd>${esc(p.gestion ?? "—")}</dd>
        <dt>Municipios</dt><dd>${esc(p.municipios.join(", ") || "—")}</dd>
        <dt>Comunidad</dt><dd>${esc(p.comunidad || "—")}</dd>
        <dt>SISIN</dt><dd>${esc(p.sisin || "—")}</dd>
        <dt>Orden de proceder</dt><dd>${fecha(p.fecha_orden_proceder)}</dd>
        <dt>Conclusión</dt><dd>${fecha(p.fecha_conclusion)}${p.plazo_dias != null ? ` (${p.plazo_dias} días)` : ""}</dd>
      </dl>

      <h4>Avance</h4>
      <dl>
        <dt>Físico</dt><dd>${barra(p.avance_fisico)} ${pct(p.avance_fisico)}</dd>
        <dt>Financiero</dt><dd>${barra(p.avance_financiero)} ${pct(p.avance_financiero)}</dd>
        <dt>Costo total</dt><dd>Bs ${bs(p.costo_total)}</dd>
        <dt>Desembolsado</dt><dd>Bs ${bs(p.desembolsado)}</dd>
      </dl>

      <h4>Financiamiento</h4>
      ${filas(p.financiamiento, [(f) => esc(f.entidad), (f) => `Bs ${bs(f.comprometido)}`, (f) => `pagado ${bs(f.desembolsado)}`])}

      <h4>Último evento</h4>
      ${p.ultimo_evento ? `<p>${fecha(p.ultimo_evento.fecha)} · <strong>${esc(p.ultimo_evento.tipo)}</strong><br>${esc(p.ultimo_evento.descripcion)}</p>`
                        : '<p class="tenue">Sin eventos en la bitácora.</p>'}

      <h4>Indicadores</h4>
      ${filas(p.mediciones, [(m) => esc(m.indicador) + (m.desagregacion ? ` – ${esc(m.desagregacion)}` : ""),
                             (m) => esc(m.momento), (m) => esc(m.valor?.toLocaleString("es-BO"))])}

      <h4>Documentos</h4>
      ${filas(p.documentos, [(d) => `<a href="${esc(d.url)}"><i class="bi bi-download"></i> ${esc(d.nombre)}</a>`, (d) => esc(d.tipo)])}

      <p style="margin-top:12px;display:flex;gap:6px;flex-wrap:wrap">
        <a class="boton" href="${esc(window.VISOR.reportes)}ficha/?ids=${p.id}" target="_blank" rel="noopener">Ficha técnica</a>
        ${p.puede_editar ? '<button type="button" class="boton" data-editar-proyecto>Editar proyecto</button>' : ""}
      </p>
    </div>`;
  panel.abrir("Proyecto", html).querySelector("[data-editar-proyecto]")
    ?.addEventListener("click", () => abrirEditor({ proyectoId: p.id, titulo: `${p.codigo} – ${p.nombre}` }));
}

const FORMAS = { Point: "Punto", MultiPoint: "Puntos", LineString: "Línea", MultiLineString: "Líneas",
                 Polygon: "Polígono", MultiPolygon: "Polígonos" };
const num = (n, d = 2) => Number(n).toLocaleString("es-BO", { maximumFractionDigits: d, minimumFractionDigits: d });

function filasCoordenada(lat, lon, prefijo = "") {
  const u = aUtm(lat, lon);
  return `<dt>${prefijo}Lat, lon</dt><dd>${num(lat, 6)}, ${num(lon, 6)}</dd>
          <dt>${prefijo}UTM ${u.zona}</dt><dd>E ${num(u.este, 1)} · N ${num(u.norte, 1)}</dd>`;
}

// Clic en un punto, línea o polígono: datos de ESE elemento (no de todo el proyecto).
export function mostrarElemento(feature, capa) {
  const p = feature.properties;
  const tipo = feature.geometry.type;
  let medidas = "";
  if (tipo === "Point") {
    const [lon, lat] = feature.geometry.coordinates;
    medidas = filasCoordenada(lat, lon);
  } else {
    const vertices = turf.coordAll(feature).length;
    if (tipo.includes("Polygon")) {
      const area = turf.area(feature);
      const perimetro = turf.length(turf.polygonToLine(feature), { units: "kilometers" });
      medidas = `<dt>Área</dt><dd>${num(area / 10000)} ha</dd><dt>Perímetro</dt><dd>${num(perimetro * 1000, 0)} m</dd>
                 <dt>Vértices</dt><dd>${tipo === "Polygon" ? vertices - feature.geometry.coordinates.length : vertices}</dd>`;
    } else {
      medidas = `<dt>Longitud</dt><dd>${num(turf.length(feature, { units: "kilometers" }) * 1000, 0)} m</dd><dt>Vértices</dt><dd>${vertices}</dd>`;
    }
    const [lon, lat] = turf.centroid(feature).geometry.coordinates;
    medidas += filasCoordenada(lat, lon, "Centro: ");
  }
  const puedeEditar = estado.config.permisos.editar_geometria;
  const html = `
    <div class="ficha">
      <div class="codigo">${esc(p.tipo_elemento)} · ${FORMAS[tipo] || tipo}</div>
      <h3>${esc(p.nombre || "Sin nombre")}</h3>
      <dl>${medidas}</dl>
      <h4>Proyecto</h4>
      <dl>
        <dt>Código</dt><dd>${esc(p.codigo)}</dd>
        <dt>Nombre</dt><dd>${esc(p.proyecto)}</dd>
        <dt>Unidad</dt><dd>${esc(p.unidad)}</dd>
        <dt>Estado</dt><dd>${esc(p.estado || "—")}</dd>
      </dl>
      <p style="margin-top:12px;display:flex;gap:6px;flex-wrap:wrap">
        <button type="button" class="boton" data-ficha>Ficha del proyecto</button>
        ${puedeEditar ? '<button type="button" class="boton secundario" data-editar-geometria>Editar geometría</button>' : ""}
        <button type="button" class="boton secundario" data-zoom>Zoom</button>
      </p>
    </div>`;
  const contenido = panel.abrir("Elemento", html);
  contenido.querySelector("[data-ficha]").addEventListener("click", () => mostrarFicha(p.proyecto_id));
  contenido.querySelector("[data-editar-geometria]")?.addEventListener("click", () => editarGeometria(p.id));
  contenido.querySelector("[data-zoom]").addEventListener("click", () => {
    if (capa.getBounds) getMapa().fitBounds(capa.getBounds(), { maxZoom: 17 });
    else getMapa().setView(capa.getLatLng(), Math.max(getMapa().getZoom(), 16));
  });
}

function fichaLimite(capa, p) {
  const nombres = { regiones: "Región", provincias: "Provincia", municipios: "Municipio" };
  const filasExtra = capa === "municipios"
    ? `<dt>Código INE</dt><dd>${esc(p.codigo_ine || "—")}${p.es_tioc ? " (TIOC)" : ""}</dd>
       <dt>Provincia</dt><dd>${esc(p.provincia)}</dd><dt>Región</dt><dd>${esc(p.region)}</dd>`
    : "";
  panel.abrir(nombres[capa] || "Límite", `<div class="ficha"><h3>${esc(p.nombre)}</h3><dl>${filasExtra}
    <dt>Área</dt><dd>${Number(p.area_km2).toLocaleString("es-BO")} km²</dd></dl></div>`);
}

export function iniciarIdentificar() {
  on("modo", (modo) => {
    if (modo === "identificar") mensaje("Identificar: haga clic en un proyecto o en un límite.");
  });
  // Sin herramienta activa (o con «Identificar»): el clic muestra el elemento; Ctrl+clic solo suma a la selección.
  on("clic-geometria", ({ feature, capa, original }) => {
    if (estado.modo !== null && estado.modo !== "identificar") return;
    if (original?.ctrlKey || original?.metaKey) return;
    mostrarElemento(feature, capa);
  });
  on("clic-limite", ({ capa, propiedades }) => {
    if (estado.modo === "identificar") fichaLimite(capa, propiedades);
  });
  on("abrir-ficha", mostrarFicha);
}

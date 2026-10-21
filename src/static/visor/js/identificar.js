// Identificar: ficha del proyecto (o del límite) sobre el que se hace clic.

import { estado, on, seleccionar } from "./estado.js";
import { get } from "./api.js";
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

      ${p.url_admin ? `<p style="margin-top:12px"><a class="boton" href="${esc(p.url_admin)}" target="_blank" rel="noopener">Editar proyecto</a></p>` : ""}
    </div>`;
  panel.abrir("Proyecto", html);
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
  on("clic-geometria", ({ feature }) => {
    if (estado.modo === "identificar") mostrarFicha(feature.properties.proyecto_id);
  });
  on("clic-limite", ({ capa, propiedades }) => {
    if (estado.modo === "identificar") fichaLimite(capa, propiedades);
  });
  on("abrir-ficha", mostrarFicha);
}

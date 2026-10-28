// Punto de entrada del visor: carga la configuración, arma el mapa, los
// paneles y la cinta de herramientas.

import { emitir, estado, on, setModo } from "./estado.js";
import { get } from "./api.js";
import { capasDeProyectos, iniciarCapas, recargarProyectos } from "./capas.js";
import { iniciarCinta } from "./cinta.js";
import { irACoordenada } from "./coordenadas.js";
import { dibujar, editar, iniciarEdicion, porCoordenadas } from "./edicion.js";
import { enfocarFiltros, iniciarFiltros } from "./filtros.js";
import { iniciarIdentificar, mostrarFicha } from "./identificar.js";
import {
  agregarMarcador, ajustarA, borrarMarcador, crearMapa, getMapa, haySiguiente, hayAnterior, irAMarcador,
  irExtensionTotal, marcadores, setMapaBase, vistaAnterior, vistaSiguiente,
} from "./mapa.js";
import { iniciarMedir, limpiarMediciones } from "./medir.js";
import { iniciarSeleccion, limpiar, porRectangulo, porUbicacion, zoomSeleccion } from "./seleccion.js";
import { estaVisible, iniciarTabla, mostrar as mostrarTabla, recargar as recargarTabla } from "./tabla.js";
import { aviso, menu, mensaje, panel } from "./ui.js";

const V = window.VISOR;
const modo = (m) => () => setModo(m);
const enModo = (m) => () => estado.modo === m;
const permiso = (p) => () => Boolean(estado.config.permisos[p]);
const proximamente = (fase) => () => aviso(`Disponible en la ${fase}.`);

function cinta() {
  return [
    { pestana: "Mapa", grupos: [
      { titulo: "Navegar", botones: [
        { etiqueta: "Acercar", icono: "zoom-in", accion: () => getMapa().zoomIn() },
        { etiqueta: "Alejar", icono: "zoom-out", accion: () => getMapa().zoomOut() },
        { etiqueta: "Extensión total", icono: "arrows-fullscreen", accion: irExtensionTotal },
        { etiqueta: "Vista anterior", icono: "arrow-left-circle", accion: vistaAnterior, habilitado: hayAnterior },
        { etiqueta: "Vista siguiente", icono: "arrow-right-circle", accion: vistaSiguiente, habilitado: haySiguiente },
        { etiqueta: "Marcadores", icono: "bookmark-star", accion: (b) => menu(b, [
          { etiqueta: "Guardar vista actual…", icono: "plus-lg", accion: agregarMarcador },
          ...(marcadores().length ? ["-"] : []),
          ...marcadores().map((m) => ({ etiqueta: m.nombre, icono: "geo-alt", accion: () => irAMarcador(m) })),
          ...(marcadores().length ? ["-", { etiqueta: "Borrar un marcador…", icono: "trash", accion: () => {
            const nombre = prompt(`Nombre del marcador a borrar:\n${marcadores().map((m) => m.nombre).join(", ")}`);
            const i = marcadores().findIndex((m) => m.nombre === nombre);
            if (i >= 0) borrarMarcador(i);
          } }] : []),
        ]) },
      ] },
      { titulo: "Mapa base", botones: [
        { etiqueta: "Mapa base", icono: "map", accion: (b) => menu(b, estado.config.mapas_base.map((m) => ({
          etiqueta: m.nombre, icono: estado.mapaBase === m.id ? "check2" : "", accion: () => setMapaBase(m.id) }))) },
      ] },
      { titulo: "Paneles", botones: [
        { etiqueta: "Capas y filtros", icono: "layers", activo: () => !document.getElementById("visor").classList.contains("sin-capas"),
          accion: () => { document.getElementById("visor").classList.toggle("sin-capas"); emitir("distribucion"); } },
        { etiqueta: "Tabla de atributos", icono: "table", activo: estaVisible, accion: () => mostrarTabla() },
        { etiqueta: "Actualizar datos", icono: "arrow-clockwise", accion: () => { recargarProyectos(); recargarTabla(); } },
      ] },
    ] },
    { pestana: "Selección", grupos: [
      { titulo: "Seleccionar", botones: [
        { etiqueta: "Por rectángulo", icono: "bounding-box", accion: porRectangulo, activo: enModo("seleccion-rectangulo") },
        { etiqueta: "Por atributos", icono: "funnel", accion: enfocarFiltros, ayuda: "Filtrar por unidad, estado, municipio, gestión o texto" },
        { etiqueta: "Por ubicación", icono: "pin-map", accion: porUbicacion, ayuda: "Proyectos dentro de un municipio" },
      ] },
      { titulo: "Selección actual", botones: [
        { etiqueta: "Zoom a selección", icono: "zoom-in", accion: zoomSeleccion, habilitado: () => estado.seleccion.size > 0 },
        { etiqueta: "Limpiar selección", icono: "x-square", accion: limpiar, habilitado: () => estado.seleccion.size > 0 },
      ] },
    ] },
    { pestana: "Edición", grupos: [
      { titulo: "Dibujar a mano", botones: [
        { etiqueta: "Punto", icono: "geo-alt", accion: () => dibujar("Point"), habilitado: permiso("crear_geometria") },
        { etiqueta: "Varios puntos", icono: "geo", accion: () => dibujar("Point", { continuo: true }), habilitado: permiso("crear_geometria") },
        { etiqueta: "Línea", icono: "bezier2", accion: () => dibujar("LineString"), habilitado: permiso("crear_geometria") },
        { etiqueta: "Polígono", icono: "pentagon", accion: () => dibujar("Polygon"), habilitado: permiso("crear_geometria") },
      ] },
      { titulo: "Otras formas", botones: [
        { etiqueta: "Por coordenadas", icono: "123", accion: porCoordenadas, habilitado: permiso("crear_geometria") },
      ] },
      { titulo: "Modificar", botones: [
        { etiqueta: "Editar / eliminar", icono: "pencil-square", accion: editar, activo: enModo("editar"), habilitado: permiso("editar_geometria") },
      ] },
    ] },
    { pestana: "Datos", grupos: [
      { titulo: "Proyectos", botones: [
        { etiqueta: "Tabla de atributos", icono: "table", activo: estaVisible, accion: () => mostrarTabla() },
        { etiqueta: "Nuevo proyecto", icono: "plus-square", habilitado: permiso("crear_proyecto"),
          accion: () => window.open(`${V.admin}proyectos/proyecto/add/`, "_blank") },
      ] },
      { titulo: "Intercambio", botones: [
        { etiqueta: "Importar", icono: "box-arrow-in-down", accion: () => window.open(V.importar, "_blank") },
        { etiqueta: "Plantillas Excel", icono: "file-earmark-spreadsheet", accion: () => window.open(`${V.importar}#plantillas`, "_blank") },
        { etiqueta: "Exportar", icono: "box-arrow-up", accion: (b) => menu(b, [
          { etiqueta: "Excel – proyectos filtrados", icono: "file-earmark-excel", accion: () => exportar("excel/") },
          { etiqueta: "Excel – solo la selección", icono: "check2-square", accion: () => exportar("excel/", true) },
          "-",
          { etiqueta: "GeoJSON – geometrías filtradas", icono: "filetype-json", accion: () => exportar("geojson/") },
          { etiqueta: "KML (Google Earth) – geometrías filtradas", icono: "globe-americas", accion: () => exportar("kml/") },
        ]) },
      ] },
    ] },
    { pestana: "Análisis", grupos: [
      { titulo: "Consultar", botones: [
        { etiqueta: "Identificar", icono: "info-circle", accion: modo("identificar"), activo: enModo("identificar") },
        { etiqueta: "Ir a coordenada", icono: "crosshair", accion: irACoordenada },
      ] },
      { titulo: "Medir", botones: [
        { etiqueta: "Distancia", icono: "rulers", accion: modo("medir-distancia"), activo: enModo("medir-distancia") },
        { etiqueta: "Área", icono: "bounding-box-circles", accion: modo("medir-area"), activo: enModo("medir-area") },
        { etiqueta: "Borrar medidas", icono: "eraser", accion: limpiarMediciones },
      ] },
      { titulo: "Resumen", botones: [
        { etiqueta: "Tarjetas y gráficas", icono: "bar-chart", accion: () => abrirReportes() },
        { etiqueta: "Alertas", icono: "exclamation-triangle", accion: () => abrirReportes({}, "#alertas") },
      ] },
    ] },
    { pestana: "Reportes", grupos: [
      { titulo: "Imprimir", botones: [
        { etiqueta: "Imprimir mapa", icono: "printer", accion: () => window.print() },
      ] },
      { titulo: "Reportes", botones: [
        { etiqueta: "Ficha técnica", icono: "file-earmark-text", accion: proximamente("Fase 10") },
        { etiqueta: "Por municipio", icono: "file-earmark-bar-graph", accion: () => abrirReportes({ por: "municipio" }) },
        { etiqueta: "Por fuente", icono: "cash-coin", accion: () => abrirReportes({ por: "fuente" }) },
      ] },
    ] },
    { pestana: "Administración", grupos: [
      { titulo: "Sistema", botones: [
        { etiqueta: "Administración", icono: "gear", visible: permiso("administracion"), accion: () => window.open(V.admin, "_blank") },
        { etiqueta: "Catálogos", icono: "list-ul", visible: permiso("administracion"), accion: () => window.open(`${V.admin}proyectos/`, "_blank") },
        { etiqueta: "Usuarios", icono: "people", visible: permiso("administracion"), accion: () => window.open(`${V.admin}core/usuario/`, "_blank") },
      ] },
      { titulo: "Sesión", botones: [
        { etiqueta: "Salir", icono: "box-arrow-right", accion: salir },
      ] },
    ] },
  ];
}

// Reportes con los mismos filtros del visor, en otra pestaña.
function abrirReportes(extra = {}, ancla = "") {
  window.open(`${V.reportes}?${new URLSearchParams({ ...estado.filtros, ...extra })}${ancla}`, "_blank");
}

// Descarga con los mismos filtros del visor (y solo la selección si se pide).
function exportar(ruta, soloSeleccion = false) {
  if (soloSeleccion && !estado.seleccion.size) {
    aviso("No hay proyectos seleccionados.");
    return;
  }
  const parametros = new URLSearchParams(estado.filtros);
  if (soloSeleccion) parametros.set("ids", [...estado.seleccion].join(","));
  window.location.href = `${V.importar}exportar/${ruta}?${parametros}`;
}

function salir() {
  const formulario = document.createElement("form");
  formulario.method = "post";
  formulario.action = V.salir;
  formulario.append(document.querySelector("[name=csrfmiddlewaretoken]").cloneNode());
  document.body.append(formulario);
  formulario.submit();
}

// Herramientas de dibujo (medir, rectángulo, dibujar) se apagan al cambiar de modo o con Esc.
function iniciarModos() {
  const mapa = getMapa();
  mapa.on("pm:create", (e) => emitir("dibujo-creado", { layer: e.layer, forma: e.shape, modo: estado.modo }));
  on("modo", (m) => {
    if (m !== "dibujar") mapa.pm.disableDraw();
    if (m === null) mensaje("");
    document.getElementById("mapa").style.cursor = m ? "crosshair" : "";
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    mapa.pm.disableDraw();
    if (estado.modo === "dibujar") panel.cerrar();
    else setModo(null, { alternar: false });
  });
}

async function iniciar() {
  try {
    estado.config = await get("config/");
  } catch (error) {
    aviso(`No se pudo iniciar el visor: ${error.message}`, "error");
    return;
  }
  document.getElementById("estado-usuario").textContent =
    `${estado.config.usuario.nombre}${estado.config.usuario.roles.length ? ` · ${estado.config.usuario.roles.join(", ")}` : ""}`;
  crearMapa();
  iniciarModos();
  iniciarFiltros();
  iniciarCapas();
  iniciarTabla();
  iniciarSeleccion();
  iniciarIdentificar();
  iniciarMedir();
  iniciarEdicion();
  iniciarCinta(cinta());
  abrirProyectoDeLaUrl();
}

// /visor/?proyecto=<id> (enlaces de las alertas): abre su ficha y acerca a sus geometrías.
function abrirProyectoDeLaUrl() {
  const id = Number(new URLSearchParams(location.search).get("proyecto"));
  if (!id) return;
  mostrarFicha(id);
  let pendiente = true; // solo la primera carga: después el usuario navega libre
  on("proyectos-cargados", () => {
    if (!pendiente) return;
    pendiente = false;
    const capas = capasDeProyectos(new Set([id]));
    if (capas.length) ajustarA(capas);
  });
}

iniciar();

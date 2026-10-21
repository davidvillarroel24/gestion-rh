// Edición de geometrías (D23): dibujar a mano punto / varios puntos / línea /
// polígono, cargar por coordenadas, y editar o eliminar una existente.
// Cada geometría pertenece a un proyecto y tiene un tipo de elemento.

import { estado, on, setModo } from "./estado.js";
import { enviar, textoError } from "./api.js";
import { capaDeGeometria, recargarProyectos } from "./capas.js";
import { aLatLng, camposCoordenadas, enlazarEtiquetas } from "./coordenadas.js";
import { getMapa } from "./mapa.js";
import { aviso, esc, mensaje, nodo, opciones, panel } from "./ui.js";

const FORMA_GEOMAN = { Point: "Marker", LineString: "Line", Polygon: "Polygon" };
const NOMBRE_FORMA = { Point: "punto", LineString: "línea", Polygon: "polígono" };

let contexto = null;  // { proyecto, tipo_elemento, nombre, tipo, continuo } mientras se dibuja
let enEdicion = null; // capa que se está editando

const proyectoPorId = (id) => estado.filas.find((f) => f.id === Number(id));

function tiposPara(proyectoId, tipoGeometria) {
  const p = proyectoPorId(proyectoId);
  if (!p) return [];
  return estado.config.tipos_elemento.filter((t) => t.unidad === p.unidad_id && (!tipoGeometria || t.tipo_geometria === tipoGeometria));
}

function campoProyectoYTipo(tipoGeometria) {
  const preseleccion = estado.seleccion.size === 1 ? [...estado.seleccion][0] : null;
  const proyectos = estado.filas.map((f) => ({ id: f.id, nombre: `${f.codigo} – ${f.nombre}` }));
  return `
    <label>Proyecto<select name="proyecto" required>${opciones(proyectos, { vacio: "Elija un proyecto…", seleccionado: preseleccion })}</select></label>
    <label>Tipo de elemento<select name="tipo_elemento" required></select></label>
    <p class="tenue" data-sin-tipos hidden>Este proyecto no tiene tipos de elemento de ${NOMBRE_FORMA[tipoGeometria]} en su unidad.
      Créelo en Administración → Tipos de elemento.</p>
    <label>Nombre (opcional)<input name="nombre" maxlength="150"></label>`;
}

function enlazarTipos(formulario, tipoGeometria) {
  const actualizar = () => {
    const tipos = tiposPara(formulario.proyecto.value, tipoGeometria);
    formulario.tipo_elemento.innerHTML = opciones(tipos);
    formulario.querySelector("[data-sin-tipos]").hidden = !formulario.proyecto.value || tipos.length > 0;
  };
  formulario.proyecto.addEventListener("change", actualizar);
  actualizar();
}

function puedeCrear() {
  if (!estado.config.permisos.crear_geometria) {
    aviso("Su rol no permite dibujar geometrías.", "error");
    return false;
  }
  if (!estado.filas.length) {
    aviso("No hay proyectos visibles. Cree uno primero (Datos → Nuevo proyecto) o revise los filtros.", "error");
    return false;
  }
  return true;
}

async function crear(datos, geometry) {
  try {
    await enviar("POST", "geometrias/", { ...datos, geometry });
    aviso("Geometría guardada.", "ok");
    recargarProyectos();
    return true;
  } catch (error) {
    aviso(`No se guardó: ${textoError(error)}`, "error");
    return false;
  }
}

// ---------------------------------------------------------------- dibujar a mano

export function dibujar(tipoGeometria, { continuo = false } = {}) {
  if (!puedeCrear()) return;
  const titulo = continuo ? "Dibujar varios puntos" : `Dibujar ${NOMBRE_FORMA[tipoGeometria]}`;
  const formulario = nodo(`<form class="formulario">${campoProyectoYTipo(tipoGeometria)}
    <div class="acciones"><button class="boton">Empezar a dibujar</button></div></form>`);
  enlazarTipos(formulario, tipoGeometria);
  formulario.addEventListener("submit", (e) => {
    e.preventDefault();
    if (!formulario.tipo_elemento.value) return;
    contexto = {
      proyecto: Number(formulario.proyecto.value),
      tipo_elemento: Number(formulario.tipo_elemento.value),
      nombre: formulario.nombre.value,
      tipo: tipoGeometria,
      continuo,
    };
    setModo("dibujar", { alternar: false });
    getMapa().pm.enableDraw(FORMA_GEOMAN[tipoGeometria], { continueDrawing: continuo });
    formulario.querySelector(".acciones").innerHTML =
      `<span class="tenue">${continuo ? "Haga clic en cada punto. " : ""}Esc o «Terminar» para salir.</span>
       <button type="button" class="boton secundario" data-terminar>Terminar</button>`;
    formulario.querySelector("[data-terminar]").addEventListener("click", () => panel.cerrar());
    mensaje(`Dibujando ${NOMBRE_FORMA[tipoGeometria]} para el proyecto elegido.`);
  });
  panel.abrir(titulo, formulario, { alCerrar: terminarDibujo });
}

function terminarDibujo() {
  contexto = null;
  if (estado.modo === "dibujar") setModo(null, { alternar: false });
}

// ---------------------------------------------------------------- por coordenadas (puntos)

export function porCoordenadas() {
  if (!puedeCrear()) return;
  const formulario = nodo(`<form class="formulario">${campoProyectoYTipo("Point")}${camposCoordenadas()}
    <div class="acciones"><button class="boton">Guardar punto</button></div>
    <p class="tenue">El formulario queda abierto para cargar varios puntos seguidos.</p></form>`);
  enlazarTipos(formulario, "Point");
  enlazarEtiquetas(formulario);
  formulario.addEventListener("submit", async (e) => {
    e.preventDefault();
    let latlng;
    try {
      latlng = aLatLng(formulario.sistema.value, formulario.x.value, formulario.y.value);
    } catch (error) {
      aviso(error.message, "error");
      return;
    }
    const ok = await crear({
      proyecto: Number(formulario.proyecto.value),
      tipo_elemento: Number(formulario.tipo_elemento.value),
      nombre: formulario.nombre.value,
    }, { type: "Point", coordinates: [latlng[1], latlng[0]] });
    if (ok) {
      formulario.x.value = "";
      formulario.y.value = "";
      formulario.nombre.value = "";
      getMapa().setView(latlng, Math.max(getMapa().getZoom(), 14));
    }
  });
  panel.abrir("Punto por coordenadas", formulario);
}

// ---------------------------------------------------------------- editar / eliminar existente

export function editar() {
  if (!estado.config.permisos.editar_geometria) {
    aviso("Su rol no permite editar geometrías.", "error");
    return;
  }
  setModo("editar");
}

function activarEdicion(capa) {
  desactivarEdicion();
  enEdicion = capa;
  const p = capa.feature.properties;
  const tipoGeometria = capa.feature.geometry.type;
  if (tipoGeometria === "Point") capa.pm.enableLayerDrag();
  else capa.pm.enable({ allowSelfIntersection: false });

  const tipos = tiposPara(p.proyecto_id, tipoGeometria);
  const formulario = nodo(`<form class="formulario">
    <p><strong>${esc(p.codigo)}</strong> – ${esc(p.proyecto)}</p>
    <p class="tenue">${tipoGeometria === "Point" ? "Arrastre el punto" : "Mueva los vértices"} y guarde.</p>
    <label>Tipo de elemento<select name="tipo_elemento">${opciones(tipos, { seleccionado: p.tipo_elemento_id })}</select></label>
    <label>Nombre<input name="nombre" maxlength="150" value="${esc(p.nombre)}"></label>
    <div class="acciones">
      <button class="boton">Guardar</button>
      <button type="button" class="boton secundario" data-cancelar>Cancelar</button>
      ${estado.config.permisos.borrar_geometria ? '<button type="button" class="boton peligro" data-eliminar>Eliminar</button>' : ""}
    </div></form>`);

  formulario.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await enviar("PATCH", `geometrias/${p.id}/`, {
        geometry: capa.toGeoJSON().geometry,
        tipo_elemento: Number(formulario.tipo_elemento.value),
        nombre: formulario.nombre.value,
      });
      aviso("Cambios guardados.", "ok");
      panel.cerrar();
    } catch (error) {
      aviso(`No se guardó: ${textoError(error)}`, "error");
    }
  });
  formulario.querySelector("[data-cancelar]").addEventListener("click", () => panel.cerrar());
  formulario.querySelector("[data-eliminar]")?.addEventListener("click", async () => {
    if (!confirm("¿Eliminar esta geometría? Queda registrada en el historial.")) return;
    try {
      await enviar("DELETE", `geometrias/${p.id}/`);
      aviso("Geometría eliminada.", "ok");
      panel.cerrar();
    } catch (error) {
      aviso(error.message, "error");
    }
  });
  panel.abrir("Editar geometría", formulario, {
    alCerrar: () => {
      desactivarEdicion();
      recargarProyectos(); // descarta cambios no guardados y muestra lo guardado
      if (estado.modo === "editar") setModo(null, { alternar: false });
    },
  });
}

function desactivarEdicion() {
  if (!enEdicion) return;
  enEdicion.pm.disable();
  enEdicion.pm.disableLayerDrag?.();
  enEdicion = null;
}

export function editarGeometria(id) {
  const capa = capaDeGeometria(id);
  if (capa) activarEdicion(capa);
}

export function iniciarEdicion() {
  on("modo", (modo) => {
    if (modo === "editar") mensaje("Editar: haga clic en la geometría que quiere modificar.");
    if (modo !== "dibujar") contexto = null;
  });
  on("clic-geometria", ({ capa }) => {
    if (estado.modo === "editar" && !enEdicion) activarEdicion(capa);
  });
  on("dibujo-creado", async ({ layer, modo }) => {
    if (modo !== "dibujar" || !contexto) return;
    const datos = { proyecto: contexto.proyecto, tipo_elemento: contexto.tipo_elemento, nombre: contexto.nombre };
    const geometry = layer.toGeoJSON().geometry;
    layer.remove();
    await crear(datos, geometry);
    if (!contexto?.continuo) panel.cerrar();
  });
}

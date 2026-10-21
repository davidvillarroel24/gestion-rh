// Selección de proyectos: clic, rectángulo, por ubicación (municipio), limpiar, zoom.

import { alternarSeleccion, estado, on, seleccionar, setModo } from "./estado.js";
import { get } from "./api.js";
import { capasDeProyectos, geometriasVisibles } from "./capas.js";
import { ajustarA, getMapa } from "./mapa.js";
import { aviso, menu, mensaje } from "./ui.js";

export function porRectangulo() {
  setModo("seleccion-rectangulo");
}

export function limpiar() {
  seleccionar([]);
}

export function zoomSeleccion() {
  if (!estado.seleccion.size) {
    aviso("No hay proyectos seleccionados.");
    return;
  }
  ajustarA(capasDeProyectos(estado.seleccion));
}

export function porUbicacion(boton) {
  menu(boton, estado.config.municipios.map((m) => ({
    etiqueta: m.nombre,
    accion: async () => {
      try {
        const { filas } = await get("proyectos/", { ...estado.filtros, municipio: m.id });
        seleccionar(filas.map((f) => f.id));
        aviso(`${filas.length} proyecto(s) en ${m.nombre}.`, "ok");
        zoomSeleccion();
      } catch (error) {
        aviso(error.message, "error");
      }
    },
  })));
}

export function iniciarSeleccion() {
  const mapa = getMapa();

  // Clic sobre una geometría sin herramienta activa: selecciona su proyecto (Ctrl suma).
  on("clic-geometria", ({ feature, original }) => {
    if (estado.modo !== null) return;
    const id = feature.properties.proyecto_id;
    if (original.ctrlKey || original.metaKey) alternarSeleccion(id);
    else seleccionar([id]);
  });

  // Rectángulo arrastrando (como en ArcGIS): mientras está activo el mapa no se desplaza.
  let inicio = null;
  let caja = null;

  on("modo", (modo) => {
    if (modo === "seleccion-rectangulo") {
      mensaje("Seleccionar: arrastre un rectángulo sobre el mapa (Esc para cancelar).");
      mapa.dragging.disable();
    } else {
      mapa.dragging.enable();
      caja?.remove();
      caja = null;
      inicio = null;
    }
  });

  // Eventos nativos del contenedor: el "mouseup" de Leaflet no siempre llega al soltar.
  const contenedor = mapa.getContainer();

  L.DomEvent.on(contenedor, "mousedown", (e) => {
    if (estado.modo !== "seleccion-rectangulo" || e.button !== 0) return;
    e.preventDefault(); // que el arrastre no seleccione texto de la página
    inicio = mapa.mouseEventToLatLng(e);
    caja = L.rectangle(L.latLngBounds(inicio, inicio), { color: "#7a5c00", weight: 1, dashArray: "4 3", fillOpacity: 0.1, interactive: false }).addTo(mapa);
  });

  L.DomEvent.on(contenedor, "mousemove", (e) => {
    if (inicio && caja) caja.setBounds(L.latLngBounds(inicio, mapa.mouseEventToLatLng(e)));
  });

  L.DomEvent.on(document, "mouseup", (e) => {
    if (estado.modo !== "seleccion-rectangulo" || !inicio) return;
    const limites = L.latLngBounds(inicio, mapa.mouseEventToLatLng(e));
    const rectangulo = turf.bboxPolygon([limites.getWest(), limites.getSouth(), limites.getEast(), limites.getNorth()]);
    const ids = new Set();
    geometriasVisibles().forEach((capa) => {
      if (turf.booleanIntersects(capa.toGeoJSON(), rectangulo)) ids.add(capa.feature.properties.proyecto_id);
    });
    seleccionar([...ids]);
    aviso(`${ids.size} proyecto(s) seleccionados.`, ids.size ? "ok" : "");
    setModo(null, { alternar: false });
  });
}

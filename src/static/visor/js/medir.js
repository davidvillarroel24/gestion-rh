// Medir distancia y área sobre el mapa (cálculo geodésico con turf).

import { on } from "./estado.js";
import { getMapa } from "./mapa.js";
import { mensaje } from "./ui.js";

let mediciones = null;

const km = (n) => n.toLocaleString("es-BO", { maximumFractionDigits: 3 });

function etiqueta(geojson) {
  if (geojson.geometry.type === "LineString") {
    const largo = turf.length(geojson, { units: "kilometers" });
    return largo < 1 ? `${km(largo * 1000)} m` : `${km(largo)} km`;
  }
  const metros = turf.area(geojson);
  return `${km(metros / 10000)} ha · ${km(metros / 1e6)} km²`;
}

export function limpiarMediciones() {
  mediciones?.clearLayers();
}

export function iniciarMedir() {
  const mapa = getMapa();
  mediciones = L.featureGroup().addTo(mapa);

  on("modo", (modo) => {
    if (modo === "medir-distancia") {
      mensaje("Medir distancia: clic para agregar puntos, clic en el último para terminar.");
      mapa.pm.enableDraw("Line", { continueDrawing: true, pathOptions: { color: "#e4572e", dashArray: "6 4" } });
    } else if (modo === "medir-area") {
      mensaje("Medir área: dibuje el polígono y ciérrelo en el primer punto.");
      mapa.pm.enableDraw("Polygon", { continueDrawing: true, pathOptions: { color: "#e4572e", dashArray: "6 4" } });
    }
  });

  on("dibujo-creado", ({ layer, modo }) => {
    if (modo !== "medir-distancia" && modo !== "medir-area") return;
    layer.setStyle?.({ color: "#e4572e", dashArray: "6 4" });
    mediciones.addLayer(layer);
    layer.bindTooltip(etiqueta(layer.toGeoJSON()), { permanent: true, className: "etiqueta-medida", direction: "center" }).openTooltip();
  });
}

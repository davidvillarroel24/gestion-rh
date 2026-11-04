// Ficha técnica: un mapa estático por ficha (proyectos sobre OpenStreetMap) y el botón de imprimir.
(function () {
  "use strict";

  const colecciones = JSON.parse(document.getElementById("geojson-fichas").textContent);
  const EXTENSION_DEPARTAMENTO = [[-18.6, -67.2], [-16.2, -64.2]];

  document.querySelectorAll(".mapa-ficha").forEach((div) => {
    const mapa = L.map(div, { zoomControl: false, attributionControl: true, dragging: false, scrollWheelZoom: false,
                              doubleClickZoom: false, boxZoom: false, keyboard: false, touchZoom: false });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                { maxZoom: 18, attribution: "© OpenStreetMap" }).addTo(mapa);
    const capa = L.geoJSON(colecciones[Number(div.dataset.indice)], {
      style: { color: "#0b6e4f", weight: 2, fillOpacity: 0.25 },
      pointToLayer: (_, latlng) => L.circleMarker(latlng, { radius: 6, color: "#fff", weight: 1.5, fillColor: "#0b6e4f", fillOpacity: 1 }),
    }).addTo(mapa);
    if (capa.getLayers().length) mapa.fitBounds(capa.getBounds(), { padding: [25, 25], maxZoom: 14 });
    else mapa.fitBounds(EXTENSION_DEPARTAMENTO);
  });

  document.getElementById("imprimir")?.addEventListener("click", () => window.print());
})();

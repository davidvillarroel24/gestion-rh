// Editor de una geometría existente (D23, plan 2026-11-18): herramientas visibles para mover,
// agregar y quitar vértices, mover todo (arrastrando o por coordenada del centro), tabla de
// vértices editable con pegado desde Excel, números de vértice en el mapa, medidas en vivo y
// deshacer / rehacer. Trabaja sobre la capa del mapa; guardar y cancelar los maneja edicion.js.

import { aLatLng, aUtm, SISTEMAS, zonaUtm } from "./coordenadas.js";
import { on } from "./estado.js";
import { getMapa } from "./mapa.js";
import { aviso, esc, mensaje, nodo } from "./ui.js";

const MINIMO = { Polygon: 3, LineString: 2 };
const MAX_ETIQUETAS = 400;
const num = (n, d) => Number(n).toLocaleString("es-BO", { maximumFractionDigits: d, minimumFractionDigits: d });
const AYUDA = {
  mover: "Arrastre los vértices. Para agregar uno, arrastre o haga clic en los puntos intermedios.",
  agregar: "Haga clic en el mapa: el vértice se inserta en el borde más cercano y la forma crece hacia ahí.",
  quitar: "Haga clic en un vértice para quitarlo.",
  todo: "Arrastre la forma completa, o escriba abajo la coordenada del nuevo centro.",
};

export function crearEditorGeometria(capa) {
  const mapa = getMapa();
  const forma = capa.feature.geometry.type; // Point | LineString | Polygon
  const esPunto = forma === "Point";
  let herramienta = esPunto ? "todo" : "mover";
  let pila = [];
  let posicion = -1;
  const quitarOyentes = [];
  if (!mapa.getPane("etiquetas")) mapa.createPane("etiquetas").style.zIndex = 650;
  const etiquetas = L.layerGroup().addTo(mapa);

  // ---- vértices de la parte editable (anillo exterior en polígonos; los huecos se conservan)
  const vertices = () => {
    if (esPunto) return [capa.getLatLng()];
    const latlngs = capa.getLatLngs();
    return (forma === "Polygon" ? latlngs[0] : latlngs).map((ll) => L.latLng(ll.lat, ll.lng));
  };
  function poner(lista) {
    if (esPunto) capa.setLatLng(lista[0]);
    else if (forma === "Polygon") {
      const anillos = capa.getLatLngs();
      anillos[0] = lista;
      capa.setLatLngs(anillos);
    } else capa.setLatLngs(lista);
    activarHerramienta(); // Geoman reconstruye sus marcadores con la forma nueva
    cambio();
  }

  // ---- historial (deshacer / rehacer)
  const foto = () => vertices().map((ll) => [ll.lat, ll.lng]);
  function registrar() {
    const actual = foto();
    if (JSON.stringify(actual) === JSON.stringify(pila[posicion])) return; // Geoman a veces avisa dos veces
    pila = pila.slice(0, posicion + 1);
    pila.push(actual);
    posicion = pila.length - 1;
  }
  function irA(nueva) {
    if (nueva < 0 || nueva >= pila.length) return;
    posicion = nueva;
    const lista = pila[posicion].map(([lat, lng]) => L.latLng(lat, lng));
    if (esPunto) capa.setLatLng(lista[0]);
    else if (forma === "Polygon") {
      const anillos = capa.getLatLngs();
      anillos[0] = lista;
      capa.setLatLngs(anillos);
    } else capa.setLatLngs(lista);
    activarHerramienta();
    refrescar();
  }

  // ---- panel
  const panel = nodo(`<div class="editor-geometria">
    ${esPunto ? "" : `<div class="herramientas" role="group" aria-label="Herramientas">
      <button type="button" data-h="mover"><i class="bi bi-arrows-move"></i> Mover puntos</button>
      <button type="button" data-h="agregar"><i class="bi bi-plus-circle"></i> Agregar puntos</button>
      <button type="button" data-h="quitar"><i class="bi bi-dash-circle"></i> Quitar puntos</button>
      <button type="button" data-h="todo"><i class="bi bi-arrows-fullscreen"></i> Mover todo</button>
    </div>`}
    <p class="tenue ayuda-herramienta"></p>
    <div class="deshacer">
      <button type="button" class="boton secundario" data-deshacer title="Ctrl+Z"><i class="bi bi-arrow-counterclockwise"></i> Deshacer</button>
      <button type="button" class="boton secundario" data-rehacer title="Ctrl+Y"><i class="bi bi-arrow-clockwise"></i> Rehacer</button>
    </div>
    <dl class="medidas"></dl>
    <fieldset class="centro">
      <legend>${esPunto ? "Coordenada del punto" : "Mover todo a un nuevo centro"}</legend>
      <select name="sistema">${SISTEMAS.map((s) => `<option value="${s.id}">${esc(s.nombre)}</option>`).join("")}</select>
      <div class="fila-coordenadas"><input name="x" inputmode="decimal" aria-label="Coordenada 1"><input name="y" inputmode="decimal" aria-label="Coordenada 2">
        <button type="button" class="boton secundario" data-mover-centro>Mover aquí</button></div>
    </fieldset>
    ${esPunto ? "" : `<details class="vertices" open>
      <summary>Vértices (<span data-cantidad></span>)</summary>
      <div class="tabla-vertices"><table><thead><tr><th>#</th><th data-c1></th><th data-c2></th><th></th></tr></thead><tbody></tbody></table></div>
      <details class="pegar"><summary>Pegar coordenadas desde Excel</summary>
        <p class="tenue">Una fila por vértice, dos columnas (en el sistema elegido arriba). Reemplaza todos los vértices.</p>
        <textarea rows="5" placeholder="-17.3912\t-66.1568"></textarea>
        <button type="button" class="boton secundario" data-pegar>Reemplazar vértices</button>
      </details>
    </details>`}
  </div>`);

  const sistema = panel.querySelector("[name=sistema]");
  const enUtm = () => sistema.value !== "WGS84";
  function aSistema(ll) {
    if (!enUtm()) return [ll.lat, ll.lng];
    const [este, norte] = proj4("EPSG:4326", sistema.value, [ll.lng, ll.lat]);
    return [este, norte];
  }
  sistema.value = "WGS84";
  sistema.addEventListener("change", refrescar);

  // ---- herramientas
  function activarHerramienta() {
    capa.pm.disable();
    capa.pm.disableLayerDrag?.();
    mapa.getContainer().classList.toggle("cursor-agregar", herramienta === "agregar");
    if (herramienta === "mover") capa.pm.enable({ allowSelfIntersection: false, removeLayerBelowMinVertexCount: false });
    if (herramienta === "quitar") {
      capa.pm.enable({ allowSelfIntersection: false, removeLayerBelowMinVertexCount: false, removeVertexOn: "click", draggable: false });
    }
    if (herramienta === "todo") capa.pm.enableLayerDrag();
    panel.querySelectorAll("[data-h]").forEach((b) => b.classList.toggle("activo", b.dataset.h === herramienta));
    panel.querySelector(".ayuda-herramienta").textContent = esPunto ? "Arrastre el punto o escriba su coordenada." : AYUDA[herramienta];
    mensaje(esPunto ? "Editar punto" : `Editar: ${AYUDA[herramienta]}`);
  }
  panel.querySelectorAll("[data-h]").forEach((b) => b.addEventListener("click", () => {
    herramienta = b.dataset.h;
    activarHerramienta();
  }));

  // Agregar: inserta el clic en el borde más cercano (en polígonos, cualquier borde; en líneas, también al inicio o al final).
  function agregar(latlng) {
    if (herramienta !== "agregar") return;
    const lista = vertices();
    const p = mapa.latLngToLayerPoint(latlng);
    const pts = lista.map((ll) => mapa.latLngToLayerPoint(ll));
    const cerrado = forma === "Polygon";
    let mejor = { distancia: Infinity, despues: lista.length - 1 };
    const tramos = cerrado ? pts.length : pts.length - 1;
    for (let i = 0; i < tramos; i++) {
      const d = L.LineUtil.pointToSegmentDistance(p, pts[i], pts[(i + 1) % pts.length]);
      if (d < mejor.distancia) mejor = { distancia: d, despues: i };
    }
    if (!cerrado) { // más cerca de un extremo que de cualquier tramo: se agrega afuera, al inicio o al final
      if (p.distanceTo(pts[0]) <= mejor.distancia + 0.5 && mejor.despues === 0) mejor.despues = -1;
      else if (p.distanceTo(pts[pts.length - 1]) <= mejor.distancia + 0.5 && mejor.despues === pts.length - 2) mejor.despues = pts.length - 1;
    }
    lista.splice(mejor.despues + 1, 0, latlng);
    poner(lista);
  }
  const clicMapa = (e) => agregar(e.latlng);
  mapa.on("click", clicMapa);
  quitarOyentes.push(on("clic-geometria", ({ latlng }) => agregar(latlng)));

  // Cambios hechos con Geoman (arrastrar, agregar por punto intermedio, quitar) y al arrastrar todo.
  capa.on("pm:edit pm:dragend", cambio);
  function cambio() {
    if (!esPunto && vertices().length < MINIMO[forma]) {
      aviso(`Un${forma === "Polygon" ? " polígono" : "a línea"} necesita al menos ${MINIMO[forma]} puntos.`, "error");
      irA(posicion);
      return;
    }
    registrar();
    refrescar();
  }

  // ---- tabla de vértices
  function refrescarTabla() {
    const cuerpo = panel.querySelector(".tabla-vertices tbody");
    if (!cuerpo) return;
    const lista = vertices();
    panel.querySelector("[data-cantidad]").textContent = lista.length;
    panel.querySelector("[data-c1]").textContent = enUtm() ? "Este" : "Latitud";
    panel.querySelector("[data-c2]").textContent = enUtm() ? "Norte" : "Longitud";
    const d = enUtm() ? 2 : 7;
    cuerpo.innerHTML = lista.map((ll, i) => {
      const [a, b] = aSistema(ll);
      return `<tr data-i="${i}"><td>${i + 1}</td>
        <td><input data-c="0" value="${a.toFixed(d)}" inputmode="decimal"></td>
        <td><input data-c="1" value="${b.toFixed(d)}" inputmode="decimal"></td>
        <td class="acciones-vertice"><button type="button" data-insertar title="Insertar un vértice después">+</button>
          <button type="button" data-borrar title="Quitar este vértice">×</button></td></tr>`;
    }).join("");
  }
  panel.querySelector(".tabla-vertices")?.addEventListener("change", (e) => {
    const fila = e.target.closest("tr[data-i]");
    if (!fila) return;
    const [a, b] = [...fila.querySelectorAll("input")].map((x) => x.value);
    try {
      const [lat, lng] = aLatLng(sistema.value, a, b);
      const lista = vertices();
      lista[Number(fila.dataset.i)] = L.latLng(lat, lng);
      poner(lista);
    } catch (error) {
      aviso(error.message, "error");
      refrescarTabla();
    }
  });
  panel.querySelector(".tabla-vertices")?.addEventListener("click", (e) => {
    const fila = e.target.closest("tr[data-i]");
    if (!fila) return;
    const i = Number(fila.dataset.i);
    const lista = vertices();
    if (e.target.closest("[data-borrar]")) {
      if (lista.length <= MINIMO[forma]) return aviso(`No puede tener menos de ${MINIMO[forma]} puntos.`, "error");
      lista.splice(i, 1);
      poner(lista);
    } else if (e.target.closest("[data-insertar]")) {
      const siguiente = lista[(i + 1) % lista.length];
      const medio = forma === "LineString" && i === lista.length - 1
        ? L.latLng(2 * lista[i].lat - lista[i - 1].lat, 2 * lista[i].lng - lista[i - 1].lng)
        : L.latLng((lista[i].lat + siguiente.lat) / 2, (lista[i].lng + siguiente.lng) / 2);
      lista.splice(i + 1, 0, medio);
      poner(lista);
    }
  });
  panel.querySelector("[data-pegar]")?.addEventListener("click", () => {
    const filas = panel.querySelector(".pegar textarea").value.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    try {
      const lista = filas.map((linea) => {
        const partes = linea.includes("\t") ? linea.split("\t") : linea.split(/[;\s]+/);
        if (partes.length < 2) throw new Error(`Fila sin dos coordenadas: «${linea}»`);
        return L.latLng(...aLatLng(sistema.value, partes[0], partes[1]));
      });
      if (lista.length < MINIMO[forma]) throw new Error(`Se necesitan al menos ${MINIMO[forma]} filas.`);
      poner(lista);
      panel.querySelector(".pegar textarea").value = "";
      aviso(`${lista.length} vértices cargados.`, "ok");
    } catch (error) {
      aviso(error.message, "error");
    }
  });

  // ---- mover todo a un nuevo centro (desplaza en metros, conserva la forma)
  const centro = () => (esPunto ? capa.getLatLng()
    : L.latLng(...turf.centroid(capa.toGeoJSON()).geometry.coordinates.slice().reverse()));
  function refrescarCentro() {
    const [a, b] = aSistema(centro());
    const d = enUtm() ? 2 : 7;
    panel.querySelector("[name=x]").value = a.toFixed(d);
    panel.querySelector("[name=y]").value = b.toFixed(d);
  }
  panel.querySelector("[data-mover-centro]").addEventListener("click", () => {
    let destino;
    try {
      destino = L.latLng(...aLatLng(sistema.value, panel.querySelector("[name=x]").value, panel.querySelector("[name=y]").value));
    } catch (error) {
      return aviso(error.message, "error");
    }
    const actual = centro();
    const zona = zonaUtm(actual.lng);
    const [x0, y0] = proj4("EPSG:4326", zona, [actual.lng, actual.lat]);
    const [x1, y1] = proj4("EPSG:4326", zona, [destino.lng, destino.lat]);
    const lista = vertices().map((ll) => {
      const [x, y] = proj4("EPSG:4326", zona, [ll.lng, ll.lat]);
      const [lng, lat] = proj4(zona, "EPSG:4326", [x + x1 - x0, y + y1 - y0]);
      return L.latLng(lat, lng);
    });
    poner(lista);
    mapa.panTo(destino);
  });

  // ---- números de vértice y medidas
  function refrescarEtiquetas() {
    etiquetas.clearLayers();
    if (esPunto) return;
    const lista = vertices();
    if (lista.length > MAX_ETIQUETAS) return;
    lista.forEach((ll, i) => L.marker(ll, {
      pane: "etiquetas", interactive: false, keyboard: false,
      icon: L.divIcon({ className: "etiqueta-vertice", html: String(i + 1), iconSize: null }),
    }).addTo(etiquetas));
  }
  function refrescarMedidas() {
    const geo = capa.toGeoJSON();
    let html;
    if (esPunto) {
      const u = aUtm(capa.getLatLng().lat, capa.getLatLng().lng);
      html = `<dt>UTM ${u.zona}</dt><dd>E ${num(u.este, 1)} · N ${num(u.norte, 1)}</dd>`;
    } else if (forma === "Polygon") {
      html = `<dt>Área</dt><dd>${num(turf.area(geo) / 10000, 2)} ha</dd>
              <dt>Perímetro</dt><dd>${num(turf.length(turf.polygonToLine(geo), { units: "kilometers" }) * 1000, 0)} m</dd>`;
    } else {
      html = `<dt>Longitud</dt><dd>${num(turf.length(geo, { units: "kilometers" }) * 1000, 0)} m</dd>`;
    }
    panel.querySelector(".medidas").innerHTML = html;
  }
  function refrescar() {
    refrescarTabla();
    refrescarEtiquetas();
    refrescarMedidas();
    refrescarCentro();
    panel.querySelector("[data-deshacer]").disabled = posicion <= 0;
    panel.querySelector("[data-rehacer]").disabled = posicion >= pila.length - 1;
  }
  panel.querySelector("[data-deshacer]").addEventListener("click", () => irA(posicion - 1));
  panel.querySelector("[data-rehacer]").addEventListener("click", () => irA(posicion + 1));
  const teclas = (e) => {
    if (!(e.ctrlKey || e.metaKey) || e.target.matches("input, textarea")) return;
    if (e.key.toLowerCase() === "z") { e.preventDefault(); irA(posicion - 1); }
    if (e.key.toLowerCase() === "y") { e.preventDefault(); irA(posicion + 1); }
  };
  document.addEventListener("keydown", teclas);

  registrar();
  activarHerramienta();
  refrescar();

  return {
    panel,
    destruir() {
      capa.pm.disable();
      capa.pm.disableLayerDrag?.();
      capa.off("pm:edit pm:dragend", cambio);
      mapa.off("click", clicMapa);
      mapa.getContainer().classList.remove("cursor-agregar");
      document.removeEventListener("keydown", teclas);
      quitarOyentes.forEach((quitar) => quitar());
      etiquetas.remove();
    },
  };
}

// «Editar proyecto» / «Nuevo proyecto» sin salir del visor: oculta el mapa y la tabla y muestra
// la página de edición (la misma que /proyectos/<id>/editar/) en su lugar. Los filtros, la
// selección y la vista del mapa se conservan; al volver se recargan los datos.

import { capaDeGeometria, recargarProyectos } from "./capas.js";
import { editarGeometria } from "./edicion.js";
import { emitir, on } from "./estado.js";
import { getMapa } from "./mapa.js";

const V = window.VISOR;
let abierto = null; // { proyectoId, cambios }

export function abrirEditor({ proyectoId = null, titulo = "Editar proyecto" } = {}) {
  const url = proyectoId ? `${V.proyectos}${proyectoId}/editar/` : `${V.proyectos}nuevo/`;
  abierto = { proyectoId, cambios: false };
  document.getElementById("editor-proyecto-titulo").textContent = titulo;
  document.getElementById("editor-proyecto-pestana").href = url;
  document.getElementById("editor-proyecto-marco").src = `${url}?incrustado=1`;
  document.getElementById("editor-proyecto").hidden = false;
  document.getElementById("visor").classList.add("editando");
}

export function cerrarEditor({ despues } = {}) {
  if (!abierto) return;
  const { proyectoId, cambios } = abierto;
  abierto = null;
  document.getElementById("editor-proyecto").hidden = true;
  document.getElementById("editor-proyecto-marco").src = "about:blank";
  document.getElementById("visor").classList.remove("editando");
  getMapa().invalidateSize();
  emitir("distribucion");
  if (cambios || despues) {
    const quitar = on("proyectos-cargados", () => {
      quitar();
      if (despues) despues();
      else if (proyectoId) emitir("abrir-ficha", proyectoId);
    });
    recargarProyectos();
  } else if (proyectoId) {
    emitir("abrir-ficha", proyectoId);
  }
}

export function iniciarEditorProyecto() {
  document.getElementById("editor-proyecto-volver").addEventListener("click", () => cerrarEditor());
  window.addEventListener("message", (e) => {
    if (e.origin !== location.origin || !abierto) return;
    if (e.data?.tipo === "proyecto-guardado") abierto.cambios = true;
    if (e.data?.tipo === "editar-geometria") {
      const id = e.data.id;
      cerrarEditor({
        despues: () => {
          const capa = capaDeGeometria(id);
          if (capa) {
            getMapa().fitBounds(capa.getBounds?.() || capa.getLatLng().toBounds(300), { maxZoom: 17 });
            editarGeometria(id);
          }
        },
      });
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && abierto) cerrarEditor();
  });
}

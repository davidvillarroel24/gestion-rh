// Filtros por atributos (panel izquierdo). Afectan a la vez al mapa y a la tabla.
// Región → Provincia → Municipio van en cascada (como en el Motor SIG): cada lista
// solo ofrece lo que es compatible con lo ya elegido en las otras.

import { emitir, estado } from "./estado.js";
import { nodo, opciones } from "./ui.js";

function compatibles(formulario) {
  const region = Number(formulario.region.value) || null;
  const provincia = Number(formulario.provincia.value) || null;
  const municipios = estado.config.municipios;
  const enRegion = municipios.filter((m) => !region || m.region === region);
  const provincias = new Set(enRegion.map((m) => m.provincia));
  const regiones = new Set(municipios.filter((m) => !provincia || m.provincia === provincia).map((m) => m.region));
  return {
    regiones: estado.config.regiones.filter((r) => regiones.has(r.id)),
    provincias: estado.config.provincias.filter((p) => provincias.has(p.id)),
    municipios: enRegion.filter((m) => !provincia || m.provincia === provincia),
  };
}

function rellenar(select, lista, vacio) {
  const actual = select.value;
  select.innerHTML = opciones(lista, { vacio, seleccionado: actual });
  if (!lista.some((x) => String(x.id) === actual)) select.value = ""; // la opción elegida ya no aplica
}

function actualizarCascada(formulario) {
  const c = compatibles(formulario);
  rellenar(formulario.region, c.regiones, "Todas");
  rellenar(formulario.provincia, c.provincias, "Todas");
  rellenar(formulario.municipio, c.municipios, "Todos");
}

export function iniciarFiltros() {
  const c = estado.config;
  const formulario = nodo(`
    <form class="formulario-filtros">
      <label>Unidad<select name="unidad">${opciones(c.unidades, { vacio: "Todas" })}</select></label>
      <label>Estado<select name="estado">${opciones(c.estados, { vacio: "Todos" })}</select></label>
      <label>Región<select name="region"></select></label>
      <label>Provincia<select name="provincia"></select></label>
      <label>Municipio<select name="municipio"></select></label>
      <label>Gestión<input name="gestion" type="number" min="1990" max="2100" placeholder="Todas"></label>
      <label>Texto<input name="q" type="search" placeholder="Código, nombre, comunidad, SISIN"></label>
      <div style="display:flex;gap:6px;margin-top:8px">
        <button class="boton" type="submit">Aplicar</button>
        <button class="boton secundario" type="reset">Limpiar</button>
      </div>
    </form>`);
  actualizarCascada(formulario);

  const aplicarFormulario = () => aplicar(Object.fromEntries(new FormData(formulario)));
  formulario.addEventListener("submit", (e) => {
    e.preventDefault();
    aplicarFormulario();
  });
  formulario.addEventListener("reset", () => setTimeout(() => {
    actualizarCascada(formulario);
    aplicar({});
  }, 0));
  // Las listas filtran al instante; los campos de texto, con Enter o "Aplicar".
  formulario.querySelectorAll("select").forEach((s) => s.addEventListener("change", () => {
    actualizarCascada(formulario);
    aplicarFormulario();
  }));
  document.getElementById("filtros").replaceChildren(formulario);
}

export function aplicar(filtros) {
  estado.filtros = Object.fromEntries(Object.entries(filtros).filter(([, v]) => v !== "" && v !== null));
  emitir("filtros", estado.filtros);
}

export function enfocarFiltros() {
  document.getElementById("visor").classList.remove("sin-capas");
  emitir("distribucion");
  document.querySelector("#filtros select")?.focus();
}

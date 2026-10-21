// Filtros por atributos (panel izquierdo). Afectan a la vez al mapa y a la tabla.

import { emitir, estado } from "./estado.js";
import { nodo, opciones } from "./ui.js";

export function iniciarFiltros() {
  const c = estado.config;
  const formulario = nodo(`
    <form class="formulario-filtros">
      <label>Unidad<select name="unidad">${opciones(c.unidades, { vacio: "Todas" })}</select></label>
      <label>Estado<select name="estado">${opciones(c.estados, { vacio: "Todos" })}</select></label>
      <label>Municipio<select name="municipio">${opciones(c.municipios, { vacio: "Todos" })}</select></label>
      <label>Gestión<input name="gestion" type="number" min="1990" max="2100" placeholder="Todas"></label>
      <label>Texto<input name="q" type="search" placeholder="Código, nombre, comunidad, SISIN"></label>
      <div style="display:flex;gap:6px;margin-top:8px">
        <button class="boton" type="submit">Aplicar</button>
        <button class="boton secundario" type="reset">Limpiar</button>
      </div>
    </form>`);

  formulario.addEventListener("submit", (e) => {
    e.preventDefault();
    aplicar(Object.fromEntries(new FormData(formulario)));
  });
  formulario.addEventListener("reset", () => setTimeout(() => aplicar({}), 0));
  // Las listas cambian el filtro al instante; los campos de texto, con Enter o "Aplicar".
  formulario.querySelectorAll("select").forEach((s) =>
    s.addEventListener("change", () => aplicar(Object.fromEntries(new FormData(formulario)))));
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

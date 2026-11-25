// Filtros por atributos (panel izquierdo). Afectan a la vez al mapa y a la tabla.
// Cada lista tiene su propio buscador y permite elegir varios valores (SelectorMultiple,
// static/js/selector-multiple.js); se envían como "1,3" y el servidor los toma como «cualquiera de».
// Región → Provincia → Municipio van en cascada: cada lista solo ofrece lo compatible con lo ya elegido.

import { emitir, estado } from "./estado.js";
import { iniciarRellenoFiltro } from "./relleno-filtro.js";
import { nodo } from "./ui.js";

const LISTAS = [
  ["unidad", "Unidad", "Todas"],
  ["programa", "Programa", "Todos"],
  ["estado", "Estado", "Todos"],
  ["region", "Región", "Todas"],
  ["provincia", "Provincia", "Todas"],
  ["municipio", "Municipio", "Todos"],
  ["gestion", "Gestión", "Todas"],
];

const selectores = {};
const elegidos = (nombre) => new Set(selectores[nombre].valor().split(",").filter(Boolean).map(Number));

function actualizarCascada() {
  const c = estado.config;
  const unidades = elegidos("unidad");
  const regiones = elegidos("region");
  const provincias = elegidos("provincia");
  selectores.programa.opciones(c.programas.filter((p) => !unidades.size || unidades.has(p.unidad)));
  const enRegiones = c.municipios.filter((m) => !regiones.size || regiones.has(m.region));
  const provinciasPosibles = new Set(enRegiones.map((m) => m.provincia));
  const regionesPosibles = new Set(c.municipios.filter((m) => !provincias.size || provincias.has(m.provincia)).map((m) => m.region));
  selectores.region.opciones(c.regiones.filter((r) => regionesPosibles.has(r.id)));
  selectores.provincia.opciones(c.provincias.filter((p) => provinciasPosibles.has(p.id)));
  selectores.municipio.opciones(enRegiones.filter((m) => !provincias.size || provincias.has(m.provincia)));
}

export function iniciarFiltros() {
  const c = estado.config;
  const formulario = nodo(`
    <form class="formulario-filtros">
      ${LISTAS.map(([nombre, titulo]) => `<label>${titulo}<span data-selector="${nombre}"></span></label>`).join("")}
      <label>Texto<input name="q" type="search" placeholder="Código, nombre, comunidad, SISIN"></label>
      <label class="relleno-filtro" title="Rellena los municipios donde están los proyectos filtrados. Sin filtros no rellena nada.">
        <input type="checkbox" name="relleno"> Relleno transparente en lo filtrado <small>(se ve al filtrar)</small></label>
      <div style="display:flex;gap:6px;margin-top:8px">
        <button class="boton" type="submit">Aplicar</button>
        <button class="boton secundario" type="reset">Limpiar</button>
      </div>
    </form>`);

  const aplicarFormulario = () => {
    const filtros = Object.fromEntries(LISTAS.map(([nombre]) => [nombre, selectores[nombre].valor()]));
    filtros.q = formulario.q.value.trim();
    aplicar(filtros);
  };
  // Las listas filtran al instante (y ajustan la cascada); el Texto, al dejar de escribir.
  LISTAS.forEach(([nombre, , vacio]) => {
    selectores[nombre] = new window.SelectorMultiple(formulario.querySelector(`[data-selector="${nombre}"]`), {
      nombre, vacio, alCambiar: () => { actualizarCascada(); aplicarFormulario(); },
    });
  });
  selectores.unidad.opciones(c.unidades);
  selectores.estado.opciones(c.estados);
  selectores.gestion.opciones(c.gestiones); // solo las gestiones que tienen proyectos
  actualizarCascada();

  formulario.addEventListener("submit", (e) => {
    e.preventDefault();
    aplicarFormulario();
  });
  formulario.addEventListener("reset", () => setTimeout(() => {
    Object.values(selectores).forEach((s) => s.limpiar());
    actualizarCascada();
    aplicar({});
  }, 0));
  let espera = null;
  formulario.querySelectorAll("input").forEach((campo) => campo.addEventListener("input", () => {
    clearTimeout(espera);
    espera = setTimeout(aplicarFormulario, 600);
  }));
  document.getElementById("filtros").replaceChildren(formulario);
  iniciarRellenoFiltro(formulario.relleno);
}

export function aplicar(filtros) {
  estado.filtros = Object.fromEntries(Object.entries(filtros).filter(([, v]) => v !== "" && v !== null && v !== undefined));
  emitir("filtros", estado.filtros);
}

export function enfocarFiltros() {
  document.getElementById("visor").classList.remove("sin-capas");
  emitir("distribucion");
  document.querySelector("#filtros .sm-boton")?.focus();
}

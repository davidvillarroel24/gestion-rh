// Tabla de atributos, sincronizada con el mapa: seleccionar una fila resalta
// sus geometrías y al revés. Doble clic abre la ficha del proyecto.

import { alternarSeleccion, emitir, estado, on, seleccionar } from "./estado.js";
import { get } from "./api.js";
import { capasDeProyectos } from "./capas.js";
import { ajustarA } from "./mapa.js";
import { aviso, bs, esc, pct } from "./ui.js";

const COLUMNAS = [
  { campo: "codigo", titulo: "Código" },
  { campo: "nombre", titulo: "Nombre" },
  { campo: "unidad", titulo: "Unidad" },
  { campo: "programa", titulo: "Programa" },
  { campo: "estado", titulo: "Estado" },
  { campo: "gestion", titulo: "Gestión", num: true },
  { campo: "municipios", titulo: "Municipios" },
  { campo: "costo_total", titulo: "Costo total (Bs)", num: true, formato: bs },
  { campo: "desembolsado", titulo: "Desembolsado (Bs)", num: true, formato: bs },
  { campo: "avance_financiero", titulo: "Av. financiero", num: true, formato: pct },
  { campo: "avance_fisico", titulo: "Av. físico", num: true, formato: pct },
];

let orden = { campo: "codigo", asc: true };
let texto = "";
let cargada = false;

const tabla = () => document.getElementById("tabla");

export async function recargar() {
  try {
    const datos = await get("proyectos/", estado.filtros);
    estado.filas = datos.filas;
    cargada = true;
    emitir("filas", estado.filas);
    if (!tabla().hidden) dibujar();
  } catch (error) {
    aviso(`No se pudo cargar la tabla: ${error.message}`, "error");
  }
}

function filasVisibles() {
  const t = texto.toLowerCase();
  const filas = t
    ? estado.filas.filter((f) => COLUMNAS.some((c) => String(f[c.campo] ?? "").toLowerCase().includes(t)))
    : [...estado.filas];
  const { campo, asc } = orden;
  filas.sort((a, b) => {
    const x = a[campo] ?? "";
    const y = b[campo] ?? "";
    const r = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), "es");
    return asc ? r : -r;
  });
  return filas;
}

function dibujar() {
  const filas = filasVisibles();
  const encabezado = COLUMNAS.map((c) =>
    `<th data-campo="${c.campo}">${esc(c.titulo)}${orden.campo === c.campo ? (orden.asc ? " ▲" : " ▼") : ""}</th>`).join("");
  const cuerpo = filas.map((f) => `<tr data-id="${f.id}" class="${estado.seleccion.has(f.id) ? "seleccionada" : ""}">${
    COLUMNAS.map((c) => `<td class="${c.num ? "num" : ""}">${esc(c.formato ? c.formato(f[c.campo]) : f[c.campo] ?? "")}</td>`).join("")
  }</tr>`).join("");
  document.getElementById("tabla-cuerpo").innerHTML =
    `<table><thead><tr>${encabezado}</tr></thead><tbody>${cuerpo}</tbody></table>`;
  document.getElementById("tabla-cantidad").textContent =
    `(${filas.length} de ${estado.filas.length}${estado.seleccion.size ? `, ${estado.seleccion.size} seleccionados` : ""})`;
}

function marcarSeleccion() {
  document.querySelectorAll("#tabla-cuerpo tbody tr").forEach((tr) =>
    tr.classList.toggle("seleccionada", estado.seleccion.has(Number(tr.dataset.id))));
  if (!tabla().hidden) {
    const n = document.querySelectorAll("#tabla-cuerpo tbody tr").length;
    document.getElementById("tabla-cantidad").textContent =
      `(${n} de ${estado.filas.length}${estado.seleccion.size ? `, ${estado.seleccion.size} seleccionados` : ""})`;
  }
}

export function mostrar(visible = tabla().hidden) {
  tabla().hidden = !visible;
  if (visible) cargada ? dibujar() : recargar();
  emitir("distribucion");
}

export const estaVisible = () => !tabla().hidden;

export function iniciarTabla() {
  const cuerpo = document.getElementById("tabla-cuerpo");
  cuerpo.addEventListener("click", (e) => {
    const th = e.target.closest("th");
    if (th) {
      orden = { campo: th.dataset.campo, asc: orden.campo === th.dataset.campo ? !orden.asc : true };
      dibujar();
      return;
    }
    const tr = e.target.closest("tr[data-id]");
    if (!tr) return;
    const id = Number(tr.dataset.id);
    if (e.ctrlKey || e.metaKey) alternarSeleccion(id);
    else seleccionar([id]);
    ajustarA(capasDeProyectos(new Set([id])));
  });
  cuerpo.addEventListener("dblclick", (e) => {
    const tr = e.target.closest("tr[data-id]");
    if (tr) emitir("abrir-ficha", Number(tr.dataset.id));
  });
  document.getElementById("tabla-buscar").addEventListener("input", (e) => {
    texto = e.target.value;
    dibujar();
  });
  document.getElementById("tabla-cerrar").addEventListener("click", () => mostrar(false));
  on("seleccion", marcarSeleccion);
  on("filtros", recargar);
  recargar();
}

// Piezas de interfaz reutilizables: avisos, panel derecho, menús, formatos.

import { emitir } from "./estado.js";

export const esc = (texto) =>
  String(texto ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

export const bs = (n) =>
  n === null || n === undefined ? "—" : n.toLocaleString("es-BO", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const pct = (n) =>
  n === null || n === undefined ? "—" : `${Number(n).toLocaleString("es-BO", { maximumFractionDigits: 1 })} %`;

export function aviso(texto, tipo = "") {
  const div = document.createElement("div");
  div.className = `aviso ${tipo}`;
  div.textContent = texto;
  document.getElementById("avisos").append(div);
  setTimeout(() => div.remove(), tipo === "error" ? 8000 : 4500);
}

export function mensaje(texto) {
  document.getElementById("estado-mensaje").textContent = texto || "";
}

let alCerrarPanel = null;

export const panel = {
  abrir(titulo, contenido, { alCerrar = null } = {}) {
    if (alCerrarPanel) alCerrarPanel();
    alCerrarPanel = alCerrar;
    document.getElementById("panel-derecho-titulo").textContent = titulo;
    const destino = document.getElementById("panel-derecho-contenido");
    if (typeof contenido === "string") destino.innerHTML = contenido;
    else destino.replaceChildren(contenido);
    document.getElementById("panel-derecho").hidden = false;
    emitir("distribucion");
    return destino;
  },
  cerrar() {
    if (alCerrarPanel) {
      const fn = alCerrarPanel;
      alCerrarPanel = null;
      fn();
    }
    document.getElementById("panel-derecho").hidden = true;
    emitir("distribucion");
  },
};

document.getElementById("panel-derecho-cerrar").addEventListener("click", () => panel.cerrar());

// Menú desplegable bajo un elemento. items: [{etiqueta, icono, accion}] o "-" para separador.
export function menu(ancla, items) {
  document.querySelectorAll(".menu-flotante").forEach((m) => m.remove());
  const caja = document.createElement("div");
  caja.className = "menu-flotante";
  items.forEach((item) => {
    if (item === "-") {
      caja.append(document.createElement("hr"));
      return;
    }
    const boton = document.createElement("button");
    boton.type = "button";
    boton.innerHTML = `${item.icono ? `<i class="bi bi-${item.icono}"></i>` : ""}<span>${esc(item.etiqueta)}</span>`;
    boton.addEventListener("click", () => {
      caja.remove();
      item.accion();
    });
    caja.append(boton);
  });
  const r = ancla.getBoundingClientRect();
  caja.style.left = `${r.left}px`;
  caja.style.top = `${r.bottom + 2}px`;
  document.body.append(caja);
  setTimeout(() => document.addEventListener("click", function cerrar(e) {
    if (!caja.contains(e.target)) {
      caja.remove();
      document.removeEventListener("click", cerrar);
    }
  }), 0);
}

// Crea un nodo a partir de HTML (para formularios del panel).
export function nodo(html) {
  const plantilla = document.createElement("template");
  plantilla.innerHTML = html.trim();
  return plantilla.content.firstElementChild;
}

export function opciones(lista, { vacio = null, seleccionado = null } = {}) {
  const inicio = vacio !== null ? `<option value="">${esc(vacio)}</option>` : "";
  return inicio + lista.map((o) =>
    `<option value="${esc(o.id)}" ${String(o.id) === String(seleccionado) ? "selected" : ""}>${esc(o.nombre)}</option>`).join("");
}

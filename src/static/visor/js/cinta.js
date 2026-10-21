// Cinta de herramientas declarativa (mismo patrón que script_ribbon_config del Motor SIG):
// pestañas -> grupos -> botones { etiqueta, icono, accion, activo?, habilitado?, visible? }.
// El estado de los botones (activo/habilitado) se vuelve a evaluar cuando algo cambia.

import { on } from "./estado.js";
import { esc } from "./ui.js";

let definicion = [];
let actual = 0;

function dibujarPestanas() {
  const nav = document.getElementById("cinta-pestanas");
  nav.innerHTML = definicion.map((p, i) =>
    `<button type="button" role="tab" aria-selected="${i === actual}" data-i="${i}">${esc(p.pestana)}</button>`).join("");
}

function dibujarGrupos() {
  const contenedor = document.getElementById("cinta-grupos");
  contenedor.replaceChildren();
  definicion[actual].grupos.forEach((grupo) => {
    const botones = grupo.botones.filter((b) => !b.visible || b.visible());
    if (!botones.length) return;
    const caja = document.createElement("div");
    caja.className = "cinta-grupo";
    const fila = document.createElement("div");
    fila.className = "cinta-grupo-botones";
    botones.forEach((b) => {
      const boton = document.createElement("button");
      boton.type = "button";
      boton.className = "cinta-boton";
      boton.title = b.ayuda || b.etiqueta;
      boton.innerHTML = `<i class="bi bi-${b.icono}"></i><span>${esc(b.etiqueta)}</span>`;
      boton.disabled = b.habilitado ? !b.habilitado() : false;
      boton.classList.toggle("activo", Boolean(b.activo?.()));
      boton.addEventListener("click", () => {
        b.accion(boton);
        refrescar();
      });
      fila.append(boton);
    });
    caja.append(fila);
    const titulo = document.createElement("div");
    titulo.className = "cinta-grupo-titulo";
    titulo.textContent = grupo.titulo;
    caja.append(titulo);
    contenedor.append(caja);
  });
}

export function refrescar() {
  dibujarPestanas();
  dibujarGrupos();
}

export function iniciarCinta(def) {
  definicion = def;
  document.getElementById("cinta-pestanas").addEventListener("click", (e) => {
    const boton = e.target.closest("[data-i]");
    if (!boton) return;
    actual = Number(boton.dataset.i);
    refrescar();
  });
  ["modo", "seleccion", "filas", "distribucion", "vista"].forEach((evento) => on(evento, refrescar));
  refrescar();
}

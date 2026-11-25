// Selector con búsqueda y selección múltiple (como bootstrap-select, sin jQuery ni Bootstrap).
// Un botón muestra lo elegido («Todas», «Riego», «3 seleccionados»); al abrirlo aparece un
// buscador propio y una lista con casillas. Lo usan los filtros del visor y de reportes.
//
//   const s = new SelectorMultiple(contenedor, { nombre: "unidad", vacio: "Todas", alCambiar: fn });
//   s.opciones([{ id: 1, nombre: "Riego" }, …]);   s.valor() -> "1,3"   s.fijar("1,3")   s.limpiar()
(function () {
  "use strict";

  const sinTildes = (t) => String(t).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  let abierto = null; // solo uno abierto a la vez

  class SelectorMultiple {
    constructor(contenedor, { nombre, vacio = "Todos", alCambiar = () => {} }) {
      this.nombre = nombre;
      this.vacio = vacio;
      this.alCambiar = alCambiar;
      this.lista = [];
      this.elegidos = new Set();
      this.raiz = document.createElement("div");
      this.raiz.className = "selector-multiple";
      this.raiz.dataset.nombre = nombre;
      this.raiz.innerHTML = `
        <button type="button" class="sm-boton" aria-haspopup="listbox" aria-expanded="false"><span class="sm-texto"></span><span class="sm-flecha">▾</span></button>
        <div class="sm-menu" hidden>
          <input type="search" class="sm-buscar" placeholder="Buscar…" aria-label="Buscar">
          <div class="sm-acciones"><button type="button" data-todos>Marcar visibles</button><button type="button" data-ninguno>Limpiar</button></div>
          <div class="sm-lista" role="listbox" aria-multiselectable="true"></div>
        </div>`;
      contenedor.replaceWith(this.raiz); // ocupa el lugar del elemento marcador
      this.boton = this.raiz.querySelector(".sm-boton");
      this.menu = this.raiz.querySelector(".sm-menu");
      this.buscar = this.raiz.querySelector(".sm-buscar");
      this.listaEl = this.raiz.querySelector(".sm-lista");

      this.boton.addEventListener("click", () => (this.menu.hidden ? this.abrir() : this.cerrar()));
      this.buscar.addEventListener("input", () => this.dibujar());
      this.buscar.addEventListener("keydown", (e) => {
        if (e.key === "Enter") { // Enter marca el primero visible
          e.preventDefault();
          this.listaEl.querySelector("input")?.click();
        }
      });
      this.listaEl.addEventListener("change", (e) => {
        const id = e.target.value;
        if (e.target.checked) this.elegidos.add(id); else this.elegidos.delete(id);
        this.texto();
        this.alCambiar(this.valor());
      });
      this.raiz.querySelector("[data-todos]").addEventListener("click", () => {
        this.visibles().forEach((o) => this.elegidos.add(String(o.id)));
        this.dibujar();
        this.texto();
        this.alCambiar(this.valor());
      });
      this.raiz.querySelector("[data-ninguno]").addEventListener("click", () => {
        if (!this.elegidos.size) return;
        this.limpiar();
        this.alCambiar(this.valor());
      });
      this.raiz.addEventListener("keydown", (e) => {
        if (e.key === "Escape") { this.cerrar(); this.boton.focus(); }
      });
      this.texto();
    }

    // Cambia las opciones (cascada); conserva solo lo elegido que sigue existiendo.
    opciones(lista) {
      this.lista = lista;
      const ids = new Set(lista.map((o) => String(o.id)));
      this.elegidos = new Set([...this.elegidos].filter((id) => ids.has(id)));
      if (!this.menu.hidden) this.dibujar();
      this.texto();
    }

    valor() { return [...this.elegidos].join(","); }

    fijar(valor) {
      this.elegidos = new Set(String(valor || "").split(",").filter(Boolean));
      this.texto();
      if (!this.menu.hidden) this.dibujar();
    }

    limpiar() {
      this.elegidos.clear();
      this.texto();
      if (!this.menu.hidden) this.dibujar();
    }

    visibles() {
      const t = sinTildes(this.buscar.value.trim());
      return t ? this.lista.filter((o) => sinTildes(o.nombre).includes(t)) : this.lista;
    }

    dibujar() {
      const visibles = this.visibles();
      // Los elegidos primero, para verlos aunque la lista sea larga.
      const orden = [...visibles.filter((o) => this.elegidos.has(String(o.id))), ...visibles.filter((o) => !this.elegidos.has(String(o.id)))];
      this.listaEl.innerHTML = orden.length
        ? orden.map((o) => `<label class="sm-opcion"><input type="checkbox" value="${esc(o.id)}" ${this.elegidos.has(String(o.id)) ? "checked" : ""}> ${esc(o.nombre)}</label>`).join("")
        : '<p class="sm-vacio">Sin coincidencias</p>';
    }

    texto() {
      const elegidos = this.lista.filter((o) => this.elegidos.has(String(o.id)));
      const texto = !this.elegidos.size ? this.vacio
        : elegidos.length === 1 ? elegidos[0].nombre
        : `${this.elegidos.size} seleccionados`;
      this.raiz.querySelector(".sm-texto").textContent = texto;
      this.boton.title = elegidos.map((o) => o.nombre).join(", ") || this.vacio;
      this.raiz.classList.toggle("con-valor", this.elegidos.size > 0);
    }

    abrir() {
      if (abierto && abierto !== this) abierto.cerrar();
      abierto = this;
      this.menu.hidden = false;
      this.boton.setAttribute("aria-expanded", "true");
      this.buscar.value = "";
      this.dibujar();
      this.buscar.focus();
    }

    cerrar() {
      this.menu.hidden = true;
      this.boton.setAttribute("aria-expanded", "false");
      if (abierto === this) abierto = null;
    }
  }

  document.addEventListener("click", (e) => {
    if (abierto && !abierto.raiz.contains(e.target)) abierto.cerrar();
  });

  window.SelectorMultiple = SelectorMultiple;
})();

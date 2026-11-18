// Página de edición del proyecto: agregar filas a las tablas, filtrar programa y tipo por
// unidad, buscar municipios, avisar si se sale sin guardar y abrir geometrías en el mapa.
(function () {
  "use strict";

  const incrustado = window.parent !== window;

  // ---- «+ Agregar fila»: copia la fila vacía del formset con el siguiente índice
  document.querySelectorAll("[data-agregar]").forEach((boton) => {
    boton.addEventListener("click", () => {
      const prefijo = boton.dataset.agregar;
      const total = document.querySelector(`[name="${prefijo}-TOTAL_FORMS"]`);
      const plantilla = document.querySelector(`template[data-fila-vacia="${prefijo}"]`);
      const indice = Number(total.value);
      const html = plantilla.innerHTML.replaceAll("__prefix__", String(indice));
      document.querySelector(`table[data-prefijo="${prefijo}"] tbody`).insertAdjacentHTML("beforeend", html);
      total.value = indice + 1;
      document.querySelector(`table[data-prefijo="${prefijo}"] tbody tr:last-child :is(input, select, textarea)`)?.focus();
    });
  });

  // ---- Programa y tipo: solo los de la unidad elegida (las opciones dicen «Nombre (Unidad)»)
  const unidad = document.querySelector("select[name=unidad]");
  function filtrarPorUnidad() {
    const nombre = unidad.selectedOptions[0]?.textContent.trim();
    ["programa", "tipo"].forEach((campo) => {
      const select = document.querySelector(`select[name=${campo}]`);
      if (!select) return;
      [...select.options].forEach((o) => { if (o.value) o.hidden = Boolean(nombre) && !o.textContent.trim().endsWith(`(${nombre})`); });
      if (select.selectedOptions[0]?.hidden) select.value = "";
    });
  }
  if (unidad) {
    unidad.addEventListener("change", filtrarPorUnidad);
    filtrarPorUnidad();
  }

  // ---- Buscar en la lista de municipios
  document.querySelector(".buscar-municipio")?.addEventListener("input", (e) => {
    const texto = e.target.value.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
    document.querySelectorAll("#id_municipios > div, #id_municipios li").forEach((item) => {
      const nombre = item.textContent.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
      item.hidden = Boolean(texto) && !nombre.includes(texto) && !item.querySelector("input:checked");
    });
  });

  // ---- Aviso al cambiar de pestaña con cambios sin guardar
  const formulario = document.querySelector("form.form-proyecto");
  let sinGuardar = false;
  formulario?.addEventListener("input", () => { sinGuardar = true; });
  formulario?.addEventListener("submit", () => { sinGuardar = false; });
  document.querySelectorAll(".pestanas-proyecto a").forEach((a) => a.addEventListener("click", (e) => {
    if (sinGuardar && !confirm("Hay cambios sin guardar en esta pestaña. ¿Salir igual?")) e.preventDefault();
  }));

  // ---- Dentro del visor: «Editar en el mapa» vuelve al mapa con esa geometría en edición
  document.querySelectorAll("[data-geometria]").forEach((a) => a.addEventListener("click", (e) => {
    if (!incrustado) return;
    e.preventDefault();
    window.parent.postMessage({ tipo: "editar-geometria", id: Number(a.dataset.geometria) }, location.origin);
  }));

  // Avisa al visor que hubo cambios (al volver al mapa recarga los datos).
  if (incrustado && document.querySelector(".mensaje.success")) {
    window.parent.postMessage({ tipo: "proyecto-guardado" }, location.origin);
  }
})();

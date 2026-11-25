// Página de reportes: filtros (en la URL, compartibles), tarjetas, agrupado con
// gráfica, curva S, indicadores y alertas. Todo sale de /reportes/api/.
(function () {
  "use strict";

  const R = window.REPORTES;
  const definicion = JSON.parse(document.getElementById("definicion-filtros").textContent);
  const formulario = document.getElementById("filtros");
  const porSelect = document.getElementById("por");
  const medidaSelect = document.getElementById("medida");
  const COLORES = { verde: "#0b6e4f", azul: "#1f77b4", naranja: "#e4572e" };
  let datos = null;
  let graficoAgrupado = null;
  let graficoCurva = null;

  // ---------------------------------------------------------------- utilidades

  const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const bs = (n) => (n === null || n === undefined ? "—" : Number(n).toLocaleString("es-BO", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
  const pct = (n) => (n === null || n === undefined ? "—" : `${Number(n).toLocaleString("es-BO", { maximumFractionDigits: 1 })} %`);
  // Tarjetas: millones abreviados (el monto exacto queda en el tooltip).
  const bsCorto = (n) => (n === null || n === undefined || Math.abs(n) < 1e6 ? bs(n)
    : `${(Number(n) / 1e6).toLocaleString("es-BO", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} M`);
  const num = (n) => (n === null || n === undefined ? "—" : Number(n).toLocaleString("es-BO", { maximumFractionDigits: 2 }));

  // Listas con buscador y selección múltiple (igual que en el visor): se envían como "1,3".
  const LISTAS = [["unidad", "Todas"], ["programa", "Todos"], ["estado", "Todos"], ["region", "Todas"],
                  ["provincia", "Todas"], ["municipio", "Todos"], ["gestion", "Todas"]];
  const selectores = {};
  const elegidos = (nombre) => new Set(selectores[nombre].valor().split(",").filter(Boolean).map(Number));

  // Región → Provincia → Municipio en cascada (igual que en el visor).
  function cascada() {
    const unidades = elegidos("unidad");
    const regiones = elegidos("region");
    const provincias = elegidos("provincia");
    selectores.programa.opciones(definicion.programas.filter((p) => !unidades.size || unidades.has(p.unidad)));
    const enRegiones = definicion.municipios.filter((m) => !regiones.size || regiones.has(m.region));
    const provinciasPosibles = new Set(enRegiones.map((m) => m.provincia));
    const regionesPosibles = new Set(definicion.municipios.filter((m) => !provincias.size || provincias.has(m.provincia)).map((m) => m.region));
    selectores.region.opciones(definicion.regiones.filter((r) => regionesPosibles.has(r.id)));
    selectores.provincia.opciones(definicion.provincias.filter((p) => provinciasPosibles.has(p.id)));
    selectores.municipio.opciones(enRegiones.filter((m) => !provincias.size || provincias.has(m.provincia)));
  }

  function parametros() {
    const p = new URLSearchParams();
    LISTAS.forEach(([nombre]) => { if (selectores[nombre].valor()) p.set(nombre, selectores[nombre].valor()); });
    const q = formulario.q.value.trim();
    if (q) p.set("q", q);
    p.set("por", porSelect.value);
    return p;
  }

  // ---------------------------------------------------------------- dibujo

  function tarjetas(t) {
    const items = [
      ["Proyectos", t.proyectos.toLocaleString("es-BO")],
      ["Comprometido (Bs)", bsCorto(t.comprometido), bs(t.comprometido)],
      ["Desembolsado (Bs)", bsCorto(t.desembolsado), bs(t.desembolsado)],
      ["Saldo por desembolsar (Bs)", bsCorto(t.saldo), bs(t.saldo)],
      ["Avance financiero", pct(t.avance_financiero)],
      ["Avance físico (ponderado)", pct(t.avance_fisico)],
      ["Municipios abarcados", t.municipios],
      ["Proyectos cerrados", t.concluidos],
    ];
    document.getElementById("tarjetas").innerHTML = items.map(([etiqueta, valor, exacto]) =>
      `<div class="dato"${exacto ? ` title="Bs ${esc(exacto)}"` : ""}><div class="valor">${esc(valor)}</div>` +
      `<div class="etiqueta">${esc(etiqueta)}</div>${exacto && exacto !== valor ? `<div class="exacto">${esc(exacto)}</div>` : ""}</div>`).join("");
  }

  function agrupado(a) {
    const medida = medidaSelect.value;
    const filas = a.filas.slice(0, 25); // la gráfica muestra los 25 mayores; la tabla, todos
    const config = {
      type: "bar",
      data: {
        labels: filas.map((f) => f.grupo),
        datasets: [{ label: medidaSelect.selectedOptions[0].textContent, data: filas.map((f) => f[medida] ?? 0), backgroundColor: COLORES.verde }],
      },
      options: { indexAxis: filas.length > 8 ? "y" : "x", maintainAspectRatio: false, plugins: { legend: { display: false } } },
    };
    graficoAgrupado?.destroy();
    graficoAgrupado = new Chart(document.getElementById("grafico-agrupado"), config);

    const conAporte = a.por === "municipio";
    const encabezado = `<thead><tr><th>${esc(a.dimension)}</th><th class="num">Proyectos</th><th class="num">Comprometido (Bs)</th>
      <th class="num">Desembolsado (Bs)</th><th class="num">Av. financiero</th>${conAporte ? '<th class="num">Aporte municipal (Bs)</th>' : ""}</tr></thead>`;
    const fila = (f, clase = "") => `<tr class="${clase}"><td>${esc(f.grupo)}</td><td class="num">${f.proyectos}</td>
      <td class="num">${bs(f.comprometido)}</td><td class="num">${bs(f.desembolsado)}</td><td class="num">${pct(f.avance_financiero)}</td>
      ${conAporte ? `<td class="num">${f.aporte_municipal === undefined ? "" : bs(f.aporte_municipal)}</td>` : ""}</tr>`;
    document.getElementById("tabla-agrupado").innerHTML = encabezado + "<tbody>" + a.filas.map((f) => fila(f)).join("")
      + fila({ ...a.total, grupo: "TOTAL (proyectos distintos)" }, "total") + "</tbody>";
    document.getElementById("nota-agrupado").textContent = a.nota || "";
  }

  function curva(c) {
    graficoCurva?.destroy();
    graficoCurva = new Chart(document.getElementById("grafico-curva"), {
      type: "line",
      data: {
        labels: c.meses,
        datasets: [
          { label: "Avance físico (%)", data: c.fisico, borderColor: COLORES.verde, backgroundColor: COLORES.verde, tension: 0.2 },
          { label: "Avance financiero (%)", data: c.financiero, borderColor: COLORES.naranja, backgroundColor: COLORES.naranja, tension: 0.2 },
        ],
      },
      options: { maintainAspectRatio: false, scales: { y: { min: 0, suggestedMax: 100 } } },
    });
  }

  function indicadores(lista) {
    const tabla = document.getElementById("tabla-indicadores");
    if (!lista.length) {
      tabla.innerHTML = '<tbody><tr><td class="tenue">Sin mediciones cargadas.</td></tr></tbody>';
      return;
    }
    tabla.innerHTML = `<thead><tr><th>Indicador</th><th>Desagregación</th><th>Unidad</th><th class="num">Proyectos</th>
      <th class="num">Línea base</th><th class="num">Meta</th><th class="num">Seguimiento</th><th class="num">Cambio</th></tr></thead><tbody>`
      + lista.map((i) => `<tr><td>${esc(i.indicador)}</td><td>${esc(i.desagregacion)}</td><td>${esc(i.unidad_medida)}</td>
        <td class="num">${i.proyectos}</td><td class="num">${num(i.linea_base)}</td><td class="num">${num(i.meta)}</td>
        <td class="num">${num(i.seguimiento)}</td><td class="num">${i.cambio === null ? "—" : (i.cambio > 0 ? "+" : "") + num(i.cambio)}</td></tr>`).join("")
      + "</tbody>";
  }

  function alertas(lista) {
    document.getElementById("cantidad-alertas").textContent = `(${lista.length})`;
    const tabla = document.getElementById("tabla-alertas");
    if (!lista.length) {
      tabla.innerHTML = '<tbody><tr><td class="tenue">Sin alertas para los proyectos filtrados.</td></tr></tbody>';
      return;
    }
    tabla.innerHTML = "<thead><tr><th>Nivel</th><th>Alerta</th><th>Proyecto</th><th>Estado</th><th>Detalle</th></tr></thead><tbody>"
      + lista.map((a) => `<tr><td><span class="nivel nivel-${esc(a.nivel)}">${esc(a.nivel)}</span></td><td>${esc(a.tipo)}</td>
        <td><a href="${R.visor}?proyecto=${a.proyecto_id}">${esc(a.codigo)}</a> – ${esc(a.nombre)}</td><td>${esc(a.estado)}</td>
        <td>${esc(a.detalle)}</td></tr>`).join("") + "</tbody>";
  }

  // ---------------------------------------------------------------- carga

  async function cargar() {
    const p = parametros();
    history.replaceState(null, "", `?${p}${location.hash}`);
    document.getElementById("descargar").href = `${R.excel}?${p}`;
    const filtrosFicha = new URLSearchParams(p);
    filtrosFicha.delete("por");
    document.getElementById("ficha").href = `${R.ficha}?${filtrosFicha}`;
    const respuesta = await fetch(`${R.datos}?${p}`, { headers: { Accept: "application/json" } });
    if (respuesta.redirected) { location.reload(); return; }
    if (!respuesta.ok) {
      document.getElementById("tarjetas").innerHTML = `<p class="error">No se pudieron cargar los datos (${respuesta.status}).</p>`;
      return;
    }
    datos = await respuesta.json();
    tarjetas(datos.tarjetas);
    agrupado(datos.agrupado);
    curva(datos.curva_s);
    indicadores(datos.indicadores);
    alertas(datos.alertas);
  }

  // Filtros iniciales desde la URL (el visor abre esta página con sus filtros, también los múltiples).
  const inicial = new URLSearchParams(location.search);
  LISTAS.forEach(([nombre, vacio]) => {
    selectores[nombre] = new window.SelectorMultiple(formulario.querySelector(`[data-selector="${nombre}"]`), {
      nombre, vacio, alCambiar: () => { cascada(); cargar(); },
    });
    selectores[nombre].fijar(inicial.get(nombre));
  });
  selectores.unidad.opciones(definicion.unidades);
  selectores.estado.opciones(definicion.estados);
  selectores.gestion.opciones(definicion.gestiones);
  formulario.q.value = inicial.get("q") || "";
  if (inicial.get("por")) porSelect.value = inicial.get("por");
  cascada();

  formulario.addEventListener("submit", (e) => { e.preventDefault(); cargar(); });
  formulario.addEventListener("reset", () => setTimeout(() => {
    Object.values(selectores).forEach((s) => s.limpiar());
    cascada();
    cargar();
  }, 0));
  porSelect.addEventListener("change", cargar);
  medidaSelect.addEventListener("change", () => datos && agrupado(datos.agrupado));
  cargar();
})();

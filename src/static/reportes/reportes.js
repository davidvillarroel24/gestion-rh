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

  function llenar(select, lista, vacio) {
    const actual = select.value || select.dataset.inicial || "";
    select.replaceChildren(new Option(vacio, ""), ...lista.map((x) => new Option(x.nombre, x.id)));
    select.value = lista.some((x) => String(x.id) === String(actual)) ? actual : "";
    delete select.dataset.inicial;
  }

  // Región → Provincia → Municipio en cascada (igual que en el visor).
  function cascada() {
    const region = Number(formulario.region.value) || null;
    const provincia = Number(formulario.provincia.value) || null;
    const enRegion = definicion.municipios.filter((m) => !region || m.region === region);
    const provincias = new Set(enRegion.map((m) => m.provincia));
    const regiones = new Set(definicion.municipios.filter((m) => !provincia || m.provincia === provincia).map((m) => m.region));
    llenar(formulario.region, definicion.regiones.filter((r) => regiones.has(r.id)), "Todas");
    llenar(formulario.provincia, definicion.provincias.filter((p) => provincias.has(p.id)), "Todas");
    llenar(formulario.municipio, enRegion.filter((m) => !provincia || m.provincia === provincia), "Todos");
  }

  function parametros() {
    const p = new URLSearchParams();
    new FormData(formulario).forEach((valor, clave) => { if (valor) p.set(clave, valor); });
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

  // Filtros iniciales desde la URL (el visor abre esta página con sus filtros).
  const inicial = new URLSearchParams(location.search);
  ["region", "provincia", "municipio"].forEach((n) => { if (inicial.get(n)) formulario[n].dataset.inicial = inicial.get(n); });
  llenar(formulario.unidad, definicion.unidades, "Todas");
  llenar(formulario.estado, definicion.estados, "Todos");
  formulario.unidad.value = inicial.get("unidad") || "";
  formulario.estado.value = inicial.get("estado") || "";
  formulario.gestion.value = inicial.get("gestion") || "";
  formulario.q.value = inicial.get("q") || "";
  if (inicial.get("por")) porSelect.value = inicial.get("por");
  cascada();

  formulario.addEventListener("submit", (e) => { e.preventDefault(); cargar(); });
  formulario.addEventListener("reset", () => setTimeout(() => { cascada(); cargar(); }, 0));
  formulario.querySelectorAll("select").forEach((s) => s.addEventListener("change", () => { cascada(); cargar(); }));
  porSelect.addEventListener("change", cargar);
  medidaSelect.addEventListener("change", () => datos && agrupado(datos.agrupado));
  cargar();
})();

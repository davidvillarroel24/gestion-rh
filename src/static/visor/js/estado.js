// Estado compartido del visor y un bus de eventos mínimo entre módulos.

const oyentes = {};

export const estado = {
  config: null,        // respuesta de /visor/api/config/
  filtros: {},         // unidad, estado, municipio, gestion, q
  filas: [],           // filas de la tabla de atributos (proyectos visibles con filtros)
  seleccion: new Set(),// ids de proyectos seleccionados
  modo: null,          // null | "identificar" | "medir-distancia" | "medir-area" | "seleccion-rectangulo" | "dibujar" | "editar"
};

export function on(evento, fn) {
  (oyentes[evento] ??= []).push(fn);
}

export function emitir(evento, datos) {
  (oyentes[evento] || []).forEach((fn) => fn(datos));
}

// Cambia la herramienta activa. Volver a pulsar la misma la apaga.
export function setModo(modo, { alternar = true } = {}) {
  estado.modo = alternar && estado.modo === modo ? null : modo;
  emitir("modo", estado.modo);
}

export function seleccionar(ids, { agregar = false } = {}) {
  if (!agregar) estado.seleccion.clear();
  ids.forEach((id) => estado.seleccion.add(id));
  emitir("seleccion", estado.seleccion);
}

export function alternarSeleccion(id) {
  if (estado.seleccion.has(id)) estado.seleccion.delete(id);
  else estado.seleccion.add(id);
  emitir("seleccion", estado.seleccion);
}

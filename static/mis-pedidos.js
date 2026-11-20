// Filtro (Todos/Pendientes/Pagados/Cancelados) y "seleccionar todos" de la
// lista de pedidos. Archivo externo para cumplir la CSP estricta del servidor.
(() => {
  const botones = [...document.querySelectorAll("#filtros-pedidos .btn-filtro")];
  const filas = [...document.querySelectorAll("tr[data-estado]")];

  const aplicarFiltro = (filtro) => {
    filas.forEach((fila) => {
      fila.hidden = !(filtro === "todos" || fila.dataset.estado === filtro);
    });
  };

  botones.forEach((boton) => {
    boton.addEventListener("click", () => {
      botones.forEach((b) => b.classList.remove("is-active"));
      boton.classList.add("is-active");
      aplicarFiltro(boton.dataset.filtro);
    });
  });

  // Marcar / desmarcar todos los pedidos visibles.
  const master = document.querySelector("#check-todos");
  if (master) {
    master.addEventListener("change", () => {
      document.querySelectorAll(".check-pedido").forEach((c) => {
        if (!c.closest("tr").hidden) c.checked = master.checked;
      });
    });
  }
})();

// Filtro por tipo (Todos / Pizza / Combo / Combo de 2 pizzas / Bebidas) del
// apartado de inventario. Archivo externo para cumplir la CSP del servidor.
(() => {
  const botones = [...document.querySelectorAll("#filtros-stock .btn-filtro")];
  const filas = [...document.querySelectorAll("tr[data-tipo]")];

  botones.forEach((boton) => {
    boton.addEventListener("click", () => {
      botones.forEach((b) => b.classList.remove("is-active"));
      boton.classList.add("is-active");
      const filtro = boton.dataset.filtro;
      filas.forEach((fila) => {
        fila.hidden = !(filtro === "todos" || fila.dataset.tipo === filtro);
      });
    });
  });
})();

// Convierte un <select multiple> en una lista donde cada clic añade o quita
// una opción sin borrar las demás (como si se mantuviera Ctrl presionado).
// getMax() indica cuántas opciones se permiten; con máximo 1, el clic
// reemplaza la opción elegida. onLimit() se llama si se intenta pasar el máximo.
window.enableClickSelect = (select, { getMax = () => Infinity, onLimit = () => {} } = {}) => {
  select.addEventListener("mousedown", (event) => {
    const option = event.target.closest("option");
    if (!option || select.disabled) return;
    event.preventDefault();

    const max = getMax();
    if (!option.selected && select.selectedOptions.length >= max) {
      if (max !== 1) {
        onLimit();
        return;
      }
      [...select.selectedOptions].forEach((other) => { other.selected = false; });
    }

    const scroll = select.scrollTop;
    option.selected = !option.selected;
    select.focus();
    select.scrollTop = scroll; // evita que la lista salte al enfocar
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
};

// Sacude brevemente un contador para avisar que se llegó al máximo.
window.shakeCounter = (element) => {
  element.classList.add("is-shake");
  setTimeout(() => element.classList.remove("is-shake"), 400);
};

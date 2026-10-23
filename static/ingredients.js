const select = document.querySelector("#ingredientes[multiple]");

if (select) {
  const min = Number(select.dataset.min);
  const max = Number(select.dataset.max);
  const count = document.querySelector("#ingredient-count");
  const summary = document.querySelector("#ingredient-summary");

  const update = () => {
    const chosen = [...select.selectedOptions].map((option) => option.value);
    count.textContent = `${chosen.length} / ${max}`;
    count.classList.toggle("is-ok", chosen.length >= min && chosen.length <= max);
    summary.textContent = chosen.length ? `Seleccionados: ${chosen.join(", ")}` : "";

    let message = "";
    if (chosen.length < min) message = `Seleccione al menos ${min} ingredientes.`;
    if (chosen.length > max) message = `Seleccione como máximo ${max} ingredientes.`;
    select.setCustomValidity(message);
  };

  // Un clic sobre un ingrediente lo añade o lo quita sin borrar los demás,
  // como si se mantuviera Ctrl presionado.
  select.addEventListener("mousedown", (event) => {
    const option = event.target.closest("option");
    if (!option) return;
    event.preventDefault();

    if (!option.selected && select.selectedOptions.length >= max) {
      count.classList.add("is-shake");
      setTimeout(() => count.classList.remove("is-shake"), 400);
      return;
    }

    const scroll = select.scrollTop;
    option.selected = !option.selected;
    select.focus();
    select.scrollTop = scroll; // evita que la lista salte al enfocar
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });

  select.addEventListener("change", update);
  update();
}

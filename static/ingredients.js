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

  window.enableClickSelect(select, {
    getMax: () => max,
    onLimit: () => window.shakeCounter(count),
  });
  select.addEventListener("change", update);
  update();
}

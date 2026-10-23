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

// Cada tipo de producto muestra solo sus campos: ingredientes (combo y pizza),
// las dos pizzas (combo de 2 pizzas) y la soda (ambos combos). Los campos
// ocultos se desactivan para que no se validen ni se envíen.
const typeRadios = document.querySelectorAll('input[name="tipo"]');
const typeBlocks = document.querySelectorAll(".type-block");

if (typeRadios.length) {
  const applyType = () => {
    const tipo = document.querySelector('input[name="tipo"]:checked')?.value;
    typeBlocks.forEach((block) => {
      const visible = block.dataset.tipos.split(" ").includes(tipo);
      block.hidden = !visible;
      block.querySelectorAll("input, select, textarea").forEach((field) => {
        field.disabled = !visible;
      });
    });
  };
  typeRadios.forEach((radio) => radio.addEventListener("change", applyType));
  applyType();
}

// En el combo de 2 pizzas no se puede elegir la misma pizza dos veces.
const duoSelects = [...document.querySelectorAll(".duo-pizza")];

if (duoSelects.length === 2) {
  const syncDuo = () => {
    duoSelects.forEach((select, i) => {
      const other = duoSelects[1 - i].value;
      [...select.options].forEach((option) => {
        option.disabled = option.value !== "" && option.value === other;
      });
    });
  };
  duoSelects.forEach((select) => select.addEventListener("change", syncDuo));
  syncDuo();
}

const picker = document.querySelector("#ingredient-picker");

if (picker) {
  const min = Number(picker.dataset.min);
  const max = Number(picker.dataset.max);
  const boxes = [...picker.querySelectorAll('input[name="ingredientes"]')];
  const count = document.querySelector("#ingredient-count");
  const list = document.querySelector("#ingredient-list");

  // Cada clic en un cuadro añade o quita el ingrediente de la lista,
  // en el orden en que se fue eligiendo.
  const order = boxes.filter((box) => box.checked).map((box) => box.value);

  const render = () => {
    const selected = order.length;
    count.textContent = `${selected} / ${max}`;
    count.classList.toggle("is-ok", selected >= min && selected <= max);

    list.replaceChildren(
      ...order.map((value) => {
        const item = document.createElement("li");
        const remove = document.createElement("button");
        remove.type = "button";
        remove.textContent = value;
        remove.title = `Quitar ${value}`;
        remove.setAttribute("aria-label", `Quitar ${value}`);
        remove.addEventListener("click", () => {
          const box = boxes.find((b) => b.value === value);
          box.checked = false;
          box.dispatchEvent(new Event("change"));
        });
        item.append(remove);
        return item;
      })
    );

    // Al llegar al máximo se bloquean los demás cuadros.
    boxes.forEach((box) => {
      box.disabled = !box.checked && selected >= max;
      box.closest(".ingredient-tile").classList.toggle("is-disabled", box.disabled);
    });

    const message =
      selected < min ? `Seleccione al menos ${min} ingredientes.` : "";
    boxes[0].setCustomValidity(message);
  };

  boxes.forEach((box) => {
    box.addEventListener("change", () => {
      const index = order.indexOf(box.value);
      if (box.checked && index === -1) order.push(box.value);
      if (!box.checked && index !== -1) order.splice(index, 1);
      render();
    });
  });

  render();
}

const pizzaSelect = document.querySelector("#pizza-id");
const quantityInput = document.querySelector("#cantidad");
const deliverySelect = document.querySelector("#entrega");

if (pizzaSelect && quantityInput && deliverySelect) {
  const summaryPizza = document.querySelector("#summary-pizza");
  const summaryUnit = document.querySelector("#summary-unit");
  const summaryQuantity = document.querySelector("#summary-quantity");
  const summaryDelivery = document.querySelector("#summary-delivery");
  const summaryTotal = document.querySelector("#summary-total");
  const currency = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  });

  const updateSummary = () => {
    const selected = pizzaSelect.selectedOptions[0];
    const unitPrice = Number(selected?.dataset.price ?? 0);
    const quantity = Math.max(1, Number.parseInt(quantityInput.value, 10) || 1);
    const deliveryLabel =
      deliverySelect.value === "FLETE A DOMICILIO"
        ? "Flete a domicilio"
        : "Retiro en sitio";

    summaryPizza.textContent = selected?.textContent.split(" — ")[0].trim() ?? "Selecciona una pizza";
    summaryUnit.textContent = currency.format(unitPrice);
    summaryQuantity.textContent = String(quantity);
    summaryDelivery.textContent = deliveryLabel;
    summaryTotal.textContent = currency.format(unitPrice * quantity);
  };

  pizzaSelect.addEventListener("change", updateSummary);
  quantityInput.addEventListener("input", updateSummary);
  deliverySelect.addEventListener("change", updateSummary);
  updateSummary();
}

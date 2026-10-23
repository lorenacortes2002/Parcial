const pizzaSelect = document.querySelector("#pizza-id");
const quantityInput = document.querySelector("#cantidad");
const deliverySelect = document.querySelector("#entrega");

if (pizzaSelect && quantityInput && deliverySelect) {
  const summaryPizza = document.querySelector("#summary-pizza");
  const summaryUnit = document.querySelector("#summary-unit");
  const summaryQuantity = document.querySelector("#summary-quantity");
  const summaryDelivery = document.querySelector("#summary-delivery");
  const summaryTotal = document.querySelector("#summary-total");
  const addressField = document.querySelector("#direccion-field");
  const addressInput = document.querySelector("#direccion");
  const summaryAddressRow = document.querySelector("#summary-address-row");
  const summaryAddress = document.querySelector("#summary-address");
  const currency = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  });

  const deliveryHelp = document.querySelector("#entrega-help");

  // Cada pizza define en Fábrica si admite domicilio, retiro o ambos:
  // se desactiva la opción no permitida y se cambia a la que sí lo está.
  const applyPizzaDelivery = () => {
    const allowed = pizzaSelect.selectedOptions[0]?.dataset.entrega ?? "AMBOS";
    [...deliverySelect.options].forEach((option) => {
      option.disabled = allowed !== "AMBOS" && option.value !== allowed;
    });
    if (deliverySelect.selectedOptions[0]?.disabled) deliverySelect.value = allowed;

    if (deliveryHelp) {
      deliveryHelp.hidden = allowed === "AMBOS";
      deliveryHelp.textContent =
        allowed === "FLETE A DOMICILIO"
          ? "Este combo solo se entrega a domicilio."
          : "Este combo solo está disponible para retiro en sitio.";
    }
  };

  const updateSummary = () => {
    const selected = pizzaSelect.selectedOptions[0];
    const unitPrice = Number(selected?.dataset.price ?? 0);
    const quantity = Math.max(1, Number.parseInt(quantityInput.value, 10) || 1);
    const isDelivery = deliverySelect.value === "FLETE A DOMICILIO";
    const deliveryLabel = isDelivery ? "Flete a domicilio" : "Retiro en sitio";

    // La dirección solo se pide (y es obligatoria) cuando el pedido va a domicilio.
    if (addressField && addressInput) {
      addressField.hidden = !isDelivery;
      addressInput.required = isDelivery;
      addressInput.disabled = !isDelivery;
      summaryAddressRow.hidden = !isDelivery;
      summaryAddress.textContent = addressInput.value.trim() || "Pendiente";
    }

    summaryPizza.textContent = selected?.textContent.split(" — ")[0].trim() ?? "Selecciona una pizza";
    summaryUnit.textContent = currency.format(unitPrice);
    summaryQuantity.textContent = String(quantity);
    summaryDelivery.textContent = deliveryLabel;
    summaryTotal.textContent = currency.format(unitPrice * quantity);
  };

  pizzaSelect.addEventListener("change", () => {
    applyPizzaDelivery();
    updateSummary();
  });
  quantityInput.addEventListener("input", updateSummary);
  deliverySelect.addEventListener("change", () => {
    updateSummary();
    if (deliverySelect.value === "FLETE A DOMICILIO") addressInput?.focus();
  });
  addressInput?.addEventListener("input", updateSummary);
  applyPizzaDelivery();
  updateSummary();
}

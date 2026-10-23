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

  // --- Sodas: cantidad, tamaño, sabores y reparto por sabor -------------
  const sodaQty = document.querySelector("#refresco-cantidad");
  const sodaSize = document.querySelector("#refresco-tamano");
  const sodaFlavors = document.querySelector("#refrescos");
  const sodaCount = document.querySelector("#soda-count");
  const sodaHelpText = document.querySelector("#soda-help-text");
  const sodaSplit = document.querySelector("#soda-split");
  const sodaSplitTotal = document.querySelector("#soda-split-total");
  const sodaDetails = document.querySelectorAll(".soda-detail:not(#soda-split)");
  const splitRows = [...document.querySelectorAll(".soda-split__row")];
  const summarySodas = document.querySelector("#summary-sodas");
  let flavorsTouched = sodaFlavors?.selectedOptions.length > 0;

  const sodaTotal = () =>
    Math.min(Number(sodaQty.max), Math.max(0, Number.parseInt(sodaQty.value, 10) || 0));
  const chosenFlavors = () => [...sodaFlavors.selectedOptions].map((o) => o.value);
  const splitRow = (flavor) => splitRows.find((row) => row.dataset.sabor === flavor);

  // Reparte las sodas en partes casi iguales entre los sabores elegidos.
  const distribute = () => {
    const flavors = chosenFlavors();
    const total = sodaTotal();
    flavors.forEach((flavor, i) => {
      const share = Math.floor(total / flavors.length) + (i < total % flavors.length ? 1 : 0);
      splitRow(flavor).querySelector("input").value = Math.max(1, share);
    });
  };

  const sodaPicker = document.querySelector("#soda-picker");
  const isCombo = () => pizzaSelect.selectedOptions[0]?.dataset.tipo === "COMBO";

  const updateSodas = () => {
    // Solo los combos incluyen sodas: con una pizza individual la sección se
    // oculta y se desactiva (sus campos no se envían ni se validan).
    const combo = isCombo();
    sodaPicker.hidden = !combo;
    sodaPicker.disabled = !combo;
    if (!combo) {
      summarySodas.textContent = "No incluye (pizza individual)";
      return;
    }

    const total = sodaTotal();
    const hasSoda = total > 0;
    sodaDetails.forEach((el) => { el.hidden = !hasSoda; });
    sodaSize.disabled = !hasSoda;
    sodaFlavors.disabled = !hasSoda;

    // No puede haber más sabores que sodas: se quitan los últimos elegidos.
    const selected = [...sodaFlavors.selectedOptions];
    selected.slice(Math.max(total, 0)).forEach((o) => { o.selected = false; });

    const flavors = chosenFlavors();
    const maxFlavors = Math.max(total, 1);
    sodaCount.textContent = `${flavors.length} / ${maxFlavors}`;
    sodaCount.classList.toggle("is-ok", flavors.length >= 1);
    sodaHelpText.textContent =
      total > 1
        ? `Haz clic en los sabores que quieras (hasta ${total}); otro clic lo quita.`
        : "Haz clic en un sabor para elegirlo.";
    sodaFlavors.setCustomValidity(hasSoda && !flavors.length ? "Elija al menos un sabor de soda." : "");

    // Con 2 o más sabores se indica cuántas sodas de cada uno.
    const showSplit = hasSoda && flavors.length > 1;
    sodaSplit.hidden = !showSplit;
    splitRows.forEach((row) => {
      const active = showSplit && flavors.includes(row.dataset.sabor);
      row.hidden = !active;
      row.querySelector("input").disabled = !active;
    });

    let summary = "Ninguna";
    if (hasSoda && flavors.length) {
      const size = sodaSize.selectedOptions[0]?.textContent.trim() ?? "";
      const parts = flavors.length === 1
        ? [`${total}× ${flavors[0]}`]
        : flavors.map((f) => `${splitRow(f).querySelector("input").value}× ${f}`);
      summary = `${parts.join(", ")} · ${size}`;
    }
    summarySodas.textContent = summary;

    if (showSplit) {
      const inputs = flavors.map((f) => splitRow(f).querySelector("input"));
      const sum = inputs.reduce((acc, input) => acc + (Number.parseInt(input.value, 10) || 0), 0);
      sodaSplitTotal.textContent = `Total ${sum} / ${total}`;
      sodaSplitTotal.classList.toggle("is-ok", sum === total);
      inputs.at(-1).setCustomValidity(
        sum === total ? "" : `La suma por sabor debe ser ${total} (ahora es ${sum}).`
      );
    }
  };

  // Si el cliente aún no eligió sabor, se sugiere el refresco del combo.
  const suggestComboFlavor = () => {
    if (flavorsTouched || sodaTotal() === 0) return;
    const comboFlavor = pizzaSelect.selectedOptions[0]?.dataset.refresco;
    [...sodaFlavors.options].forEach((o) => { o.selected = o.value === comboFlavor; });
  };

  if (sodaQty && sodaFlavors) {
    window.enableClickSelect(sodaFlavors, {
      getMax: () => Math.max(sodaTotal(), 1),
      onLimit: () => window.shakeCounter(sodaCount),
    });
    sodaFlavors.addEventListener("change", () => {
      flavorsTouched = true;
      distribute();
      updateSodas();
    });
    sodaQty.addEventListener("input", () => {
      suggestComboFlavor();
      distribute();
      updateSodas();
    });
    sodaSize.addEventListener("change", updateSodas);
    splitRows.forEach((row) => row.querySelector("input").addEventListener("input", updateSodas));
    suggestComboFlavor();
    updateSodas();
  }

  pizzaSelect.addEventListener("change", () => {
    applyPizzaDelivery();
    if (sodaFlavors) {
      suggestComboFlavor();
      updateSodas();
    }
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

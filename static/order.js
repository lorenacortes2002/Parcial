const orderForm = document.querySelector("#pedido-form");

if (orderForm) {
  const currency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
  const money = (value) => currency.format(Math.round(value * 100) / 100);

  // --- Paso 1: combo o pizza individual -----------------------------------
  const categoryRadios = [...document.querySelectorAll('input[name="categoria"]')];
  const productChoices = [...document.querySelectorAll(".product-choice")];
  const quantityInput = document.querySelector("#cantidad");

  const category = () => categoryRadios.find((r) => r.checked)?.value ?? "COMBO";
  const activeSelect = () =>
    productChoices.find((c) => c.dataset.categoria === category())?.querySelector("select");
  const selectedProduct = () => activeSelect()?.selectedOptions[0];
  const isCombo = () => (selectedProduct()?.dataset.tipo ?? "PIZZA") !== "PIZZA";
  const quantity = () => Math.max(1, Number.parseInt(quantityInput.value, 10) || 1);

  // Solo se envía el selector de la categoría elegida.
  const applyCategory = () => {
    productChoices.forEach((choice) => {
      const active = choice.dataset.categoria === category();
      choice.hidden = !active;
      choice.querySelector("select").disabled = !active;
    });
  };

  // --- Sodas: cantidad, tamaño, sabores y reparto por sabor ----------------
  const sodaQty = document.querySelector("#refresco-cantidad");
  const sodaSize = document.querySelector("#refresco-tamano");
  const sodaFlavors = document.querySelector("#refrescos");
  const sodaNote = document.querySelector("#soda-note");
  const sodaCount = document.querySelector("#soda-count");
  const sodaHelpText = document.querySelector("#soda-help-text");
  const sodaSplit = document.querySelector("#soda-split");
  const sodaSplitTotal = document.querySelector("#soda-split-total");
  const sodaDetails = document.querySelectorAll(".soda-detail:not(#soda-split)");
  const splitRows = [...document.querySelectorAll(".soda-split__row")];
  let flavorsTouched = sodaFlavors.selectedOptions.length > 0;
  let sodaQtyTouched = false;

  const sodaTotal = () =>
    Math.min(Number(sodaQty.max), Math.max(0, Number.parseInt(sodaQty.value, 10) || 0));
  const chosenFlavors = () => [...sodaFlavors.selectedOptions].map((o) => o.value);
  const splitRow = (flavor) => splitRows.find((row) => row.dataset.sabor === flavor);
  const splitValue = (flavor) =>
    Number.parseInt(splitRow(flavor).querySelector("input").value, 10) || 0;

  // Precio de las sodas: cada combo incluye una lata (se paga la diferencia
  // si el tamaño es mayor y las sodas extra completas); en pizzas se cobran todas.
  const sodasPrice = () => {
    const total = sodaTotal();
    if (!total) return 0;
    const price = Number(sodaSize.selectedOptions[0]?.dataset.price ?? 0);
    if (!isCombo()) return total * price;
    const included = Math.min(total, quantity());
    const difference = price - Number(sodaNote.dataset.incluida);
    return included * difference + (total - included) * price;
  };

  // Reparte las sodas en partes casi iguales entre los sabores elegidos.
  const distribute = () => {
    const flavors = chosenFlavors();
    const total = sodaTotal();
    flavors.forEach((flavor, i) => {
      const share = Math.floor(total / flavors.length) + (i < total % flavors.length ? 1 : 0);
      splitRow(flavor).querySelector("input").value = Math.max(1, share);
    });
  };

  // Sugiere el sabor del combo mientras el cliente no haya elegido otro.
  const suggestComboFlavor = () => {
    if (flavorsTouched || sodaTotal() === 0) return;
    const comboFlavor = selectedProduct()?.dataset.refresco;
    [...sodaFlavors.options].forEach((o) => { o.selected = o.value === comboFlavor; });
  };

  // Por defecto: una soda por combo y ninguna con las pizzas individuales.
  const defaultSodaQty = () => {
    if (sodaQtyTouched) return;
    sodaQty.value = isCombo() ? quantity() : 0;
  };

  const sodaSummary = () => {
    const total = sodaTotal();
    const flavors = chosenFlavors();
    if (!total || !flavors.length) return "Ninguna";
    const size = sodaSize.selectedOptions[0]?.textContent.split(" — ")[0].trim() ?? "";
    const parts = flavors.length === 1
      ? [`${total}× ${flavors[0]}`]
      : flavors.map((f) => `${splitValue(f)}× ${f}`);
    return `${parts.join(", ")} (${size})`;
  };

  const updateSodas = () => {
    const total = sodaTotal();
    const hasSoda = total > 0;
    sodaNote.hidden = !isCombo();
    sodaDetails.forEach((el) => { el.hidden = !hasSoda; });
    sodaSize.disabled = !hasSoda;
    sodaFlavors.disabled = !hasSoda;

    // No puede haber más sabores que sodas: se quitan los últimos elegidos.
    [...sodaFlavors.selectedOptions].slice(total).forEach((o) => { o.selected = false; });

    const flavors = chosenFlavors();
    sodaCount.textContent = `${flavors.length} / ${Math.max(total, 1)}`;
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
    if (showSplit) {
      const inputs = flavors.map((f) => splitRow(f).querySelector("input"));
      const sum = flavors.reduce((acc, f) => acc + splitValue(f), 0);
      sodaSplitTotal.textContent = `Total ${sum} / ${total}`;
      sodaSplitTotal.classList.toggle("is-ok", sum === total);
      inputs.at(-1).setCustomValidity(
        sum === total ? "" : `La suma por sabor debe ser ${total} (ahora es ${sum}).`
      );
    }
  };

  // --- Vista previa del producto que se va a agregar -----------------------
  const summaryPizza = document.querySelector("#summary-pizza");
  const summaryUnit = document.querySelector("#summary-unit");
  const summaryQuantity = document.querySelector("#summary-quantity");
  const summarySodas = document.querySelector("#summary-sodas");
  const summarySodasPrice = document.querySelector("#summary-sodas-price");
  const summaryTotal = document.querySelector("#summary-total");

  const updatePreview = () => {
    const option = selectedProduct();
    const unitPrice = Number(option?.dataset.price ?? 0);
    const sodas = sodasPrice();
    summaryPizza.textContent = option?.textContent.split(" — ")[0].trim() ?? "—";
    summaryUnit.textContent = money(unitPrice);
    summaryQuantity.textContent = String(quantity());
    summarySodas.textContent = sodaSummary();
    summarySodasPrice.textContent = money(sodas);
    summaryTotal.textContent = money(unitPrice * quantity() + sodas);
  };

  // --- Paso 2: entrega -----------------------------------------------------
  const deliverySelect = document.querySelector("#entrega");
  const deliveryHelp = document.querySelector("#entrega-help");
  const addressField = document.querySelector("#direccion-field");
  const addressInput = document.querySelector("#direccion");
  const cartItems = Number(document.querySelector("#tu-pedido")?.dataset.items ?? 0);

  // La entrega se limita según los productos del pedido (o, si aún está
  // vacío, según el producto elegido, que es el que se confirmaría).
  const applyDelivery = () => {
    const allowed = cartItems
      ? deliverySelect.dataset.carrito || "AMBOS"
      : selectedProduct()?.dataset.entrega ?? "AMBOS";
    [...deliverySelect.options].forEach((option) => {
      option.disabled = allowed !== "AMBOS" && option.value !== allowed;
    });
    if (deliverySelect.selectedOptions[0]?.disabled) deliverySelect.value = allowed;
    deliveryHelp.hidden = allowed === "AMBOS";
    deliveryHelp.textContent =
      allowed === "FLETE A DOMICILIO"
        ? "Este pedido solo se entrega a domicilio."
        : "Este pedido solo está disponible para retiro en sitio.";

    // La dirección solo se pide (y es obligatoria) cuando el pedido va a domicilio.
    const isDelivery = deliverySelect.value === "FLETE A DOMICILIO";
    addressField.hidden = !isDelivery;
    addressInput.required = isDelivery;
    addressInput.disabled = !isDelivery;
  };

  // --- Eventos ------------------------------------------------------------
  const refreshAll = () => {
    applyCategory();
    defaultSodaQty();
    suggestComboFlavor();
    updateSodas();
    updatePreview();
    applyDelivery();
  };

  window.enableClickSelect(sodaFlavors, {
    getMax: () => Math.max(sodaTotal(), 1),
    onLimit: () => window.shakeCounter(sodaCount),
  });
  categoryRadios.forEach((radio) => radio.addEventListener("change", () => {
    flavorsTouched = false;
    refreshAll();
  }));
  productChoices.forEach((choice) =>
    choice.querySelector("select").addEventListener("change", refreshAll)
  );
  quantityInput.addEventListener("input", () => {
    defaultSodaQty();
    distribute();
    updateSodas();
    updatePreview();
  });
  sodaQty.addEventListener("input", () => {
    sodaQtyTouched = true;
    suggestComboFlavor();
    distribute();
    updateSodas();
    updatePreview();
  });
  sodaFlavors.addEventListener("change", () => {
    flavorsTouched = true;
    distribute();
    updateSodas();
    updatePreview();
  });
  sodaSize.addEventListener("change", () => { updateSodas(); updatePreview(); });
  splitRows.forEach((row) =>
    row.querySelector("input").addEventListener("input", () => { updateSodas(); updatePreview(); })
  );
  deliverySelect.addEventListener("change", () => {
    applyDelivery();
    if (deliverySelect.value === "FLETE A DOMICILIO") addressInput.focus();
  });

  // Al confirmar un pedido que ya tiene productos, el paso 1 no se envía
  // (ni se valida): solo cuentan los productos de «Tu pedido».
  document.querySelector("#confirmar-pedido").addEventListener("click", () => {
    if (!cartItems) return;
    const itemFields = document.querySelector("#item-fields");
    itemFields.disabled = true;
    // Si el navegador bloquea el envío (p. ej. falta el nombre), se reactiva.
    setTimeout(() => { itemFields.disabled = false; }, 0);
  });

  sodaQtyTouched = sodaQty.value !== String(isCombo() ? quantity() : 0);
  refreshAll();
}

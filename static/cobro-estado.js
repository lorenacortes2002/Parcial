// Auto-refresco de la página de cobro Yappy.
// Se mantiene en un archivo externo (no en línea) para cumplir una CSP
// estricta (script-src 'self', sin 'unsafe-inline'). La URL a consultar
// llega por el atributo data-status-url del elemento #cobro-estado.
(() => {
  const el = document.getElementById("cobro-estado");
  if (!el || !el.dataset.statusUrl) return;
  const statusUrl = el.dataset.statusUrl;
  const timer = setInterval(async () => {
    try {
      const response = await fetch(statusUrl, { cache: "no-store" });
      if (!response.ok) return;
      const data = await response.json();
      if (data.estado !== "PAGADO") return;
      clearInterval(timer);
      // Recarga para mostrar la confirmación con los avisos del servidor.
      window.location.reload();
    } catch (error) {
      // Sin conexión momentánea: se reintenta en el siguiente ciclo.
    }
  }, 2500);
})();

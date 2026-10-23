const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
const revealTargets = document.querySelectorAll(
  ".hero-copy, .service-point, .page-heading, .section-header, .grid .card, " +
    ".table-wrap, .form-card, .order-summary, .section-title, .empty-state, .alert",
);

if (!reduceMotion.matches && "IntersectionObserver" in window) {
  const observer = new IntersectionObserver(
    (entries, currentObserver) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          currentObserver.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.12, rootMargin: "0px 0px -40px 0px" },
  );

  revealTargets.forEach((element, index) => {
    element.classList.add("reveal");
    if (element.matches(".service-point, .grid .card")) {
      element.style.setProperty("--reveal-delay", `${(index % 5) * 75}ms`);
    }
    observer.observe(element);
  });
  document.documentElement.classList.add("motion-ready");
}

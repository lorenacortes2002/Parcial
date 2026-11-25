const menuSearch = document.querySelector("#menu-search");
const menuCategory = document.querySelector("#menu-category");

if (menuSearch && menuCategory) {
  const cards = [...document.querySelectorAll("[data-menu-item]")];
  const sections = [...document.querySelectorAll(".menu-section")];
  const resultCount = document.querySelector("#menu-result-count");
  const noResults = document.querySelector("#menu-no-results");

  const applyFilters = () => {
    const query = menuSearch.value.trim().toLocaleLowerCase();
    const category = menuCategory.value;
    let visible = 0;

    cards.forEach((card) => {
      const matchesCategory = category === "TODOS" || card.dataset.category === category;
      const matchesSearch = card.dataset.search.includes(query);
      card.hidden = !matchesCategory || !matchesSearch;
      if (!card.hidden) visible += 1;
    });

    sections.forEach((section) => {
      section.hidden = !section.querySelector("[data-menu-item]:not([hidden])");
    });
    resultCount.textContent = `${visible} ${visible === 1 ? "producto" : "productos"}`;
    noResults.hidden = visible > 0;
  };

  menuSearch.addEventListener("input", applyFilters);
  menuCategory.addEventListener("change", applyFilters);
}

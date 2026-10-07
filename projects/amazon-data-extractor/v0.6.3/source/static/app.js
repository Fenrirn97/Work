(() => {
  const app = document.querySelector("[data-tab-app]");
  if (app) {
    const buttons = [...app.querySelectorAll("[data-tab-button]")];
    const panels = [...app.querySelectorAll("[data-tab-panel]")];
    const selectTab = (name) => {
      const validName = panels.some((panel) => panel.dataset.tabPanel === name) ? name : "live";
      buttons.forEach((button) => {
        const selected = button.dataset.tabButton === validName;
        button.classList.toggle("active", selected);
        button.setAttribute("aria-selected", String(selected));
      });
      panels.forEach((panel) => {
        panel.hidden = panel.dataset.tabPanel !== validName;
      });
    };
    buttons.forEach((button) => button.addEventListener("click", () => selectTab(button.dataset.tabButton)));
    selectTab(app.dataset.initialTab || "live");
  }

  const exitForm = document.querySelector("[data-exit-form]");
  if (exitForm) {
    exitForm.addEventListener("submit", (event) => {
      if (!window.confirm("Close Amazon Data Extractor?")) {
        event.preventDefault();
      }
    });
  }
})();
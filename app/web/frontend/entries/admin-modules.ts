import "../admin-modules/styles.css";
import { ModulesController } from "../admin-modules/controller";

const root = document.getElementById("admin-modules-root");
if (root) {
  const controller = new ModulesController(root);
  void controller.init();
  window.addEventListener("pagehide", event => { if (!event.persisted) controller.destroy(); });
}

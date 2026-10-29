import "../admin-users/styles.css";
import { UsersController } from "../admin-users/controller";

const root = document.getElementById("admin-users-root");
if (root) {
  const controller = new UsersController(root);
  void controller.init();
  window.addEventListener("pagehide", event => { if (!event.persisted) controller.destroy(); });
}

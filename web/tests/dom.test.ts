// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";

import { h } from "../src/ui/dom";

describe("h()", () => {
  it("entende tag, classes e #id (a linha de status depende do id)", () => {
    const element = h("p.hint#status", {}, "ok");
    expect([element.tagName, element.className, element.id, element.textContent]).toEqual(["P", "hint", "status", "ok"]);
  });

  it("liga eventos e ignora atributos falsos", () => {
    let clicks = 0;
    const button = h("button.button.primary", { type: "button", disabled: false, onclick: () => clicks++ });
    button.click();
    expect([clicks, button.className, button.hasAttribute("disabled")]).toEqual([1, "button primary", false]);
  });
});

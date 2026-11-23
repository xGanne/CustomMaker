/** Utilitários mínimos de interface (sem framework). */

type Child = Node | string | null | undefined | false;

/** h("p.hint#status", { onclick }, "Texto") — elemento com classes, id, atributos e filhos. */
export function h<K extends keyof HTMLElementTagNameMap>(
  spec: K | `${K}.${string}` | `${K}#${string}`,
  props: Partial<Record<string, unknown>> = {},
  ...children: Child[]
): HTMLElementTagNameMap[K] {
  const [selector, id] = spec.split("#");
  const [tag, ...classes] = selector.split(".") as [K, ...string[]];
  const element = document.createElement(tag);
  if (classes.length) element.className = classes.join(" ");
  if (id) element.id = id;
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key.startsWith("on") && typeof value === "function") {
      element.addEventListener(key.slice(2), value as EventListener);
    } else if (key === "dataset") {
      Object.assign(element.dataset, value);
    } else if (key in element && typeof value !== "string") {
      (element as unknown as Record<string, unknown>)[key] = value;
    } else {
      element.setAttribute(key, value === true ? "" : String(value));
    }
  }
  for (const child of children) if (child) element.append(child);
  return element;
}

export { store } from "../core/storage";

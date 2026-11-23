/**
 * Tela de enquadrar: a borda fica parada no centro e a imagem se move por baixo.
 *
 * Durante o gesto a imagem anda só por CSS (transform na GPU): fica fluido em
 * qualquer celular. A imagem mostrada é a mesma (já reduzida) que vira a custom. A borda por cima é desenhada com as mesmas máscaras da
 * custom final. A custom exata sai depois, do enquadramento (posição e tamanho),
 * pelo mesmo render do PC.
 */
import { BORDA_POS, fitFraming, pan, zoomAt, type Framing } from "../core/framing";
import type { Raster } from "../core/raster";
import { rules } from "../core/rules";
import { h } from "./dom";

export interface EditorOptions {
  /** a imagem que vira a custom (a tela mostra exatamente estes pixels) */
  source: Promise<Raster>;
  /** enquadramento salvo; null = encaixe automático quando a imagem carregar */
  framing: Framing | null;
  /** borda (225x350, transparente no meio) já na cor e estilo atuais */
  overlay: Raster;
  /** chamado ao fim de cada gesto, com o enquadramento novo */
  onChange: (framing: Framing) => void;
  onError?: (message: string) => void;
}

export interface Editor {
  element: HTMLElement;
  setOverlay: (overlay: Raster) => void;
  /** volta ao encaixe automático */
  fit: () => void;
}

const DOUBLE_TAP_MS = 300;
const TAP_SLOP_PX = 10;

export function createEditor(options: EditorOptions): Editor {
  const { width: W, height: H } = rules.border;
  const image = h("canvas.picture", { width: 1, height: 1 });
  const overlayCanvas = h("canvas", { width: W, height: H });
  const frame = h("div.frame", {}, overlayCanvas);
  const stage = h("div.stage", {}, image, frame, h("div.stage-hint", {}, "Carregando a imagem..."));

  let framing: Framing | null = options.framing;
  let natural: [number, number] | null = null;
  let fitWidth = 0;
  let scale = 1;
  let frameLeft = 0;
  let frameTop = 0;

  function drawOverlay(overlay: Raster): void {
    overlayCanvas.getContext("2d")?.putImageData(new ImageData(overlay.data, overlay.width, overlay.height), 0, 0);
  }

  function layout(): void {
    const box = stage.getBoundingClientRect();
    if (!box.width || !box.height) return;
    // margem em volta da borda para ver (e alcançar) o que fica de fora
    scale = Math.min((box.width - 48) / W, (box.height - 48) / H);
    frameLeft = (box.width - W * scale) / 2;
    frameTop = (box.height - H * scale) / 2;
    Object.assign(frame.style, {
      width: `${W * scale}px`,
      height: `${H * scale}px`,
      transform: `translate(${frameLeft}px, ${frameTop}px)`,
    });
    place();
  }

  function place(): void {
    if (!framing) return;
    const [x, y] = framing.pos;
    const [w, hgt] = framing.size;
    image.style.width = `${w * scale}px`;
    image.style.height = `${hgt * scale}px`;
    image.style.transform = `translate(${frameLeft + (x - BORDA_POS[0]) * scale}px, ${frameTop + (y - BORDA_POS[1]) * scale}px)`;
  }

  function commit(): void {
    if (framing) options.onChange(framing);
  }

  function fit(): void {
    if (!natural) return;
    const fitted = fitFraming(natural[0], natural[1]);
    if (!fitted) return;
    framing = fitted;
    place();
    commit();
  }

  /** ponto da tela -> coordenadas da custom */
  function toCustom(clientX: number, clientY: number): [number, number] {
    const box = stage.getBoundingClientRect();
    return [(clientX - box.left - frameLeft) / scale + BORDA_POS[0], (clientY - box.top - frameTop) / scale + BORDA_POS[1]];
  }

  // ── gestos ──────────────────────────────────────────────────────────
  const pointers = new Map<number, { x: number; y: number }>();
  let gestureMoved = false;
  let downAt = 0;
  let downPoint = { x: 0, y: 0 };
  let lastTap = { at: 0, x: 0, y: 0 };

  stage.addEventListener("pointerdown", (event) => {
    stage.setPointerCapture(event.pointerId);
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pointers.size === 1) {
      gestureMoved = false;
      downAt = event.timeStamp;
      downPoint = { x: event.clientX, y: event.clientY };
    }
  });

  stage.addEventListener("pointermove", (event) => {
    const previous = pointers.get(event.pointerId);
    if (!previous || !framing) return;
    const current = { x: event.clientX, y: event.clientY };
    if (Math.hypot(current.x - downPoint.x, current.y - downPoint.y) > TAP_SLOP_PX) gestureMoved = true;
    if (pointers.size === 1) {
      framing = pan(framing, (current.x - previous.x) / scale, (current.y - previous.y) / scale);
    } else if (pointers.size === 2) {
      const [other] = [...pointers.entries()].filter(([id]) => id !== event.pointerId).map(([, p]) => p);
      const before = Math.hypot(previous.x - other.x, previous.y - other.y);
      const after = Math.hypot(current.x - other.x, current.y - other.y);
      const midBefore = toCustom((previous.x + other.x) / 2, (previous.y + other.y) / 2);
      const midAfter = toCustom((current.x + other.x) / 2, (current.y + other.y) / 2);
      if (before > 0) framing = zoomAt(framing, after / before, midBefore[0], midBefore[1], fitWidth);
      framing = pan(framing, midAfter[0] - midBefore[0], midAfter[1] - midBefore[1]);
    }
    pointers.set(event.pointerId, current);
    place();
  });

  function pointerEnd(event: PointerEvent): void {
    if (!pointers.delete(event.pointerId)) return;
    if (pointers.size > 0) return;
    // toque rápido sem arrastar, duas vezes seguidas: encaixe automático
    const isTap = !gestureMoved && event.timeStamp - downAt < 250;
    if (isTap) {
      const near = Math.hypot(event.clientX - lastTap.x, event.clientY - lastTap.y) < 40;
      if (event.timeStamp - lastTap.at < DOUBLE_TAP_MS && near) {
        lastTap = { at: 0, x: 0, y: 0 };
        fit();
        return;
      }
      lastTap = { at: event.timeStamp, x: event.clientX, y: event.clientY };
    }
    if (gestureMoved) commit();
  }
  stage.addEventListener("pointerup", pointerEnd);
  stage.addEventListener("pointercancel", pointerEnd);

  // roda do mouse (para testar no PC): zoom em torno do cursor
  let wheelTimer = 0;
  stage.addEventListener("wheel", (event) => {
    if (!framing) return;
    event.preventDefault();
    const [cx, cy] = toCustom(event.clientX, event.clientY);
    framing = zoomAt(framing, Math.exp(-event.deltaY * 0.0015), cx, cy, fitWidth);
    place();
    window.clearTimeout(wheelTimer);
    wheelTimer = window.setTimeout(commit, 200);
  }, { passive: false });

  // ── imagem ──────────────────────────────────────────────────────────
  options.source.then(
    (raster) => {
      image.width = raster.width;
      image.height = raster.height;
      image.getContext("2d")?.putImageData(new ImageData(raster.data, raster.width, raster.height), 0, 0);
      natural = [raster.width, raster.height];
      fitWidth = fitFraming(natural[0], natural[1])?.size[0] ?? natural[0];
      stage.querySelector(".stage-hint")?.remove();
      if (!framing) {
        fit();
      } else {
        place();
      }
    },
    () => {
      const hint = stage.querySelector(".stage-hint");
      if (hint) hint.textContent = "Não foi possível abrir a imagem.";
      options.onError?.("Não foi possível abrir a imagem.");
    },
  );

  new ResizeObserver(layout).observe(stage);
  drawOverlay(options.overlay);

  return { element: stage, setOverlay: drawOverlay, fit };
}

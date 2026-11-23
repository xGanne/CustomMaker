/**
 * Página de teste da fase M1: escolhe uma foto, aplica o auto fit e mostra a
 * custom nos 5 estilos de borda — o mesmo render do PC, pixel a pixel.
 */
import "./style.css";

import { autoFit } from "./core/autofit";
import { applyBorder, loadMasks, type BorderMasks } from "./core/borders";
import { encodePng } from "./core/png";
import { createRaster, type Raster } from "./core/raster";
import { renderToBorder } from "./core/render";
import { rules, type BorderStyle } from "./core/rules";

// a borda fica em coordenadas próprias, como no canvas do PC
const BORDA_POS: [number, number] = [0, 0];
// fotos de celular passam de 4000 px: acima disto, decodifica já reduzida
const MAX_SOURCE_SIDE = 2400;

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const fileInput = $<HTMLInputElement>("file");
const colorSelect = $<HTMLSelectElement>("color");
const customColor = $<HTMLInputElement>("custom-color");
const statusLine = $<HTMLParagraphElement>("status");
const results = $<HTMLElement>("results");

let masks: BorderMasks | null = null;
let source: Raster | null = null;
let sourceName = "exemplo";
const downloadUrls: string[] = [];

for (const [name, hex] of Object.entries(rules.colors)) {
  colorSelect.add(new Option(name, hex, false, hex === "#89b4fa"));
}
colorSelect.add(new Option("Personalizada", "custom"));

function currentColor(): string {
  return colorSelect.value === "custom" ? customColor.value : colorSelect.value;
}

async function getMasks(): Promise<BorderMasks> {
  if (!masks) {
    const response = await fetch(`${import.meta.env.BASE_URL}${rules.masks.file}`);
    if (!response.ok) throw new Error(`máscaras de borda: HTTP ${response.status}`);
    masks = await loadMasks(await response.arrayBuffer());
  }
  return masks;
}

async function decodeFile(file: File): Promise<Raster> {
  // sem conversão de cor: o PC (Pillow) também ignora o perfil de cor da imagem
  const options: ImageBitmapOptions = { colorSpaceConversion: "none", premultiplyAlpha: "none" };
  let bitmap = await createImageBitmap(file, options);
  const longest = Math.max(bitmap.width, bitmap.height);
  if (longest > MAX_SOURCE_SIDE) {
    const scale = MAX_SOURCE_SIDE / longest;
    const [w, h] = [Math.round(bitmap.width * scale), Math.round(bitmap.height * scale)];
    bitmap.close();
    bitmap = await createImageBitmap(file, { ...options, resizeWidth: w, resizeHeight: h, resizeQuality: "high" });
  }
  const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
  const context = canvas.getContext("2d");
  if (!context) throw new Error("canvas indisponível");
  context.drawImage(bitmap, 0, 0);
  const image = context.getImageData(0, 0, bitmap.width, bitmap.height);
  bitmap.close();
  return { width: image.width, height: image.height, data: image.data };
}

/** Imagem de exemplo: degradê com xadrez (funciona sem escolher foto). */
function sampleImage(): Raster {
  const raster = createRaster(600, 840);
  for (let y = 0; y < raster.height; y++) {
    for (let x = 0; x < raster.width; x++) {
      const i = (y * raster.width + x) * 4;
      raster.data[i] = (x * 255) / raster.width;
      raster.data[i + 1] = 90 + ((y * 120) / raster.height);
      raster.data[i + 2] = ((Math.floor(x / 30) + Math.floor(y / 30)) % 2) * 120 + 100;
      raster.data[i + 3] = 255;
    }
  }
  return raster;
}

async function render(): Promise<void> {
  if (!source) return;
  statusLine.textContent = "Gerando...";
  const fit = autoFit(source.width, source.height, BORDA_POS);
  if (!fit) {
    statusLine.textContent = "Imagem pequena demais.";
    return;
  }
  const [w, h, x, y] = fit;
  const borderMasks = await getMasks();
  const started = performance.now();
  const cropped = renderToBorder(source, [x, y], [w, h], BORDA_POS);
  const renderMs = performance.now() - started;

  downloadUrls.splice(0).forEach((url) => URL.revokeObjectURL(url));
  results.replaceChildren();
  const color = currentColor();
  for (const style of Object.keys(rules.styles) as BorderStyle[]) {
    const custom = applyBorder(cropped, style, color, borderMasks);
    const card = document.createElement("figure");
    card.className = "custom";
    const canvas = document.createElement("canvas");
    canvas.width = custom.width;
    canvas.height = custom.height;
    canvas.getContext("2d")?.putImageData(new ImageData(custom.data, custom.width, custom.height), 0, 0);
    const url = URL.createObjectURL(new Blob([(await encodePng(custom)) as BlobPart], { type: "image/png" }));
    downloadUrls.push(url);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${sourceName}_${style}.png`;
    link.textContent = `${rules.styles[style]} — baixar`;
    card.append(canvas, link);
    results.append(card);
  }
  statusLine.textContent =
    `Foto ${source.width}×${source.height} enquadrada em ${w}×${h}. ` +
    `Render no aparelho: ${Math.round(renderMs)} ms.`;
}

fileInput.addEventListener("change", async () => {
  const file = fileInput.files?.[0];
  if (!file) return;
  statusLine.textContent = "Abrindo a foto...";
  try {
    source = await decodeFile(file);
    sourceName = file.name.replace(/\.[^.]+$/, "") || "custom";
    await render();
  } catch (error) {
    statusLine.textContent = `Não foi possível abrir a foto: ${(error as Error).message}`;
  }
});

$<HTMLButtonElement>("sample").addEventListener("click", async () => {
  source = sampleImage();
  sourceName = "exemplo";
  await render();
});

// ?exemplo abre já com a imagem de exemplo (também usado para testar o build)
if (new URLSearchParams(location.search).has("exemplo")) {
  source = sampleImage();
  void render();
}

colorSelect.addEventListener("change", () => void render());
customColor.addEventListener("input", () => {
  colorSelect.value = "custom";
  void render();
});

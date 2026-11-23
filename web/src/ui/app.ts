/**
 * Telas do app (fase M2): Buscar -> Escolher -> Gerar.
 *
 * Navegação pelo #hash: cada tela é uma entrada no histórico, então o botão
 * "voltar" do Android volta uma tela em vez de fechar o app.
 */
import { applyBorder, loadMasks, type BorderMasks } from "../core/borders";
import {
  buildTags,
  DanbooruError,
  importSource,
  searchPosts,
  suggestTags,
  type Post,
  type SearchOptions,
} from "../core/danbooru";
import { BORDA_POS, fitFraming, framingKey, rounded, type Framing } from "../core/framing";
import { decodeImage, fetchImage } from "../core/images";
import { isNativeApp } from "../core/network";
import { encodePng } from "../core/png";
import { createRaster, type Raster } from "../core/raster";
import { renderToBorder } from "../core/render";
import { rules, type BorderStyle } from "../core/rules";
import { autoSelect } from "../core/scorer";
import { h, store } from "./dom";
import { createEditor } from "./editor";
import { handleBackButton, shareNative, type PngFile } from "./native";

const PAGE_SIZE = 40;
const RATING_BADGES: Record<string, [string, string]> = {
  g: ["G", "#a6e3a1"],
  s: ["S", "#f9e2af"],
  q: ["Q", "#fab387"],
  e: ["E", "#f38ba8"],
};

type View = "busca" | "escolher" | "enquadrar" | "gerar";

/** O que vira custom: um post do Danbooru ou uma foto do celular. */
interface Item {
  key: string;
  name: string;
  post?: Post;
  file?: File;
}

const state = {
  search: store.get<SearchOptions>("search", { query: "", rating: "Geral", sort: "Mais recentes", portraitOnly: false }),
  tags: "",
  page: 1,
  posts: [] as Post[],
  loading: false,
  selected: new Map<number, Post>(),
  photos: [] as File[],
  style: store.get<BorderStyle>("style", rules.defaultStyle),
  color: store.get<string>("color", "#89b4fa"),
  status: "",
  auto: null as AbortController | null,
  /** enquadramento escolhido por imagem (Item.key); sem entrada = encaixe automático */
  framings: new Map<string, Framing>(),
  editIndex: 0,
};

const root = document.getElementById("app") as HTMLElement;
let masksPromise: Promise<BorderMasks> | null = null;

function masks(): Promise<BorderMasks> {
  masksPromise ??= fetch(`${import.meta.env.BASE_URL}${rules.masks.file}`)
    .then((response) => {
      if (!response.ok) throw new Error(`máscaras de borda: HTTP ${response.status}`);
      return response.arrayBuffer();
    })
    .then(loadMasks);
  return masksPromise;
}

function currentView(): View {
  const view = location.hash.replace("#", "") as View;
  return view === "escolher" || view === "enquadrar" || view === "gerar" ? view : "busca";
}

function navigate(view: View): void {
  if (currentView() === view) render();
  else location.hash = view; // nova entrada no histórico: o "voltar" desfaz
}

function setStatus(text: string): void {
  state.status = text;
  const line = document.getElementById("status");
  if (line) line.textContent = text;
}

// ── Buscar ──────────────────────────────────────────────────────────────

let suggestAbort: AbortController | null = null;
let suggestTimer = 0;

function onQueryInput(input: HTMLInputElement, list: HTMLDataListElement): void {
  window.clearTimeout(suggestTimer);
  suggestTimer = window.setTimeout(async () => {
    suggestAbort?.abort();
    suggestAbort = new AbortController();
    const suggestions = await suggestTags(input.value, suggestAbort.signal);
    // a sugestão substitui só a última palavra digitada
    const prefix = input.value.replace(/\S+$/, "");
    list.replaceChildren(...suggestions.map((s) => h("option", { value: `${prefix}${s.name}` }, `${s.postCount} posts`)));
  }, 250);
}

async function runSearch(page: number): Promise<void> {
  state.loading = true;
  setStatus(`Buscando a página ${page}...`);
  try {
    const posts = await searchPosts(state.tags, page, PAGE_SIZE);
    if (!posts.length && page > 1) {
      setStatus(`A página ${page} não tem resultados — fim da busca.`);
      return;
    }
    state.page = page;
    state.posts = posts;
    setStatus(posts.length ? "" : "Nenhum resultado. Tente outras tags ou outra classificação.");
  } catch (error) {
    setStatus(error instanceof DanbooruError ? error.message : `Erro na busca: ${(error as Error).message}`);
  } finally {
    state.loading = false;
    render();
  }
}

async function startSearch(): Promise<void> {
  state.tags = buildTags(state.search);
  if (!state.search.query.trim()) {
    setStatus("Digite ao menos uma tag (ex.: o nome do personagem).");
    return;
  }
  store.set("search", state.search);
  const recent = store.get<string[]>("recent", []).filter((q) => q !== state.search.query.trim());
  store.set("recent", [state.search.query.trim(), ...recent].slice(0, 10));
  state.selected.clear();
  state.posts = [];
  navigate("escolher");
  await runSearch(1);
}

function selectField(label: string, options: string[], value: string, onChange: (value: string) => void) {
  const select = h("select", { onchange: () => onChange(select.value) },
    ...options.map((option) => h("option", { value: option, selected: option === value }, option)));
  return h("label.field", {}, label, select);
}

function searchView(): HTMLElement {
  const list = h("datalist", { id: "sugestoes" });
  const input = h("input", {
    type: "search", value: state.search.query, placeholder: "ex.: hatsune_miku", list: "sugestoes",
    enterkeyhint: "search", autocapitalize: "off", autocomplete: "off", spellcheck: false,
    oninput: () => {
      state.search.query = input.value;
      onQueryInput(input, list);
    },
  });
  const photoInput = h("input", {
    type: "file", accept: "image/*", multiple: true, hidden: true,
    onchange: () => {
      state.photos = [...(photoInput.files ?? [])];
      if (state.photos.length) {
        state.editIndex = 0;
        navigate("enquadrar");
      }
    },
  });
  const recent = store.get<string[]>("recent", []);
  return h("section.view", {},
    h("header", {}, h("h1", {}, "CustomMaker"),
      h("p.hint", {}, "Busque no Danbooru, escolha as imagens e gere as customs do Mudae.")),
    h("form.search", {
      onsubmit: (event: Event) => {
        event.preventDefault();
        input.blur(); // fecha o teclado
        void startSearch();
      },
    },
    h("label.field.wide", {}, "Tags", input, list),
    selectField("Classificação", Object.keys(rules.danbooru.ratingTags), state.search.rating, (v) => {
      state.search.rating = v;
    }),
    selectField("Ordenar", Object.keys(rules.danbooru.sortTags), state.search.sort, (v) => {
      state.search.sort = v;
    }),
    h("label.check", {}, h("input", {
      type: "checkbox", checked: state.search.portraitOnly,
      onchange: (event: Event) => {
        state.search.portraitOnly = (event.target as HTMLInputElement).checked;
      },
    }), "Só imagens em pé (retrato)"),
    h("button.button.primary.wide", { type: "submit" }, "Buscar")),
    recent.length ? h("div.chips", {}, ...recent.map((query) => h("button.chip", {
      type: "button",
      onclick: () => {
        state.search.query = query;
        void startSearch();
      },
    }, query))) : null,
    h("div.or", {}, "ou"),
    h("label.button.wide", {}, "Usar fotos do celular", photoInput),
    h("p.hint#status", {}, state.status));
}

// ── Escolher ────────────────────────────────────────────────────────────

function toggle(post: Post): void {
  if (state.selected.has(post.id)) state.selected.delete(post.id);
  else state.selected.set(post.id, post);
  render();
}

async function runAuto(countInput: HTMLInputElement): Promise<void> {
  if (state.auto) {
    state.auto.abort();
    return;
  }
  const count = Math.max(1, Math.min(Number(countInput.value) || 10, PAGE_SIZE * rules.danbooru.autoSelectMaxPages));
  state.auto = new AbortController();
  const { signal } = state.auto;
  render();
  try {
    const result = await autoSelect({
      count,
      firstPage: state.page,
      firstPosts: state.posts,
      pageSize: PAGE_SIZE,
      fetchPage: (page) => searchPosts(state.tags, page, PAGE_SIZE, signal),
      loadPreview: (post) => post.preview_file_url
        ? fetchImage(post.preview_file_url, signal, 400).catch(() => null)
        : Promise.resolve(null),
      alreadySelected: new Set(state.selected.keys()),
      signal,
      onProgress: setStatus,
    });
    result.posts.forEach((post) => state.selected.set(post.id, post));
    const where = result.pages > 1 ? `nas páginas ${state.page}–${result.lastPage}` : "nesta página";
    const elsewhere = result.posts.filter((p) => !state.posts.some((q) => q.id === p.id)).length;
    const parts = [
      result.posts.length
        ? `${result.posts.length} escolhida(s) ${where} — revise e toque em Gerar.`
        : `Nada ${where} parece um bom custom (quadrinho, P&B, grupo, sem personagem...). Tente outra busca.`,
      elsewhere ? `${elsewhere} de outras páginas (→ para ver).` : "",
      result.excluded ? `${result.excluded} questionável/explícito fora.` : "",
      result.posts.length && result.posts.length < count ? `Só ${result.posts.length} de ${count} pareceram bons.` : "",
    ];
    state.status = parts.filter(Boolean).join(" ");
  } catch (error) {
    state.status = (error as Error).name === "AbortError" ? "Auto cancelado." : `Auto: ${(error as Error).message}`;
  } finally {
    state.auto = null;
    render();
  }
}

function resultCard(post: Post): HTMLElement {
  const selected = state.selected.has(post.id);
  const badge = RATING_BADGES[String(post.rating ?? "")];
  return h("button.card", { type: "button", "aria-pressed": String(selected), onclick: () => toggle(post) },
    // no app Android o pedido da imagem é refeito pelo próprio app (DanbooruWebViewClient)
    h("img", { src: post.preview_file_url ?? "", alt: `#${post.id}`, loading: "lazy" }),
    badge ? h("span.badge", { style: `background:${badge[1]}` }, badge[0]) : null,
    selected ? h("span.tick", {}, "✓") : null);
}

function chooseView(): HTMLElement {
  const countInput = h("input", { type: "number", min: 1, max: PAGE_SIZE * rules.danbooru.autoSelectMaxPages, value: 10, inputmode: "numeric" });
  const label = state.search.query.trim() || state.tags;
  return h("section.view", {},
    h("header.bar", {},
      h("button.icon", { type: "button", "aria-label": "Voltar", onclick: () => history.back() }, "←"),
      h("div.title", {}, h("strong", {}, label), h("span.hint", {}, `página ${state.page} · ${state.selected.size} escolhida(s)`))),
    h("div.toolbar", {},
      h("label.auto", {}, "★ Auto", countInput),
      h(state.auto ? "button.button.danger" : "button.button.primary", {
        type: "button", disabled: state.loading || !state.posts.length,
        onclick: () => void runAuto(countInput),
      }, state.auto ? "Cancelar" : "Escolher"),
      h("button.button", {
        type: "button", disabled: !state.selected.size,
        onclick: () => {
          state.selected.clear();
          render();
        },
      }, "Limpar")),
    h("p.hint#status", {}, state.loading ? "Buscando..." : state.status),
    h("div.grid", {}, ...state.posts.map(resultCard)),
    h("nav.pager", {},
      h("button.button", { type: "button", disabled: state.loading || state.page <= 1, onclick: () => void runSearch(state.page - 1) }, "← Anterior"),
      h("span", {}, `pág. ${state.page}`),
      h("button.button", { type: "button", disabled: state.loading || state.posts.length < PAGE_SIZE, onclick: () => void runSearch(state.page + 1) }, "Próxima →")),
    h("footer.actions", {},
      h("button.button.primary.wide", {
        type: "button", disabled: !state.selected.size,
        onclick: () => {
          state.photos = [];
          state.editIndex = 0;
          navigate("enquadrar");
        },
      }, `Enquadrar (${state.selected.size})`)));
}

// ── Gerar ───────────────────────────────────────────────────────────────

/** Recortes já calculados, por imagem e enquadramento (cor/estilo não mudam o recorte). */
const crops = new Map<string, Raster>();
let generation = 0;

function items(): Item[] {
  if (state.photos.length) {
    return state.photos.map((file, i) => ({ key: `foto:${i}:${file.name}:${file.size}`, name: file.name.replace(/\.[^.]+$/, ""), file }));
  }
  return [...state.selected.values()].map((post) => ({ key: `post:${post.id}`, name: String(post.id), post }));
}

/** Endereço da imagem para a tela de enquadrar (a mesma que vira a custom). */
const photoUrls = new Map<string, string>();

function sourceUrl(item: Item): string | null {
  if (item.file) {
    let url = photoUrls.get(item.key);
    if (!url) {
      url = URL.createObjectURL(item.file);
      photoUrls.set(item.key, url);
    }
    return url;
  }
  return item.post ? importSource(item.post) : null;
}

async function cropFor(item: Item): Promise<Raster> {
  const saved = state.framings.get(item.key);
  const cacheKey = `${item.key}|${saved ? framingKey(saved) : "auto"}`;
  const cached = crops.get(cacheKey);
  if (cached) return cached;
  let source: Raster;
  if (item.file) {
    source = await decodeImage(item.file);
  } else {
    const url = sourceUrl(item);
    if (!url) throw new Error("post sem imagem");
    source = await fetchImage(url);
  }
  // sem enquadramento salvo (não passou pela tela de enquadrar): encaixe automático
  const framing = saved ? rounded(saved) : fitFraming(source.width, source.height);
  if (!framing) throw new Error("imagem pequena demais");
  const cropped = renderToBorder(source, framing.pos, framing.size, BORDA_POS);
  crops.set(cacheKey, cropped);
  return cropped;
}

const built: PngFile[] = [];

async function buildAll(grid: HTMLElement): Promise<void> {
  const run = ++generation;
  const list = items();
  built.length = 0;
  const borderMasks = await masks();
  let renderMs = 0;
  let rendered = 0;
  for (const [index, item] of list.entries()) {
    if (run !== generation) return; // trocou cor/estilo no meio: recomeçou
    setStatus(`Gerando ${index + 1} de ${list.length}...`);
    const card = grid.children[index] as HTMLElement;
    try {
      const fresh = !crops.has(item.key);
      const started = performance.now();
      const cropped = await cropFor(item);
      if (fresh) {
        renderMs += performance.now() - started;
        rendered++;
      }
      const custom = applyBorder(cropped, state.style, state.color, borderMasks);
      const png = new Blob([(await encodePng(custom)) as BlobPart], { type: "image/png" });
      if (run !== generation) return;
      const file = { name: `${item.name}_custom.png`, png };
      built.push(file);
      const canvas = h("canvas", { width: custom.width, height: custom.height });
      canvas.getContext("2d")?.putImageData(new ImageData(custom.data, custom.width, custom.height), 0, 0);
      // no app Android não existe download: abre o menu de compartilhar do sistema
      const save = isNativeApp()
        ? h("button.link", { type: "button", onclick: () => void shareFiles([file]) }, "Compartilhar")
        : h("a", { href: URL.createObjectURL(png), download: file.name }, "Baixar");
      card.replaceChildren(canvas, save);
    } catch (error) {
      card.replaceChildren(h("p.hint", {}, `Falhou: ${(error as Error).message}`));
    }
  }
  const timing = rendered ? ` Tempo médio por custom no aparelho: ${Math.round(renderMs / rendered)} ms (download + render).` : "";
  setStatus(`${built.length} de ${list.length} custom(s) prontas.${timing}`);
}

async function shareFiles(pngs: PngFile[]): Promise<void> {
  if (!pngs.length) return;
  if (isNativeApp()) {
    try {
      await shareNative(pngs);
    } catch (error) {
      // fechar o menu sem escolher também cai aqui: só avisa se for outra coisa
      const message = (error as Error).message ?? "";
      if (!/cancel/i.test(message)) setStatus(`Não foi possível compartilhar: ${message}`);
    }
    return;
  }
  const files = pngs.map((b) => new File([b.png], b.name, { type: "image/png" }));
  if (navigator.canShare?.({ files })) {
    try {
      await navigator.share({ files, title: "Customs" });
      return;
    } catch (error) {
      if ((error as Error).name === "AbortError") return; // fechou o menu de compartilhar
    }
  }
  for (const file of files) {
    const link = h("a", { href: URL.createObjectURL(file), download: file.name });
    link.click();
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
}

/** Cor, cor personalizada e estilo da borda (enquadrar e gerar). */
function borderControls(onChange: () => void): HTMLElement[] {
  const colorSelect = h("select", {
    onchange: () => {
      if (colorSelect.value !== "custom") state.color = colorSelect.value;
      store.set("color", state.color);
      onChange();
    },
  },
  ...Object.entries(rules.colors).map(([name, hex]) => h("option", { value: hex, selected: hex === state.color }, name)),
  h("option", { value: "custom", selected: !Object.values(rules.colors).includes(state.color) }, "Personalizada"));
  const customColor = h("input", {
    type: "color", value: state.color,
    oninput: () => {
      state.color = customColor.value;
      colorSelect.value = "custom";
      store.set("color", state.color);
      onChange();
    },
  });
  const styleSelect = h("select", {
    onchange: () => {
      state.style = styleSelect.value as BorderStyle;
      store.set("style", state.style);
      onChange();
    },
  }, ...Object.entries(rules.styles).map(([key, label]) => h("option", { value: key, selected: key === state.style }, label)));
  return [
    h("label.field", {}, "Cor", colorSelect),
    h("label.field", {}, "Personalizada", customColor),
    h("label.field", {}, "Estilo", styleSelect),
  ];
}

// ── Enquadrar ───────────────────────────────────────────────────────────

/** Só a borda (225x350, transparente no meio), na cor e estilo atuais. */
function borderOverlay(borderMasks: BorderMasks): Raster {
  return applyBorder(createRaster(rules.border.width, rules.border.height), state.style, state.color, borderMasks);
}

function frameView(): HTMLElement {
  const list = items();
  state.editIndex = Math.max(0, Math.min(state.editIndex, list.length - 1));
  const item = list[state.editIndex];
  const editor = createEditor({
    src: sourceUrl(item) ?? "",
    framing: state.framings.get(item.key) ?? null,
    overlay: createRaster(rules.border.width, rules.border.height),
    onChange: (framing) => state.framings.set(item.key, framing),
    onError: setStatus,
  });
  const refreshOverlay = () => void masks().then((m) => editor.setOverlay(borderOverlay(m)));
  refreshOverlay();
  const go = (delta: number) => {
    state.editIndex += delta;
    render();
  };
  return h("section.view", {},
    h("header.bar", {},
      h("button.icon", { type: "button", "aria-label": "Voltar", onclick: () => history.back() }, "←"),
      h("div.title", {}, h("strong", {}, `Enquadrar · ${state.editIndex + 1} de ${list.length}`),
        h("span.hint", {}, "Arraste para mover · dois dedos para zoom · toque duplo para encaixar"))),
    editor.element,
    h("div.toolbar", {}, ...borderControls(refreshOverlay),
      h("button.button", { type: "button", onclick: () => editor.fit() }, "Encaixar")),
    h("nav.pager", {},
      h("button.button", { type: "button", disabled: state.editIndex <= 0, onclick: () => go(-1) }, "◀ Anterior"),
      h("span", {}, `${state.editIndex + 1}/${list.length}`),
      h("button.button", { type: "button", disabled: state.editIndex >= list.length - 1, onclick: () => go(1) }, "Próxima ▶")),
    h("p.hint#status", {}, ""),
    h("footer.actions", {},
      h("button.button.primary.wide", { type: "button", onclick: () => navigate("gerar") }, `Gerar customs (${list.length})`)));
}

// ── Gerar (continuação) ─────────────────────────────────────────────────

function generateView(): HTMLElement {
  const list = items();
  const grid = h("div.customs", {}, ...list.map(() => h("figure.custom", {}, h("p.hint", {}, "Na fila..."))));

  const view = h("section.view", {},
    h("header.bar", {},
      h("button.icon", { type: "button", "aria-label": "Voltar", onclick: () => history.back() }, "←"),
      h("div.title", {}, h("strong", {}, `${list.length} custom(s)`),
        h("span.hint", {}, "Como você enquadrou (o que não passou pela tela de enquadrar usa o encaixe automático)"))),
    h("div.toolbar", {}, ...borderControls(() => void buildAll(grid))),
    h("p.hint#status", {}, ""),
    grid,
    h("footer.actions", {},
      h("button.button.primary.wide", { type: "button", onclick: () => void shareFiles([...built]) },
        isNativeApp() ? "Compartilhar todas" : "Compartilhar / baixar todas")));
  queueMicrotask(() => void buildAll(grid));
  return view;
}

// ── Montagem ────────────────────────────────────────────────────────────

function render(): void {
  const view = currentView();
  if ((view === "gerar" || view === "enquadrar") && !items().length) {
    history.replaceState(null, "", "#busca");
    root.replaceChildren(searchView());
    return;
  }
  if (view !== "gerar") generation++; // saiu da tela: para de gerar
  const screens: Record<View, () => HTMLElement> = {
    busca: searchView,
    escolher: chooseView,
    enquadrar: frameView,
    gerar: generateView,
  };
  root.replaceChildren(screens[view]());
}

export function startApp(): void {
  window.addEventListener("hashchange", render);
  if (isNativeApp()) handleBackButton();
  const params = new URLSearchParams(location.search);
  // ?q=tags abre já buscando (links de busca); ?auto=N roda o ★ Auto em seguida
  const query = params.get("q");
  render();
  if (query) {
    state.search.query = query;
    void startSearch().then(() => {
      const auto = Number(params.get("auto"));
      if (auto > 0) {
        const input = h("input", { value: String(auto) });
        void runAuto(input);
      }
    });
  }
}

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
import { renderInBackground } from "../core/render-client";
import { rules, type BorderStyle } from "../core/rules";
import { ImgChestAuthError, uploadCustoms } from "../core/imgchest";
import { mudaeCommands, suggestTitle } from "../core/mudae";
import { autoSelect, parseAvoidTags } from "../core/scorer";
import { h, store } from "./dom";
import { createEditor } from "./editor";
import { copyText, handleBackButton, shareNative, type PngFile } from "./native";

// preferências do aparelho (tela Configurações)
const settings = {
  get token(): string {
    return store.get<string>("imgchestToken", "");
  },
  get avoidTags(): string {
    // null = nunca configurado (lista padrão do PC); "" = limpou de propósito
    return store.get<string | null>("avoidTags", null) ?? rules.scorer.defaultAvoidTags;
  },
  get pageSize(): number {
    return store.get<number>("pageSize", 40);
  },
};
const RATING_BADGES: Record<string, [string, string]> = {
  g: ["G", "#a6e3a1"],
  s: ["S", "#f9e2af"],
  q: ["Q", "#fab387"],
  e: ["E", "#f38ba8"],
};

type View = "busca" | "escolher" | "enquadrar" | "gerar" | "config";

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
  autoCount: store.get<number>("autoCount", 10),
  /** muda a cada busca nova: resultado (de busca ou Auto) de uma busca anterior é descartado */
  searchId: 0,
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
  return ["escolher", "enquadrar", "gerar", "config"].includes(view) ? view : "busca";
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

let searchAbort: AbortController | null = null;

async function runSearch(page: number): Promise<void> {
  // uma busca por vez: a anterior (outra página ou outra busca) é cancelada,
  // senão a resposta dela poderia chegar depois e tomar o lugar desta
  searchAbort?.abort();
  const controller = new AbortController();
  searchAbort = controller;
  state.loading = true;
  state.status = `Buscando a página ${page}...`;
  render(); // desativa os botões de página enquanto carrega
  try {
    const posts = await searchPosts(state.tags, page, settings.pageSize, controller.signal);
    if (controller.signal.aborted) return;
    if (!posts.length && page > 1) {
      state.status = `A página ${page} não tem resultados — fim da busca.`;
      return;
    }
    state.page = page;
    state.posts = posts;
    state.status = posts.length ? "" : "Nenhum resultado. Tente outras tags ou outra classificação.";
  } catch (error) {
    if (controller.signal.aborted) return; // trocada por outra busca
    state.status = error instanceof DanbooruError ? error.message : `Erro na busca: ${(error as Error).message}`;
  } finally {
    if (searchAbort === controller) {
      searchAbort = null;
      state.loading = false;
      render();
    }
  }
}

async function startSearch(): Promise<void> {
  state.tags = buildTags(state.search);
  if (!state.search.query.trim()) {
    setStatus("Digite ao menos uma tag (ex.: o nome do personagem).");
    return;
  }
  store.set("search", state.search);
  // o Auto da busca anterior não pode marcar nada nesta
  state.searchId++;
  state.auto?.abort();
  state.auto = null;
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
    h("header.home", {},
      h("h1", {}, "CustomMaker"),
      h("button.icon", { type: "button", "aria-label": "Configurações", onclick: () => navigate("config") }, "⚙")),
    h("header", {},
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

async function runAuto(): Promise<void> {
  if (state.auto) {
    state.auto.abort();
    return;
  }
  const count = Math.max(1, Math.min(state.autoCount || 10, settings.pageSize * rules.danbooru.autoSelectMaxPages));
  const controller = new AbortController();
  const { signal } = controller;
  const searchId = state.searchId;
  state.auto = controller;
  render();
  try {
    const result = await autoSelect({
      count,
      firstPage: state.page,
      firstPosts: state.posts,
      pageSize: settings.pageSize,
      fetchPage: (page) => searchPosts(state.tags, page, settings.pageSize, signal),
      loadPreview: (post) => post.preview_file_url
        ? fetchImage(post.preview_file_url, signal, 400).catch(() => null)
        : Promise.resolve(null),
      alreadySelected: new Set(state.selected.keys()),
      avoidTags: parseAvoidTags(settings.avoidTags),
      signal,
      onProgress: (message) => {
        if (searchId === state.searchId) setStatus(message);
      },
    });
    if (searchId !== state.searchId) return; // já é outra busca: descarta
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
    if (searchId !== state.searchId) return;
    state.status = (error as Error).name === "AbortError" ? "Auto cancelado." : `Auto: ${(error as Error).message}`;
  } finally {
    if (state.auto === controller) {
      state.auto = null;
      render();
    }
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
  // o número fica no estado: a tela é redesenhada a cada toque numa miniatura
  const countInput = h("input", {
    type: "number", min: 1, max: settings.pageSize * rules.danbooru.autoSelectMaxPages,
    value: state.autoCount, inputmode: "numeric",
    oninput: () => {
      const value = Math.trunc(Number(countInput.value));
      if (value > 0) {
        state.autoCount = value;
        store.set("autoCount", value);
      }
    },
  });
  const label = state.search.query.trim() || state.tags;
  return h("section.view", {},
    h("header.bar", {},
      h("button.icon", { type: "button", "aria-label": "Voltar", onclick: () => history.back() }, "←"),
      h("div.title", {}, h("strong", {}, label), h("span.hint", {}, `página ${state.page} · ${state.selected.size} escolhida(s)`))),
    h("div.toolbar", {},
      h("label.auto", {}, "★ Auto", countInput),
      h(state.auto ? "button.button.danger" : "button.button.primary", {
        type: "button", disabled: state.loading || !state.posts.length,
        onclick: () => void runAuto(),
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
      h("button.button", { type: "button", disabled: state.loading || state.posts.length < settings.pageSize, onclick: () => void runSearch(state.page + 1) }, "Próxima →")),
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
  const cropped = await renderInBackground(source, framing.pos, framing.size, BORDA_POS);
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

let building: Promise<void> = Promise.resolve();

/** Resultado do envio: o comando $ai (em partes de até 2000 caracteres) com botão de copiar. */
function uploadResult(title: string, links: string[], errors: string[]): HTMLElement {
  const copyButton = (label: string, text: string) => {
    const button: HTMLButtonElement = h("button.button", {
      type: "button",
      onclick: async () => {
        try {
          await copyText(text);
          button.textContent = "Copiado ✓";
        } catch {
          button.textContent = "Não deu para copiar: segure o texto";
        }
      },
    }, label);
    return button;
  };
  const commands = links.length ? mudaeCommands(title, links) : [];
  return h("div.upload-result", {},
    links.length ? h("p", {}, `${links.length} imagem(ns) enviada(s). Cole no Discord:`) : null,
    ...commands.map((command, i) => h("div.command", {},
      h("pre", {}, command),
      copyButton(commands.length > 1 ? `Copiar comando ${i + 1} de ${commands.length}` : "Copiar comando", command))),
    links.length ? copyButton("Copiar só os links", links.join("\n")) : null,
    ...errors.map((error) => h("p.error", {}, error)));
}

function generateView(): HTMLElement {
  const list = items();
  const grid = h("div.customs", {}, ...list.map(() => h("figure.custom", {}, h("p.hint", {}, "Na fila..."))));
  const rebuild = () => {
    building = buildAll(grid);
  };
  const titleInput = h("input", {
    type: "text", value: state.photos.length ? "" : suggestTitle(state.search.query),
    placeholder: "Nome do personagem no Mudae", autocapitalize: "words", enterkeyhint: "send",
  });
  const result = h("div", {});
  const sendButton: HTMLButtonElement = h("button.button.primary", {
    type: "button",
    onclick: async () => {
      const title = titleInput.value.trim();
      if (!title) {
        setStatus("Digite o nome da custom (o mesmo nome do personagem no Mudae).");
        titleInput.focus();
        return;
      }
      if (!settings.token) {
        setStatus("Falta o token do ImgChest: abra as Configurações (⚙ na tela inicial).");
        return;
      }
      sendButton.disabled = true;
      try {
        await building; // termina de gerar antes de enviar
        setStatus(`Enviando ${built.length} custom(s) ao ImgChest...`);
        const { links, errors } = await uploadCustoms([...built], title, settings.token, {
          onProgress: (done, total) => setStatus(`Enviando ao ImgChest: ${done} de ${total}...`),
        });
        result.replaceChildren(uploadResult(title, links, errors));
        setStatus(errors.length ? "Enviado com erros — veja abaixo." : "Pronto! Copie o comando e cole no Discord.");
        result.scrollIntoView({ behavior: "smooth", block: "start" });
      } catch (error) {
        setStatus(error instanceof ImgChestAuthError ? error.message : `Falhou: ${(error as Error).message}`);
      } finally {
        sendButton.disabled = false;
      }
    },
  }, "Enviar ao ImgChest");

  const view = h("section.view", {},
    h("header.bar", {},
      h("button.icon", { type: "button", "aria-label": "Voltar", onclick: () => history.back() }, "←"),
      h("div.title", {}, h("strong", {}, `${list.length} custom(s)`),
        h("span.hint", {}, "Como você enquadrou (o que não passou pela tela de enquadrar usa o encaixe automático)"))),
    h("div.toolbar", {}, ...borderControls(rebuild)),
    h("p.hint#status", {}, ""),
    grid,
    h("section.upload", {},
      h("label.field.wide", {}, "Nome da custom no Mudae", titleInput),
      result),
    h("footer.actions.split", {},
      h("button.button", { type: "button", onclick: () => void shareFiles([...built]) },
        isNativeApp() ? "Compartilhar" : "Baixar"),
      sendButton));
  queueMicrotask(rebuild);
  return view;
}

// ── Configurações ───────────────────────────────────────────────────────

function configView(): HTMLElement {
  const token = h("input", {
    type: "password", value: settings.token, placeholder: "cole aqui o token", autocomplete: "off", spellcheck: false,
    onchange: () => store.set("imgchestToken", token.value.trim()),
  });
  const avoid = h("textarea", {
    rows: 4, value: settings.avoidTags, spellcheck: false,
    onchange: () => store.set("avoidTags", avoid.value.split(/\s+/).filter(Boolean).join(" ")),
  });
  const pageSize = h("select", { onchange: () => store.set("pageSize", Number(pageSize.value)) },
    ...[20, 40, 100, 200].map((n) => h("option", { value: n, selected: n === settings.pageSize }, `${n}`)));
  return h("section.view", {},
    h("header.bar", {},
      h("button.icon", { type: "button", "aria-label": "Voltar", onclick: () => history.back() }, "←"),
      h("div.title", {}, h("strong", {}, "Configurações"))),
    h("section.settings", {},
      h("label.field.wide", {}, "Token do ImgChest", token),
      h("p.hint", {}, "Pegue em imgchest.com › Settings › API. Fica salvo só neste aparelho e só é enviado ao ImgChest."),
      h("div.toolbar", {},
        h("button.button", {
          type: "button",
          onclick: () => {
            token.type = token.type === "password" ? "text" : "password";
          },
        }, "Mostrar/ocultar"),
        h("button.button", {
          type: "button",
          onclick: () => {
            token.value = "";
            store.set("imgchestToken", "");
            setStatus("Token apagado deste aparelho.");
          },
        }, "Esquecer token")),
      h("label.field.wide", {}, "Tags que o ★ Auto evita", avoid),
      h("p.hint", {}, "Pesam contra, não excluem. Questionável e explícito ficam sempre de fora. Vazio: não evita nenhuma."),
      h("button.button", {
        type: "button",
        onclick: () => {
          avoid.value = rules.scorer.defaultAvoidTags;
          store.set("avoidTags", null);
        },
      }, "Voltar à lista padrão"),
      h("label.field.wide", {}, "Resultados por página", pageSize),
      h("p.hint", {}, "Mais resultados dão mais candidatos ao ★ Auto em uma página só."),
      h("p.hint#status", {}, "")));
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
    config: configView,
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
        state.autoCount = Math.trunc(auto);
        void runAuto();
      }
    });
  }
}

# Plano — Fase 2: estilos de borda, guias, lupa e ajustes de cor

> Origem: ideias do PhotoCraft (`storytold/photocraft`) adaptadas a customs 225×350.
> Escrito em 2026-10-28 sobre o commit `8790ed8`.
>
> Fases: [Fase 1](PLANO_FASE_1.md) → **2 (este arquivo)** → [Fase 3](PLANO_FASE_3.md).

## ✅ Status (atualizado em 2026-10-31) — Fase 2 implementada

| Item | Situação |
|---|---|
| 6 — Lupa no conta-gotas | **Feito** `4fa0f4f`: lupa 11×11 com pixel central e hex; Shift+clique só nesta imagem; Ctrl média 3×3; Esc sai. |
| 5 — Guias e encaixe | **Feito** `f5944af`: terços e centro (G fixa, salvo na config), encaixe nas bordas/centro ao arrastar (Alt desliga; posições por código não encaixam), área vazia hachurada com aviso uma vez por imagem. 5.d (encaixe do rosto) não feito — opcional. |
| 4 — Estilos de borda | **Feito** `fca32a2`: Simples (byte a byte igual ao antigo), Dupla, Brilho, Degradê, Sombra; prévia = export; sessão, presets, paleta (`Ctrl+K`); desabilitado com animação; autoteste do exe cobre o Brilho. |
| 7 — Ajustes de cor | **Feito** `7adf05c` (core) e `65e2a84`: brilho/contraste/saturação ao vivo, nitidez só na Revisão/export, desfazer por gesto, Resetar, Aplicar a todas, sessão, preset opcional; autoteste do exe cobre um ajuste. |

Diferenças em relação ao plano, por decisão:
- **Aplicar a todas** cria o passo de desfazer só na imagem atual (o histórico é por imagem e
  as outras não estão abertas); as demais podem ser resetadas uma a uma.
- A lista de imagens **não** ganhou indicador para imagens com ajuste de cor.
- Largura mínima da janela subiu com o seletor de estilo; os combos da barra de opções
  foram estreitados para compensar.

Correção encontrada no caminho: o menu de histórico da Fase 1 quebrava com 2+ passos
anteriores (`_time` não importado) — corrigido em `65e2a84`, com teste.

## Visão geral

| # | Item | Ganho | Esforço | Commits previstos |
|---|------|-------|---------|-------------------|
| 4 | Estilos de borda (dupla, brilho, degradê, sombra) | Customs mais bonitas sem editor externo | Médio | 3 |
| 5 | Guias e encaixe no enquadramento | Enquadrar mais rápido e sem "buracos" | Médio | 3 |
| 6 | Lupa no conta-gotas | Pegar a cor certa (olho, cabelo) de primeira | Baixo | 2 |
| 7 | Ajustes leves de cor (não destrutivos) | Salvar imagens apagadas/escuras do Danbooru | Alto | 4 |

**Pré-requisito:** Fase 1, item 1 (snapshot de undo como dataclass). Os itens 4 e 7
acrescentam campos ao snapshot, ao estado do editor, à sessão, aos presets e às tasks de
export.

**Ordem sugerida: 6 → 5 → 4 → 7** (do mais isolado para o que mais mexe no pipeline). O 6
só toca o canvas; o 5 só o canvas e a janela; o 4 e o 7 passam pelo pipeline inteiro
(estado → sessão → preset → task → worker → revisão).

### Regra de ouro desta fase: prévia == export
Tudo o que aparece no canvas tem que sair igual no arquivo. Para isso:
- o desenho de estilos e os ajustes de cor ficam **em `src/core/`** (funções puras de PIL)
  e são chamados **pelos dois lados**: canvas e `batch_worker`;
- nenhuma "versão aproximada" em Qt (`QPainter`) para a prévia;
- cada item tem um teste que compara a prévia com o export.

### Checklist de "campo novo no estado" (vale para os itens 4 e 7)
Ao criar um campo novo de estado da custom, ele tem que passar por **todos** estes pontos:

| Ponto | Arquivo |
|---|---|
| Estado | `EditorState` em [editor_state.py](src/core/editor_state.py) (+ `remove_image`, `reset_images`) |
| Sessão | `snapshot_session` / `apply_session` em [session_store.py](src/core/session_store.py) |
| Undo | `Snapshot` em `src/core/history.py` (Fase 1) |
| Preset | `_save_preset` em [editor_tab.py](src/qt/tabs/editor_tab.py) e `apply_preset` em [adjustments_mixin.py](src/qt/mixins/adjustments_mixin.py) |
| Task de export | `BatchController._get_task_data` em [batch_controller.py](src/controllers/batch_controller.py) |
| Render | `process_image_task`, `render_custom_preview` em [batch_worker.py](src/core/batch_worker.py) |
| Self-test do exe | [self_test.py](src/self_test.py) (um caso com o campo ligado) |
| "Não exportada" | marcar `image_dirty` quando o campo mudar |

**Sessão:** `apply_session` rejeita qualquer `version != SESSION_VERSION`. **Não subir a
versão** para campos novos: gravar as chaves novas e lê-las com `.get(..., padrão)`.
Assim as sessões salvas antes da atualização continuam abrindo.

---

## Item 4 — Estilos de borda

### Objetivo
Além da borda sólida atual (5 px), oferecer estilos que ficam bonitos no tamanho em que o
Mudae mostra a custom:

| Estilo | Desenho (tudo dentro de 225×350) |
|---|---|
| **Simples** (atual) | Retângulo de 5 px na cor escolhida. Precisa sair **byte a byte igual** ao de hoje. |
| **Dupla** | Linha externa de 3 px + vão de 2 px (mostra a imagem) + linha interna de 1 px. |
| **Brilho** | Borda de 5 px + brilho para dentro: a borda desfocada (`GaussianBlur`, raio ~6) com ~55% de opacidade sobre a imagem. |
| **Degradê** | Borda de 5 px preenchida com um degradê vertical da cor escolhida até uma versão mais clara (mesma matiz, `L` + 25% em HLS). |
| **Sombra** | Borda de 5 px + sombra interna escura (preto, ~40%, desfocado) logo dentro da borda, dando profundidade. |

**Restrição importante:** a custom tem exatamente 225×350 e não existe área *fora* da
borda. "Brilho externo" e "sombra projetada" do Photoshop não cabem — os efeitos vão
**para dentro**, sobre a imagem. Confirmar visualmente em 100% e no tamanho reduzido do
Discord antes de fechar os parâmetros.

### Estado atual (onde mexer)
- Export estático: `ImageProcessor.add_borda_to_image(cropped, cor)` em
  [image_processor.py](src/core/image_processor.py) (`draw.rectangle`, `width=BORDER_THICKNESS`).
- Animações: geram a própria borda como overlay (`overlay_only=True`) em
  [animation_processor.py](src/core/animation_processor.py).
- Prévia no canvas: `border_item` (`QGraphicsRectItem` com `QPen` de 5 px) em
  [image_canvas.py](src/qt/widgets/image_canvas.py). Já existe `preview_item` (z=12) usado
  pela prévia de animação (`set_preview_overlay`), que esconde o `border_item`.
- Barra de opções: `_build_options_bar` em [main_window.py](src/qt/main_window.py)
  (Borda, cor, Auto, Animação, Aplicar a Todas).

### Passo a passo

**4.a — Overlays de estilo no core**
1. Novo `src/core/border_styles.py`:
   ```python
   BORDER_STYLES = {"simples": "Simples", "dupla": "Dupla", "brilho": "Brilho",
                    "degrade": "Degradê", "sombra": "Sombra"}

   def border_overlay(style: str, color_hex: str, size=(BORDA_WIDTH, BORDA_HEIGHT)) -> Image:
       """RGBA do tamanho da custom: borda + efeito, transparente no resto."""

   def apply_border(cropped: Image, style: str, color_hex: str) -> Image:
       """cropped (RGBA 225x350) com a borda do estilo aplicada."""
   ```
2. `apply_border(..., "simples", ...)` **delega para o `add_borda_to_image` atual**, sem
   mudar uma linha dele — garante zero regressão. Os outros estilos usam
   `cropped.alpha_composite(border_overlay(...))`.
3. Cache em memória por `(style, color, size)` com `functools.lru_cache(maxsize=64)`
   sobre uma função que devolve **bytes** do overlay (imagens PIL não são hasheáveis e
   não devem ser compartilhadas mutáveis): reconstruir o `Image` via `Image.frombytes`.
   No pool de processos cada worker tem o seu cache — tudo bem.
4. Estilo desconhecido (preset antigo/arquivo editado) → cai em `simples` com log de
   aviso.

**4.b — Pipeline de estado e export**
1. Estado global: `EditorState.border_style: str = "simples"`. **Sem estilo por imagem
   nesta fase** (manter simples; a borda individual por imagem continua sendo só a cor).
2. Seguir o checklist do topo: sessão (`"border_style"`), preset (`"border_style"`,
   sempre incluído — é parte do visual, como a animação), snapshot de undo **não** precisa
   (é global, como a animação hoje), task (`data["border_style"]`).
3. `batch_worker._process_cropped`: no ramo estático, trocar
   `ImageProcessor.add_borda_to_image(cropped, border_color)` por
   `apply_border(cropped, border_style, border_color)`. `render_custom_preview` idem.
4. **Animações:** nesta fase o estilo vale só para "Nenhuma". Com animação ativa, o combo
   de estilo fica desabilitado com a dica "Os estilos valem para customs sem animação".
   (Combinar efeitos com animações — ex. brilho pulsante — fica como ideia futura.)

**4.c — UI e prévia**
1. Barra de opções: `QLabel("Estilo:")` + `QComboBox` com `BORDER_STYLES`, entre a cor e
   o botão Auto. Mudar → `editor_state.border_style`, marca todas as imagens como não
   exportadas (`image_dirty`), atualiza a prévia e grava a sessão (o autosave já cobre).
2. Prévia: para `simples`, nada muda (`border_item` com `QPen`). Para os demais:
   - gerar `border_overlay(style, cor)` (rápido: 225×350) e mostrar num **novo**
     `style_overlay_item` (`QGraphicsPixmapItem`, z=11, posicionado na borda, como o
     `preview_item`), escondendo o `border_item`;
   - `style_overlay_item.setAcceptedMouseButtons(Qt.NoButton)` — senão ele **bloqueia o
     arrasto da imagem** por estar por cima;
   - reposicionar em `_layout_border` junto com o `border_item` (redimensionar a janela
     desloca a borda);
   - antes/depois (B) e prévia de animação escondem o overlay e o restauram depois.
3. Revisão em grade: já usa `render_custom_preview` → mostra o estilo sem código extra.

### Casos de borda
- Cor muito escura + "Sombra": a sombra some. Aceitável; não tentar compensar.
- "Degradê" com branco: `L` + 25% satura em branco → usar o inverso (escurecer) quando
  `L > 0.75`.
- Pick color / cor automática continuam definindo só a cor; o estilo é independente.

### Testes
- `tests/test_border_styles.py`: `apply_border("simples")` == `add_borda_to_image` (pixels
  idênticos); todo estilo devolve 225×350 RGBA; o centro (longe da borda) não é alterado
  pelos estilos **Simples** e **Dupla**; estilo desconhecido cai em simples.
- Prévia == export: o overlay mostrado no canvas é o mesmo `border_overlay` usado no
  worker (comparar bytes).
- Sessão e preset: ida e volta preservam o estilo; sessão antiga sem a chave abre com
  `simples`.
- O combo fica desabilitado com animação ativa.

### Critérios de aceite
- [ ] Cinco estilos selecionáveis, com prévia instantânea no canvas.
- [ ] Export e Revisão idênticos à prévia.
- [ ] Customs "Simples" continuam byte a byte iguais às de antes.
- [ ] Estilo é salvo na sessão e nos presets.

### Commits
1. `feat: estilos de borda no core (dupla, brilho, degrade, sombra)`
2. `feat: estilo de borda no export, sessao e presets`
3. `feat(UI): seletor de estilo de borda com previa no canvas`

---

## Item 5 — Guias e encaixe no enquadramento

### Objetivo
1. **Guias:** regra dos terços e linhas de centro desenhadas **dentro da borda**,
   visíveis enquanto a imagem é arrastada (e fixas com a tecla **G**).
2. **Encaixe (snap):** ao arrastar, as bordas da imagem "grudam" nas bordas da custom e o
   centro da imagem gruda no centro horizontal. `Alt` segurado desliga o encaixe.
3. **Aviso de área vazia:** se a imagem não cobre a borda inteira, a parte descoberta
   (que sai **transparente** no export) aparece hachurada em vermelho, com dica na status
   bar.

### Estado atual (onde mexer)
- Arrasto: `_DraggablePixmapItem` em [image_canvas.py](src/qt/widgets/image_canvas.py),
  com `ItemIsMovable` e `ItemSendsGeometryChanges`; `itemChange` só trata
  `ItemPositionHasChanged`.
- Teclas que não podem roubar campos de texto: `keyPressEvent` de
  [main_window.py](src/qt/main_window.py) (padrão já usado pela tecla B).
- A cena não tem escala (o zoom muda o tamanho do item), então 1 unidade de cena = 1 px
  de tela; o limiar de encaixe pode ser fixo em pixels.

### Passo a passo

**5.a — Guias**
1. No `ImageCanvas`, criar um `QGraphicsItemGroup` `guides_item` (z=10.5, abaixo do
   `border_item`, acima da imagem) com 2 linhas verticais e 2 horizontais nos terços e
   1 linha vertical de centro, em `QPen` tracejado, 1 px, cor `tokens()["text_secondary"]`
   com alfa ~120. `setAcceptedMouseButtons(Qt.NoButton)`.
2. Reposicionar em `_layout_border` (junto da borda).
3. Visibilidade: aparece em `mousePressEvent` do item arrastável e some no
   `mouseReleaseEvent`; com o modo fixo (`set_guides_pinned(bool)`), fica sempre visível.
4. Tecla **G** (sem modificadores, sem auto-repeat) em `keyPressEvent` da janela alterna
   o modo fixo; status bar "Guias fixas: ligadas/desligadas". Persistir em
   `app_config["canvas_guides_pinned"]`.

**5.b — Encaixe**
1. Tratar `QGraphicsItem.ItemPositionChange` em `_DraggablePixmapItem.itemChange`
   (antes de a posição ser aplicada) e devolver a posição ajustada:
   ```python
   if change == ItemPositionChange and self._snap_fn:
       value = self._snap_fn(value)   # QPointF -> QPointF
   ```
2. `ImageCanvas._snap_position(point)`:
   - candidatos X: borda esquerda da imagem → borda esquerda da custom; direita →
     direita; centro da imagem → centro da custom. Candidatos Y: topo → topo,
     base → base;
   - escolher, por eixo, o candidato mais próximo dentro do limiar
     (`SNAP_THRESHOLD_PX = 8`);
   - `QApplication.keyboardModifiers() & Qt.AltModifier` → sem encaixe;
   - só durante arrasto do mouse (flag ligada no press, desligada no release) — o encaixe
     **não** pode alterar posições definidas por código (auto fit, undo, sessão), que
     também passam por `setPos`.
3. Realce: a linha de guia correspondente ao encaixe ativo fica na cor de destaque
   (`tokens()["accent"]`) enquanto encaixada.
4. Undo: o arrasto continua gerando um único snapshot "Mover" (Fase 1); o encaixe não
   cria passos.

**5.c — Aviso de área vazia**
1. Após cada mudança de estado (`_emit_state_changed`), calcular a interseção do
   retângulo da imagem com o retângulo da borda. Se não cobrir tudo, desenhar as faixas
   descobertas num `QGraphicsPathItem` (z=10.6) com hachura vermelha translúcida
   (`Qt.BDiagPattern`, `tokens()["error"]`).
2. A janela mostra na status bar, uma vez por imagem: "Parte da custom está vazia e
   ficará transparente — Alt+B ajusta à borda."
3. Lógica de geometria em função pura (`uncovered_regions(image_rect, border_rect)` em
   `src/core/image_processor.py`) para testar sem Qt.

**5.d (opcional) — Encaixe do rosto no terço superior**
- Quando o Ajuste Inteligente já detectou rostos para a imagem (guardar a caixa do rosto
  escolhido em `_face_cycle`), incluir como candidato Y "centro do rosto → linha do terço
  superior". Só se o 5.b estiver estável.

### Casos de borda
- Imagem menor que a borda nos dois eixos: os candidatos de borda conflitam com o de
  centro; preferir o centro (mais útil) quando ambos estão no limiar.
- Antes/depois (B) ativo: esconder guias e hachura.
- Prévia de animação: guias e hachura ficam **abaixo** do `preview_item` (z=12), então
  não poluem a prévia.

### Testes
- `uncovered_regions`: totalmente coberta → vazio; deslocada 10 px à direita → faixa de
  10 px à esquerda; menor que a borda → quatro faixas.
- `_snap_position` (canvas offscreen): ponto a 5 px da borda esquerda encaixa; a 20 px
  não; com Alt não encaixa; posições definidas por `set_image_state` não são alteradas.
- Tecla G alterna e persiste.

### Critérios de aceite
- [ ] Guias aparecem ao arrastar e podem ficar fixas com G.
- [ ] Bordas e centro encaixam; Alt desliga.
- [ ] Área vazia aparece hachurada e some ao cobrir a borda.
- [ ] Auto fit, undo e sessão não são afetados pelo encaixe.

### Commits
1. `feat(canvas): guias de tercos e centro dentro da borda (G fixa)`
2. `feat(canvas): encaixe nas bordas e no centro ao arrastar (Alt desliga)`
3. `feat(canvas): destaque da area vazia que sairia transparente`

---

## Item 6 — Lupa no conta-gotas

### Objetivo
Com o **Pick Color** ativo, uma lupa segue o cursor mostrando ~11×11 pixels ampliados,
com o pixel central destacado, o hex e uma amostra da cor. Clique aplica (como hoje).

Extras de baixo custo:
- **Shift+clique** aplica a cor **só na imagem atual** (borda individual), usando
  `individual_bordas` / `custom_borda_hex_individual`, que já existem.
- **Ctrl+clique** usa a **média 3×3** em volta do ponto (evita pegar um pixel de ruído
  de JPEG).
- **Esc** sai do modo Pick Color.

### Estado atual (onde mexer)
- Modo: `toggle_color_picker` / `on_canvas_color_picked` em
  [main_window.py](src/qt/main_window.py); o canvas lê o pixel em `mousePressEvent` de
  [image_canvas.py](src/qt/widgets/image_canvas.py) a partir de `_base_image` (a prévia
  da imagem, já com edições de pixel).
- O sinal `color_picked = Signal(str)` só carrega a cor.

### Passo a passo

**6.a — Lupa**
1. `set_color_pick_enabled(True)` passa a ligar `self.viewport().setMouseTracking(True)`
   e a criar (uma vez) `self._loupe = QLabel(self.viewport())` com
   `Qt.WA_TransparentForMouseEvents` e objectName `CanvasLoupe` (estilo no
   [theme.py](src/qt/theme.py): fundo `surface_elevated`, borda `border_strong`, raio
   `radius_sm`).
2. `mouseMoveEvent` (só com o modo ativo e imagem carregada):
   - converter a posição para coordenadas de `_base_image` (mesmo cálculo do
     `mousePressEvent` — extrair para `_image_pixel_at(view_pos) -> (x, y) | None`);
   - recortar a janela 11×11 com `Image.crop` (preenchendo com transparente fora da
     imagem), ampliar ×11 com `Image.NEAREST`, desenhar a grade fina e o quadrado do
     pixel central (PIL ou `QPainter` sobre o `QPixmap`);
   - texto embaixo: `#RRGGBB` e uma amostra 16×16;
   - posicionar a 24 px abaixo/à direita do cursor, invertendo o lado perto das bordas do
     viewport.
3. `leaveEvent` e desligar o modo escondem a lupa; desligar também desliga o mouse
   tracking.
4. Custo: um recorte de 11×11 por movimento — desprezível; sem necessidade de throttle.

**6.b — Modificadores e Esc**
1. Trocar `color_picked = Signal(str)` por `Signal(str, bool)` (`cor`, `so_esta_imagem`).
2. Ctrl no clique → média 3×3 (`ImageStat.Stat(crop).mean` em RGB, ignorando pixels
   transparentes).
3. Em `on_canvas_color_picked(color, only_current)`: se `only_current`, gravar
   `individual_bordas[path] = "Cor Personalizada"` e
   `custom_borda_hex_individual[path] = color` (o mesmo caminho que o "Auto → Nesta
   imagem" usa em `apply_auto_border`), marcar a imagem como não exportada e atualizar o
   badge da lista; senão, o comportamento atual (cor global).
4. Esc com o modo ativo → desliga (tratar em `ImageCanvas.keyPressEvent` e no
   `keyPressEvent` da janela).
5. Atualizar a dica do botão na toolbar: "Pick Color — clique: todas · Shift+clique: só
   esta · Ctrl: média 3×3 · Esc: sair".

### Testes
- `_image_pixel_at` mapeia corretamente com zoom ≠ 1 e imagem deslocada.
- A lupa aparece com o modo ativo e some ao desligar (`isVisible`).
- Shift+clique grava borda individual e não muda a global; Ctrl usa média (imagem de
  teste com tabuleiro preto/branco → cinza).
- Esc desliga o modo.

### Critérios de aceite
- [ ] Lupa acompanha o cursor com o pixel central destacado e o hex.
- [ ] Shift+clique aplica só na imagem atual; Ctrl tira a média.
- [ ] Esc sai do modo.

### Commits
1. `feat(Pick Color): lupa com pixels ampliados e hex`
2. `feat(Pick Color): Shift aplica so na imagem atual, Ctrl usa media 3x3, Esc sai`

---

## Item 7 — Ajustes leves de cor (não destrutivos)

### Objetivo
Quatro controles por imagem — **Brilho, Contraste, Saturação, Nitidez** (−100…+100,
0 = neutro) — guardados como **parâmetros**, nunca gravados por cima da imagem. São
aplicados no export, aparecem na prévia e podem ser desfeitos, copiados para todas e
salvos em preset.

### Decisões técnicas (importantes para prévia == export)
1. **Onde aplicar no export:** depois do recorte 225×350 e **antes** da borda (a cor da
   borda nunca é afetada). É barato: 225×350 é minúsculo.
2. **Contraste não pode usar `ImageEnhance.Contrast`:** ele usa a **média de luminância
   da imagem** como pivô. Na prévia a imagem é a inteira; no export é só o recorte → as
   médias diferem e o resultado também. Usar contraste em torno de **128 fixo** via LUT:
   `out = (in − 128) × f + 128`. Brilho também via LUT (`out = in × f`). Os dois juntos
   viram **um único `Image.point`** por canal RGB (alfa intocado).
3. **Saturação:** `ImageEnhance.Color` é por pixel (mistura com o cinza do próprio pixel)
   → igual na prévia e no export.
4. **Nitidez:** depende da vizinhança e da escala (a prévia tem outra resolução) → **não
   é mostrada ao vivo no canvas**. Aparece na Revisão (que usa o caminho do export) e na
   dica do controle: "A nitidez aparece na Revisão". Isso evita uma prévia que mente.
5. Fatores: `f = 1 + v/100` para brilho/contraste/saturação (0…2); nitidez
   `f = 1 + v/50` (0…3), limitado.

### Estado atual (onde mexer)
- Pipeline: `render_custom_crop` / `process_image_task` / `_process_cropped` em
  [batch_worker.py](src/core/batch_worker.py).
- Prévia do canvas: `set_image` em [image_canvas.py](src/qt/widgets/image_canvas.py)
  (recria o item e guarda `_original_image` para o antes/depois).
- Aba Edição: [editor_tab.py](src/qt/tabs/editor_tab.py).
- Checklist de campo novo: ver topo deste arquivo.

### Passo a passo

**7.a — Core**
1. Novo `src/core/color_adjustments.py`:
   ```python
   NEUTRAL = {"brightness": 0, "contrast": 0, "saturation": 0, "sharpness": 0}

   def normalize(adj) -> dict          # valida, limita a -100..100, descarta chaves estranhas
   def is_neutral(adj) -> bool
   def apply_tone(image, adj) -> Image  # brilho+contraste (LUT) + saturação — prévia e export
   def apply_all(image, adj) -> Image   # apply_tone + nitidez — só export/revisão
   ```
   `apply_*` com ajuste neutro devolve **a própria imagem** (sem cópia) para não pesar o
   caminho comum.
2. Preservar o alfa: separar o canal A, ajustar RGB e recombinar.

**7.b — Estado, export, sessão, preset, undo**
1. `EditorState.image_adjustments: Dict[str, dict]` (só imagens com ajuste não neutro).
2. Checklist completo do topo. No undo, o `Snapshot` ganha `adjustments: dict`
   (Fase 1 já previu o campo) — desfazer volta os controles e a prévia.
3. Task: `data["adjustments"]`; em `render_custom_crop`, depois do
   `render_image_to_borda`: `cropped = apply_all(cropped, adj)`. Animações: aplicar no
   `cropped` antes de gerar os quadros (o conteúdo é o mesmo em todos).
4. Preset: checkbox opcional "Ajustes de cor" (como "Enquadramento padrão"); aplicar o
   preset grava os ajustes na imagem atual.
5. `image_dirty` ao mudar.

**7.c — Prévia ao vivo no canvas**
1. Novo `ImageCanvas.replace_display_image(pil)`: troca `_base_image` / `_base_pixmap`
   **mantendo** posição e tamanho (reaplica `_apply_size_transform`) e **sem** mexer em
   `_original_image` — assim o antes/depois (B) compara com o original sem ajustes,
   o que é exatamente o desejado.
2. Na janela, ao mover um controle: debounce de 60 ms (`QTimer` single-shot) → task na
   `task_runner` com número de sequência (descarta resultados velhos) que aplica
   `apply_tone` sobre a prévia **sem ajustes** guardada (`_preview_cache` / imagem
   editada) → `replace_display_image`. Prévia de até 2400 px: a LUT leva poucos ms; a
   saturação, dezenas — por isso fora da GUI thread.
3. Ao trocar de imagem, aplicar os ajustes daquela imagem na prévia carregada
   (`load_image` → depois do `set_image`).
4. A prévia de animação (`preview_item`) e a Revisão já saem do caminho do export.

**7.d — UI**
1. Grupo "Ajustes de cor" na aba Edição (abaixo de "Ajuste em Lote"; a aba já rola —
   commit `8790ed8`): quatro linhas `QLabel` + `QSlider(Qt.Horizontal, -100..100)` +
   valor numérico (`QSpinBox` pequeno, sincronizado).
2. Botões: **Resetar** (só esta imagem), **Aplicar a todas** (copia os quatro valores
   para todas as imagens; um único passo de undo por imagem), duplo clique num controle
   zera aquele controle.
3. Undo: um snapshot por **gesto** (no `sliderPressed`, ou no primeiro `valueChanged` de
   uma sequência de teclado, com o mesmo debounce de 0,5 s da roda do mouse — F8), nome
   "Brilho", "Contraste" etc.
4. Lista de imagens: as ajustadas ganham o indicador de "editada" que já existe.

### Casos de borda
- Imagem com edição de pixels (rotação/IA): os ajustes se aplicam **sobre** a imagem
  editada; rotacionar não zera os ajustes.
- Cor automática da borda (`suggest_border_color`): passa a analisar o recorte **já
  ajustado** (senão sugere cor de uma imagem que não é a que vai sair).
- Imagem removida: `remove_image` limpa `image_adjustments[path]`.
- Valores corrompidos na sessão/preset: `normalize` descarta e loga.

### Testes
- `tests/test_color_adjustments.py`: neutro devolve a mesma instância; alfa preservado;
  contraste com pivô 128 dá o **mesmo pixel** na imagem inteira e num recorte (o teste
  que justifica a decisão 2); limites −100/+100.
- Export: imagem com brilho +50 sai mais clara que sem ajuste e a borda mantém a cor
  exata.
- Prévia == export (tom): `apply_tone` na prévia e o pixel correspondente do recorte
  exportado diferem ≤ 2 níveis (só pela reamostragem).
- Undo/redo, sessão e preset fazem ida e volta dos valores.

### Critérios de aceite
- [ ] Os quatro controles alteram a prévia ao vivo (exceto nitidez, que aparece na
      Revisão, com a dica explicando).
- [ ] O arquivo original nunca é alterado; os ajustes vivem na sessão.
- [ ] Undo, "Aplicar a todas" e presets funcionam com ajustes.
- [ ] A borda nunca muda de cor por causa de um ajuste.

### Commits
1. `feat: ajustes de cor nao destrutivos no core (brilho, contraste, saturacao, nitidez)`
2. `feat: ajustes de cor no export, sessao, presets e undo`
3. `feat(canvas): previa ao vivo dos ajustes de cor`
4. `feat(Edicao): controles de ajustes de cor com resetar e aplicar a todas`

---

## Definição de pronto da Fase 2
- Suíte verde no CI, incluindo os testes de prévia == export de cada item.
- `--self-test` do exe cobre um estilo de borda e um ajuste de cor.
- Teste manual: imagem escura do Danbooru → brilho/contraste → estilo "Brilho" → cor pela
  lupa com Shift (só esta) → Revisão → export; abrir os arquivos e comparar com o canvas.
- Este arquivo atualizado com o status de cada item.

# Plano — Fase 1: histórico, tamanho do export e paleta de comandos

> Origem: ideias do PhotoCraft (clone open source do Photoshop, `storytold/photocraft`),
> filtradas para o fluxo do CustomMaker. Escrito em 2026-10-28 sobre o commit `8790ed8`
> (252 testes passando).
>
> Fases: **1 (este arquivo)** → [Fase 2](PLANO_FASE_2.md) → [Fase 3](PLANO_FASE_3.md).

## ✅ Status (atualizado em 2026-10-31) — Fase 1 concluída

| Item | Situação |
|---|---|
| 1 — Histórico | **Feito**: 1.a `890ce06` (snapshot como dataclass); 1.b `41ac926` (nomes nos passos — tinha sido revertido durante a caça ao crash e foi reaplicado depois da correção); 1.c e 1.d `4798c2b` (`Ctrl+Alt+Z`, histórico na setinha do Desfazer com salto direto, Limpar histórico; comandos na paleta). |
| 2 — Tamanho no export | **Feito**: `0446c89` (encode_custom, bytes idênticos ao export antigo), `b61eab7` (Revisão: Calcular tamanhos, aviso, cache por conteúdo, limite em Configurações › Exportação), `e973e39` (total no resumo, aviso antes do upload com Revisar/Enviar/Cancelar). 2.d (reduzir GIF) não feito, por decisão do próprio plano. |
| 3 — Paleta de comandos | **Feito**: `51c9dca` (registro único, Ctrl+K / Ctrl+Shift+P, busca sem acento e com erro leve, bordas/animações/presets/enquadramento, recentes, dica de descoberta, atalhos derivados do registro). |

Correções encontradas no caminho:
- `25b8593` e `e373a60` — crash nativo intermitente das tasks em segundo plano (memória
  liberada duas vezes / QObject destruído fora da GUI thread). Suíte completa: de 4/10 com
  crash para 0/20.
- `5f3fe86` — o aviso de tamanho antes do upload codificava as customs duas vezes.
- `db2d7ce`, `a3ff8c3`, `8255151` — testes mais leves: exportação em threads (sem pool de
  processos), `scripts/test_changed.py` para rodar só o que mudou, Qt sem tela localmente.

Fora do escopo, por decisão: 2.d (reduzir GIF, depende de números reais) e o comando
"Limpar sessão" da paleta (a sessão já é oferecida/descartada ao abrir o app).

## Visão geral

| # | Item | Ganho | Esforço | Commits previstos |
|---|------|-------|---------|-------------------|
| 1 | Alternar último estado + histórico nomeado | Comparar e voltar ajustes sem perder nada | Médio | 3 |
| 2 | Tamanho estimado no export | Evitar upload que estoura limite / custom pesada | Médio | 3 |
| 3 | Paleta de comandos (`Ctrl+K`) | Achar e executar qualquer ação digitando | Médio | 3 |

**Ordem obrigatória: 1 → 2 → 3.**
- O item 1 troca o formato do snapshot de undo (tupla → dataclass). A Fase 2 (ajustes de
  cor, estilo de borda) precisa guardar campos novos no snapshot, então isso vem primeiro.
- O item 3 registra comandos de todas as funções. Fazê-lo por último permite incluir os
  comandos criados nos itens 1 e 2 ("Histórico…", "Calcular tamanhos").

**Já existe e não deve ser refeito:** o antes/depois segurando **B** (ou crase), feito no
F17. Ele mostra a imagem *original* encaixada na borda
(`ImageCanvas.show_original_preview` / `restore_edit_preview` em
[image_canvas.py](src/qt/widgets/image_canvas.py), acionado em `keyPressEvent` /
`keyReleaseEvent` de [main_window.py](src/qt/main_window.py)). O item 1 complementa isso
comparando com o *ajuste anterior*, não com o original.

---

## Item 1 — Alternar último estado + histórico nomeado

### Objetivo
1. **Alternar último estado** (`Ctrl+Alt+Z`, como o "Toggle Last State" do Photoshop):
   se a última ação foi uma edição, desfaz; se foi um desfazer, refaz. Apertar de novo
   volta. Serve para comparar "como estava" × "como ficou" num toque.
2. **Histórico nomeado:** cada passo do undo ganha um nome ("Auto fit", "Ajuste
   inteligente — rosto 2 de 3", "Arrastar", "Zoom", "Rotacionar à esquerda"…). Um menu
   no botão Desfazer da toolbar lista os passos da imagem atual; clicar num passo pula
   direto para ele.

### Estado atual (onde mexer)
- Snapshots: `_capture_current_snapshot()` em
  [image_loader_mixin.py](src/qt/mixins/image_loader_mixin.py) devolve a tupla
  `(imagem|None, pos, size, tinha_pixels_editados)`.
- Pilhas: `self._undo_stacks` (criado em `main_window.py`) e `self._redo_stacks`
  (`_redo_stack_map()`), ambos `dict[path] -> list[snapshot]`, limite de 20 em
  `save_state_for_undo()`.
- Consumidores da tupla que precisam mudar:
  - `_apply_snapshot`, `_drop_redo_stack`, `save_state_for_undo` (descarte do mais antigo);
  - `main_window.py`: o deslocamento das pilhas em `on_border_pos_changed` (por volta da
    linha 583), `_forget_image` (≈680) e a limpeza ao fechar (≈913).
- Chamadores de `save_state_for_undo()`: `apply_auto_fit`, `apply_intelligent_fit`,
  `rotate_current_image` ([adjustments_mixin.py](src/qt/mixins/adjustments_mixin.py)) e o
  sinal `image_canvas.interaction_started` (arrasto/roda/Ctrl+0).

### Passo a passo

**1.a — Snapshot vira dataclass (refatoração sem mudança de comportamento)**
1. Criar `src/core/history.py`:
   ```python
   @dataclass
   class Snapshot:
       image: Optional[Image.Image]   # só quando há edição de pixels (como hoje)
       pos: Tuple[int, int]
       size: Tuple[int, int]
       pixel_edited: bool
       label: str = ""
       timestamp: float = field(default_factory=time.monotonic)
   ```
   Deixar espaço explícito para a Fase 2: `adjustments: dict` e `border_style: str`
   entram aqui depois, com default — nenhum consumidor precisa mudar quando entrarem.
2. Trocar todos os pontos que desempacotam a tupla (`image, pos, size, x = snapshot`,
   `for image, *_rest in stack`) por acesso a atributo. Usar `grep -rn "_undo_stacks\|_redo_stack"`
   para não esquecer nenhum.
3. Rodar a suíte inteira **antes** de seguir — esse passo não pode mudar nada visível.
   Commit: `refactor: snapshot de undo vira dataclass com nome do passo`.

**1.b — Nomear os passos**
1. `save_state_for_undo(label="")` passa o nome adiante para o snapshot.
2. O snapshot guarda o estado **anterior** à ação; o `label` guarda o nome da **ação**
   que estava para acontecer. A lista do menu mostra **ações**, como o Photoshop: clicar
   numa ação leva ao estado logo **depois** dela. Exemplo, com três ações A1, A2, A3:
   ```
   undo = [S0 (label "A1"), S1 ("A2"), S2 ("A3")]   atual = depois de A3
   Menu:  A3  ● atual
          A2  → estado S2 (depois de A2, antes de A3) = voltar 1
          A1  → estado S1                             = voltar 2
          Início (como abriu) → estado S0             = voltar 3
   ```
   Ou seja: o item da ação `undo[i].label` fica na linha do estado `undo[i+1]` (ou do
   atual, para o último), e "Início" aponta para `undo[0]`. Ver o salto em 1.d.
3. Nomes por chamador:
   | Chamador | Nome |
   |---|---|
   | `apply_auto_fit` | `Auto fit` |
   | `apply_intelligent_fit` | `Ajuste inteligente` (+ ` — rosto i de n` quando n > 1; o índice só é conhecido depois da detecção, então atualizar o `label` do snapshot recém-empilhado) |
   | `rotate_current_image` | `Rotacionar à esquerda` / `à direita` |
   | arrasto (`_DraggablePixmapItem.mousePressEvent`) | `Mover` |
   | roda do mouse (`wheelEvent`) | `Zoom` |
   | `zoom_to_actual_size` | `Zoom 100%` |
4. Para o canvas informar *qual* interação começou, trocar `interaction_started = Signal()`
   por `Signal(str)` em [image_canvas.py](src/qt/widgets/image_canvas.py) e emitir
   `"Mover"`, `"Zoom"`, `"Zoom 100%"`. Em `main_window.py`, conectar a
   `lambda label: self.save_state_for_undo(label)`. Atualizar os testes que conectam
   esse sinal (`grep -rn interaction_started tests`).
5. Ao desfazer, o snapshot do estado atual que vai para o redo **herda o `label`** do
   snapshot desempilhado (é a mesma ação, agora "refazível"); ao refazer, o inverso. Sem
   isso, o redo e o menu perdem os nomes.
6. Mensagens da status bar no desfazer/refazer passam a citar o passo:
   `"Desfeito: Auto fit"` / `"Refeito: Zoom"`.

**1.c — Alternar último estado (`Ctrl+Alt+Z`)**
1. Guardar por imagem a última operação de histórico: `self._last_history_op[path]` ∈
   `{"edit", "undo", "redo"}`. `save_state_for_undo` grava `"edit"`; `undo_current_image`
   grava `"undo"`; `redo_current_image` grava `"redo"`.
2. `toggle_last_state()`: se a última op foi `"undo"` → `redo_current_image()`; senão →
   `undo_current_image()`. Sem nada para desfazer → status "Nada para comparar".
3. Status bar: `"Comparando com o passo anterior — Ctrl+Alt+Z de novo para voltar."`
4. Registrar em `_register_shortcuts` (QAction). Não há conflito com campos de texto
   (QLineEdit não usa `Ctrl+Alt+Z`).
5. Atenção ao deslocamento de borda (`on_border_pos_changed`): ele já desloca as pilhas;
   `_last_history_op` não guarda posições, então não precisa ajuste.

**1.d — Menu de histórico no botão Desfazer**
1. No `_build_toolbar`, o botão "Desfazer" vira `QToolButton` com
   `setPopupMode(QToolButton.MenuButtonPopup)` (clique = desfazer; setinha = menu).
   Aproveitar o estilo `hasMenu` já existente em [theme.py](src/qt/theme.py).
2. O menu é montado em `aboutToShow` (sempre atual), para a imagem atual:
   - no topo, em cinza itálico, as ações desfeitas que ainda podem ser refeitas (pilha
     de redo) — clicar avança até elas;
   - a ação atual em negrito com `●`, desabilitada;
   - abaixo, as ações anteriores (mais recente primeiro), cada uma com nome e tempo
     relativo ("Auto fit · há 2 min"), seguindo a correspondência do exemplo em 1.b;
   - por último `Início (como abriu)`;
   - separador e `Limpar histórico desta imagem`.
   - Pilha vazia → um único item desabilitado "Sem histórico".
3. **Pular N passos sem renderizar os intermediários** — `jump_history(steps)` (negativo
   = voltar). Para voltar N (N ≥ 1), com `undo=[S0..Sk]`, `atual=C`:
   ```
   redo.append(capture(C))
   repita N-1 vezes: redo.append(undo.pop())
   alvo = undo.pop(); _apply_snapshot(alvo)
   ```
   Avançar é simétrico, trocando as pilhas. Só o último `_apply_snapshot` mexe no canvas,
   então pular 15 passos custa o mesmo que 1 (importante quando há edição de pixels, que
   recarrega a imagem).
4. Nunca reter imagens descartadas: "Limpar histórico" fecha as imagens de todos os
   snapshots (`_dispose_images`), como `_drop_redo_stack` já faz.

### Casos de borda
- Imagem trocada no meio (navegação ←/→): o menu sempre reflete `self.current_path`.
- Imagem removida da lista: `_forget_image` já descarta as pilhas — também apagar
  `_last_history_op[path]` e `_face_cycle[path]`.
- Limite de 20: ao descartar o mais antigo, o menu simplesmente mostra menos itens.
- Antes/depois (B) ativo: `_before_after_active` suprime `state_changed`; bloquear
  `toggle_last_state` e `jump_history` enquanto ele estiver ativo (senão o canvas fica com
  o pixmap do original e o estado restaurado em cima).
- Exportação em andamento: o lote usa `batch_controller.frozen()`, então mexer no
  histórico durante o export é seguro — nada a fazer, só não regredir isso.

### Testes (`tests/test_history.py` + ajustes nos existentes)
- `Snapshot` é criado com label e o undo/redo continuam idênticos (rodar
  `test_image_loader_mixin.py` e `test_ui_flows.py` sem mudar asserts de comportamento).
- `toggle_last_state`: edição → toggle desfaz; toggle de novo refaz; após um undo manual,
  o toggle refaz.
- `jump_history(-3)` deixa as pilhas iguais a três undos seguidos, mas chama
  `_apply_snapshot` **uma vez** (patch com contador).
- Labels: auto fit, inteligente com 2 rostos (patch de `detect_faces_ranked`), rotação.
- Limpar histórico fecha as imagens (mock de `close`).

### Critérios de aceite
- [ ] `Ctrl+Alt+Z` alterna entre o ajuste atual e o anterior, quantas vezes quiser.
- [ ] A setinha do Desfazer lista os passos com nome e tempo; clicar pula direto.
- [ ] Undo/redo/antes-depois (B) continuam funcionando como antes.
- [ ] Memória: pular entre passos não cria cópias extras de imagem.

### Commits
1. `refactor: snapshot de undo vira dataclass com nome do passo`
2. `feat: alternar ultimo estado com Ctrl+Alt+Z`
3. `feat: historico nomeado no botao Desfazer, com salto direto para um passo`

---

## Item 2 — Tamanho estimado no export

### Objetivo
Mostrar quanto cada custom vai pesar **antes** de salvar/enviar, e avisar quando passar de
um limite. GIF animado (Rainbow, Neon, Glitch…) com 20–40 quadros é o caso crítico.

1. Na **Revisão em grade**, cada card mostra o tamanho (`PNG · 148 KB`,
   `GIF · 2,3 MB`); cards acima do limite ganham um selo de aviso.
2. Depois de exportar (Salvar Todas / ZIP / ImgChest), o resumo mostra o total e a maior
   custom (tamanho real dos arquivos gerados — custo zero).
3. Antes de um upload para o ImgChest, se alguma custom passar do limite, perguntar:
   "3 customs passam de X MB. Enviar mesmo assim?" com **Revisar** / **Enviar** /
   **Cancelar**.

### Pergunta em aberto (resolver antes de codar o aviso)
- **Qual é o limite real?** Não está confirmado no código nem na documentação a que tivemos
  acesso: limite por arquivo do ImgChest e o que o Mudae aceita exibir. O plano usa a chave
  de config `export_size_warn_mb` (padrão **8**, provisório), editável em Configurações. Se
  o limite real for conhecido, só muda o padrão.

### Estado atual (onde mexer)
- Codificação: `_process_cropped` / `_save_frames` em
  [batch_worker.py](src/core/batch_worker.py). Hoje só sabem gravar num **caminho**
  (`_save_frames` decide GIF pelo sufixo `.gif`).
- Revisão: [review_dialog.py](src/qt/dialogs/review_dialog.py) renderiza só a versão
  estática (`render_custom_preview`) na `task_runner`, a partir de `batch.frozen()`.
- Resultados do export: `save_all_images` / `save_zip` / `upload_to_imgchest` em
  [batch_controller.py](src/controllers/batch_controller.py) já devolvem `results` com
  `saved_to`.
- Config: [app_config.py](src/core/app_config.py) (`DEFAULT_CONFIG` + validação);
  Configurações em [settings_dialog.py](src/qt/dialogs/settings_dialog.py).

### Passo a passo

**2.a — Codificar para memória (refatoração do worker)**
1. Em `batch_worker.py`, separar "codificar" de "gravar":
   ```python
   def encode_custom(task_data) -> tuple[bytes, str]:
       """Bytes exatos que o export gravaria e o formato ("png" | "gif")."""
   ```
   - `_save_frames(final_frames, target, duration, fmt)` passa a aceitar um `BytesIO` ou
     um caminho, com `fmt` explícito (não mais deduzido do sufixo). Os chamadores atuais
     passam `fmt` a partir da extensão — comportamento idêntico.
   - O caminho estático faz `final.save(buffer, format="PNG")`.
2. **Garantia de fidelidade:** `encode_custom(data)` tem que produzir **os mesmos bytes**
   que o arquivo gravado por `process_image_task(data com output_path)`. Escrever esse
   teste antes da refatoração (estático e um animado com semente fixa — o Glitch usa
   `random`, então fixar `random.seed` no teste ou excluí-lo da comparação byte a byte).
3. Função de pool: `measure_custom(task_data) -> {"path", "bytes": int, "format"}`, que
   chama `encode_custom` e descarta os bytes (não devolver os bytes ao processo
   principal — só o tamanho).

**2.b — Tamanho na Revisão**
1. Novo botão na Revisão: **"Calcular tamanhos"** (não automático: num lote animado de 40
   imagens, codificar 40 GIFs leva alguns segundos — o render estático atual continua
   instantâneo).
2. Rodar as medições no **pool de processos** do `BatchController` (o mesmo do export:
   `_get_executor`), via um método novo `measure_sizes(paths, on_progress, cancel_event)`
   que monta as tasks com `_get_task_data` exatamente como `save_all_images` (mesmo
   formato de saída: `.gif` se houver animação, senão `.png`).
3. Na UI: barra de progresso no rodapé da Revisão; cada card recebe a legenda
   `nome\nGIF · 2,3 MB` ao chegar o resultado. Acima do limite: texto com cor
   `tokens()["warning"]` e prefixo `⚠`. Rodapé: `Total 31,4 MB · maior 4,1 MB (nome.png)`.
4. Cache: guardar o resultado em `main_window._size_cache[chave]` com a mesma chave de
   conteúdo descrita na Fase 3, item 8 (se a Fase 3 ainda não existir, usar uma chave
   simples `(path, mtime, rel_pos, size, cor, anim, edit_version)` e migrar depois).
5. Fechar a Revisão cancela a medição (mesmo padrão do `closeEvent` atual:
   `_render_seq += 1` + `cancel`).

**2.c — Resumo pós-export e aviso no upload**
1. Em `save_all_images` / `save_zip`: somar `os.path.getsize(saved_to)` dos sucessos e
   devolver `{"total_bytes", "largest": (path, bytes)}` no resultado. No ZIP, usar
   `ZipInfo.file_size` das entradas.
2. A mensagem final do export em [export_mixin.py](src/qt/mixins/export_mixin.py) ganha
   `"· 31,4 MB no total"`.
3. Upload ImgChest: antes de enviar, se `export_size_warn_mb` > 0, medir (com cache) e
   mostrar o diálogo de aviso quando houver excesso. **Revisar** abre `open_review(paths)`
   já com os tamanhos calculados.
4. Formatação única: `format_bytes(n)` em `src/core/` (`"148 KB"`, `"2,3 MB"` — vírgula
   decimal, pt-BR), com teste.

**2.d (opcional, só se os GIFs estiverem grandes na prática) — Reduzir GIF**
- Opções que reduzem bastante sem mudar o visual da borda: paleta global única
  (`Image.quantize` uma vez e `ADAPTIVE` compartilhado), metade dos quadros com o dobro
  de `duration` (40 → 20 no Rainbow) e `optimize=True`. Decidir **depois** de ver os
  números reais do 2.b; não implementar no escuro.

### Casos de borda
- Imagem com edição de pixels (rotação/IA): `_get_task_data` grava o override num
  `source_dir` temporário — usar `tempfile.mkdtemp` e apagar no fim, como a Revisão já faz.
- Imagem sem enquadramento possível (`_get_task_data` → `None`): card sem tamanho, com o
  erro atual.
- Mudar animação/borda com a Revisão aberta: os tamanhos ficam velhos → ao clicar
  **Atualizar**, limpar as legendas de tamanho (o cache por conteúdo resolve o resto).
- `export_size_warn_mb = 0` desliga o aviso.

### Testes
- `tests/test_batch_worker.py`: `encode_custom` == bytes do arquivo gravado (estático e
  Rainbow).
- `tests/test_batch_controller.py`: `measure_sizes` devolve um tamanho por path, na ordem
  da lista, e respeita `cancel_event`.
- `tests/test_review.py`: "Calcular tamanhos" preenche as legendas; acima do limite
  aparece `⚠` (limite baixíssimo no teste, ex. 0,001 MB).
- `format_bytes`: 0, 999, 1024, 1536, 5 MB.
- Upload com excesso abre o aviso e **Cancelar** não chama o uploader (mock).

### Critérios de aceite
- [ ] Revisão mostra o tamanho exato (igual ao arquivo final) de cada custom.
- [ ] O resumo do export informa total e maior arquivo.
- [ ] O upload avisa antes de mandar customs acima do limite configurado.
- [ ] Nenhuma regressão de velocidade no export (medição só quando pedida).

### Commits
1. `refactor: codificacao das customs para memoria (encode_custom)`
2. `feat(Revisao): tamanho de cada custom e aviso acima do limite`
3. `feat: total exportado no resumo e aviso de tamanho antes do upload`

---

## Item 3 — Paleta de comandos (`Ctrl+K`)

### Objetivo
Uma caixa de busca (`Ctrl+K`) que lista **todas** as ações do app e executa a escolhida
com Enter. Digitar "zip", "rainbow", "inteligente todas", "borda vermelha", "preset
anime" resolve sem procurar em abas/menus. Inspirado no registro único de comandos do
PhotoCraft (UI, atalhos e automação chamam a mesma lista).

### Estado atual (onde mexer)
- Atalhos: `_register_shortcuts()` em [main_window.py](src/qt/main_window.py) (lista de
  tuplas `(sequência, handler)`); teclas que não podem roubar campos de texto ficam em
  `keyPressEvent` (Ctrl+Z, Ctrl+V, ←/→, B).
- Ações espalhadas: toolbar (`_build_toolbar`), aba Edição
  ([editor_tab.py](src/qt/tabs/editor_tab.py)), barra de opções (borda/animação),
  aba Online, presets (`preset_manager.list_presets()`).

### Passo a passo

**3.a — Registro de comandos**
1. Criar `src/qt/commands.py`:
   ```python
   @dataclass
   class Command:
       id: str                 # "export.zip"
       title: str              # "Exportar ZIP"
       handler: Callable[[], None]
       category: str = ""      # "Exportar", "Enquadramento", "Borda", "Animação", "Preset"…
       shortcut: str = ""      # só exibição, ex. "Ctrl+S"
       keywords: tuple = ()    # sinônimos: ("salvar", "compactar")
       enabled: Callable[[], bool] = lambda: True

   class CommandRegistry:
       def register(self, command): ...
       def add_provider(self, fn: Callable[[], list[Command]]): ...   # comandos dinâmicos
       def all(self) -> list[Command]: ...                               # estáticos + providers
       def search(self, query, recent_ids=()) -> list[Command]: ...
   ```
2. **Busca** (função pura, testável sem Qt):
   - normalizar acentos e caixa (`unicodedata.normalize("NFKD")` + remover marcas): "animacao"
     acha "Animação";
   - casar contra `title`, `category`, `keywords`;
   - pontuação: prefixo do título > início de palavra > subsequência (fuzzy: "rbw" →
     "Rainbow"); desempate pela ordem de uso recente;
   - consulta vazia: recentes primeiro (até 8), depois todos por categoria.
3. Comandos **estáticos** (registrados em `main_window._register_commands()`):
   abrir pasta, colar, desfazer, refazer, alternar último estado, auto fit, ajuste
   inteligente, auto fit/inteligente em todas, copiar enquadramento para todas, zoom 100%,
   rotacionar, pick color, cor automática (atual/todas), salvar todas, salvar atual, ZIP,
   ImgChest, revisar, calcular tamanhos (item 2), configurações, ir para aba
   Edição/Online/IA, focar busca do Danbooru, limpar sessão.
4. Comandos **dinâmicos** (providers, recalculados a cada abertura):
   - `Borda: <nome>` para cada item de `BORDA_HEX` + "Cor personalizada…";
   - `Animação: <tipo>` (respeitando o aviso de fotossensibilidade do Strobe — chamar o
     mesmo caminho do combo, não setar o estado direto);
   - `Preset: <nome>` (aplica via `apply_preset`);
   - `Enquadramento padrão: Auto fit / Inteligente`.
5. **Unificar atalhos:** `_register_shortcuts` passa a ser derivado do registro (comandos
   com `shortcut` registrável viram `QAction`), assim o atalho exibido na paleta nunca
   diverge do real. As teclas tratadas em `keyPressEvent` ficam como estão, só com
   `shortcut` de exibição.

**3.b — Diálogo da paleta**
1. `src/qt/dialogs/command_palette.py`: `QDialog` sem moldura
   (`Qt.Popup | Qt.FramelessWindowHint`), largura ~520 px, centralizado no topo da
   janela principal (como o VS Code).
2. Conteúdo: `QLineEdit` (placeholder "Digite um comando…") + `QListWidget` com até ~12
   linhas visíveis. Cada linha: título à esquerda, categoria em cinza e atalho à direita
   (delegate simples ou dois `QLabel` num widget de item).
3. Teclado: ↑/↓ movem a seleção **sem tirar o foco do campo** (tratar no `keyPressEvent`
   do campo/filtro de eventos); Enter executa; Esc fecha; `PgUp/PgDn` pulam.
   Mouse: clique executa.
4. Executar = fechar o diálogo **primeiro** e chamar o handler via
   `QTimer.singleShot(0, handler)` (handlers que abrem diálogos modais não podem rodar
   com a paleta ainda aberta).
5. Comando desabilitado (`enabled()` falso, ex. "Salvar todas" sem imagens): aparece em
   cinza com o motivo na dica; Enter mostra o motivo na status bar em vez de executar.
6. Estilo: tokens do tema ([theme.py](src/qt/theme.py)), `#CommandPalette` no QSS;
   funcionar nos temas claro e escuro.

**3.c — Atalho, recentes e descoberta**
1. `Ctrl+K` (QAction na janela). Também `Ctrl+Shift+P` para quem vem do VS Code.
   Observação: em campos de texto, o Qt pode consumir `Ctrl+K` ("apagar até o fim da
   linha") em algumas plataformas; no Windows não há esse binding, mas se acontecer,
   `Ctrl+Shift+P` continua funcionando.
2. Recentes: `app_config["command_palette_recent"]` (lista de ids, máx. 8, validada em
   `app_config.py`).
3. Descoberta: dica na status bar ao abrir o app pela primeira vez após a atualização
   ("Novo: Ctrl+K abre a paleta de comandos") com a flag `command_palette_hint_shown`.

### Casos de borda
- Comando de aba que não existe no momento (ex. aba IA sem provedor): `enabled` falso.
- Preset apagado entre abrir a paleta e executar: o handler confere e mostra status.
- Paleta aberta durante export: comandos que exportam ficam desabilitados
  (`_running_user_operations()` já existe na janela).

### Testes
- `tests/test_commands.py` (sem Qt): busca com acento, fuzzy, prefixo antes de
  subsequência, recentes primeiro, providers dinâmicos incluídos.
- `tests/test_command_palette.py` (Qt): `Ctrl+K` abre; digitar "zip" + Enter chama o
  handler do ZIP (mock); Esc fecha sem executar; comando desabilitado não executa.
- Teste de consistência: todo `QAction` registrado pela janela tem um comando
  correspondente com o mesmo atalho (evita divergência futura).

### Critérios de aceite
- [ ] `Ctrl+K` abre a paleta em qualquer aba; Enter executa; Esc fecha.
- [ ] Busca tolera acento e erro de digitação leve ("rnbow" acha "Rainbow").
- [ ] Bordas, animações e presets aparecem como comandos.
- [ ] Os atalhos exibidos são exatamente os que funcionam.

### Commits
1. `feat: registro unico de comandos (atalhos derivados dele)`
2. `feat: paleta de comandos com Ctrl+K`
3. `feat(paleta): comandos recentes e dica de descoberta`

---

## Definição de pronto da Fase 1
- Suíte inteira verde no CI (pytest + build do exe + `--self-test`).
- Teste manual: lote de 10 imagens do Danbooru → ajustar 3 → `Ctrl+Alt+Z` / histórico →
  Revisão com tamanhos → upload com aviso → tudo pela paleta (`Ctrl+K`).
- [PLANO_FASE_1.md](PLANO_FASE_1.md) atualizado com o status de cada item, como foi feito
  no `PLANO_CORRECOES_MELHORIAS.md`.

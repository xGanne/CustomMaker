# Plano de Correções e Melhorias — CustomMaker v2

> Auditoria completa do código em 2026-07-18. Suíte de testes atual: **82 testes, todos passando**.
> Os problemas abaixo foram encontrados por leitura sistemática de todos os módulos de `src/`.
> Cada item tem arquivo/linha, descrição do problema e a correção proposta.

## ✅ Status de implementação (atualizado em 2026-10-13)

**Plano concluído: F1–F22 e M1–M22 implementados**, cada item em um commit próprio
(`fix(Fn)`, `feat(Mn)`, `perf(M15)`, `build(M22)`, `refactor(M14)`, `test(M18)`).
Suíte atual: **150 testes, todos passando** (com as dependências de `requirements.txt` instaladas).

Primeira rodada (2026-07-18): F1–F22, M1, M2, M3, M6, M12, M13, M17, M19, M20, M21.
Extras: redo com Ctrl+Y/Ctrl+Shift+Z (F15) e tecla **B** para o antes/depois (F17).

Segunda rodada (2026-10-13):
- **M4** indicador "Carregando…" no canvas (com atraso de 150 ms para não piscar)
- **M5** filete colorido por rating nos cards do Danbooru
- **M7** tema claro em Configurações › Aparência (vale ao reiniciar); cores dos widgets vêm do tema
- **M8** Ctrl+roda (passo de 20%), zoom ancorado no cursor, Ctrl+0 = 100% e indicador fixo de zoom
- **M9** multi-seleção, Delete/“Remover selecionadas”, badge de borda individual e “Revelar no Explorer”
- **M10** aviso único de fotossensibilidade; Strobe limitado a < 3 flashes/s (350 ms por quadro)
- **M11** enquadramento padrão (auto fit/inteligente) para imagens não ajustadas; presets podem
  incluir enquadramento e blacklist; amostra de cor no combo
- **M14** resolvido pela opção “honesta” do próprio item: a chave `ui_language` foi **removida**
  (o app só existe em pt-BR); i18n de verdade fica para quando houver demanda
- **M15** pool de processos reutilizado entre exportações (2º lote: ~0,9 s → ~0,06 s)
- **M16** botão Cancelar na busca, campo para pular para a página N, cache do autocomplete por prefixo
- **M18** testes de UI para F1/F2/F3/F5 com o `QTest` do PySide6 (sem adicionar pytest-qt)
- **M22** versões fixadas (PySide6==6.12.0); removidas dependências da UI legada

Correções encontradas durante a segunda rodada (fora do plano original):
- campo de tags da aba Online era apagado após cada busca
- detecção de rosto concorrente na mesma instância do cascade falhava em silêncio (agora com lock)
- OpenCL desativado na detecção: a primeira detecção da sessão levava ~2 s
- checkboxes desmarcados ficavam invisíveis (o tema não estilizava o indicador)

---

## Sumário de priorização

| # | Item | Severidade | Área |
|---|------|-----------|------|
| F1 | Thumbnails da lista criados fora da GUI thread (risco de crash) | 🔴 Crítica | Threading/Qt |
| F2 | Antes/Depois (tecla `) corrompe o enquadramento salvo + crash potencial | 🔴 Crítica | Canvas |
| F3 | Atalhos globais roubam Left/Right/Ctrl+V/Ctrl+Z dos campos de texto | 🔴 Alta | UX/Atalhos |
| F4 | Exportação/upload pula silenciosamente imagens sem enquadramento | 🔴 Alta | Exportação |
| F5 | Ordem dos links de upload/ZIP é aleatória (quebra o comando Mudae) | 🔴 Alta | Exportação |
| F6 | Token placeholder do `.env` é tratado como token válido | 🟠 Média | Upload |
| F7 | Erro de rede na busca Danbooru aparece como "0 resultados" | 🟠 Média | Online |
| F8 | Zoom com roda cria 1 snapshot de undo por tick (memória + undo inútil) | 🟠 Média | Canvas/Undo |
| F9 | Ajuste em lote acessa estado compartilhado sem lock (race condition) | 🟠 Média | Threading |
| F10 | Rotação usa a versão preview (resolução reduzida) como fonte de export | 🟠 Média | Qualidade |
| F11 | Colar imagem: caminho temp hardcoded + colisão de nomes | 🟠 Média | Editor |
| F12 | Configurações só têm efeito após reiniciar, sem aviso; blacklist duplicada | 🟠 Média | Settings |
| F13 | Export animado encolhe/distorce o conteúdo; estático não | 🟠 Média | Animação |
| F14 | Escrita de config/presets não é atômica | 🟡 Menor | Persistência |
| F15 | Undo sem redo; imagem "des-editada" continua marcada como editada | 🟡 Menor | Undo |
| F16 | Overlay de animação 1px mais fino à direita/embaixo (off-by-one) | 🟡 Menor | Animação |
| F17 | Tecla ` (crase) é dead key em teclado ABNT — atalho não funciona no BR | 🟡 Menor | UX |
| F18 | Modelo Gemini 1.5 descontinuado; slider "Intensidade" sem efeito | 🟡 Menor | IA |
| F19 | Arquivos de estado (.cache, config, presets, logs) relativos ao cwd | 🟡 Menor | Infra |
| F20 | Limpeza do filtro de `uploaded_links` usa heurística sem sentido | 🟡 Menor | Estado |
| F21 | Viewers do Danbooru anteriores não são fechados ao fechar o app | 🟡 Menor | Recursos |

---

## 1. Falhas críticas

### F1 — `QPixmap`/`setIcon` fora da GUI thread na lista de imagens
**Arquivo:** [image_list_panel.py:109-133](src/qt/widgets/image_list_panel.py#L109-L133)

`_load_thumb_async` usa `future.add_done_callback(on_done)`, e esse callback executa **na thread do executor**, não na GUI thread. Lá dentro acontecem duas violações do Qt:

1. `_generate_thumb` cria um `QPixmap` em thread de worker — `QPixmap` só pode existir na GUI thread (o Qt documenta isso explicitamente; pode corromper estado gráfico ou crashar).
2. `item.setIcon(QIcon(pixmap))` altera um item de widget a partir da worker thread. O próprio comentário no código admite: *"must set icon from main thread via a queued call"* — mas a chamada **não** é enfileirada.

Além disso, se a lista for limpa (`set_paths`) enquanto um future está pendente, `item` já foi deletado no lado C++ → `RuntimeError`/crash. O check de `generation` reduz mas não elimina a janela de corrida.

**Correção:** replicar o padrão já correto de [danbooru_grid.py:229-264](src/qt/widgets/danbooru_grid.py#L229-L264): o worker retorna a **imagem PIL** (ou bytes), emite um `Signal(int, object, object)` e a conversão para `QPixmap` + `setIcon` acontece no slot conectado (GUI thread). Validar o item por índice/geração dentro do slot antes de usar.

---

### F2 — Antes/Depois (tecla `) corrompe o estado salvo do enquadramento
**Arquivo:** [image_canvas.py:194-223](src/qt/widgets/image_canvas.py#L194-L223)

Três defeitos encadeados:

1. **Corrupção de estado:** `show_original_preview` move o `image_item` para a posição da borda. Isso dispara `itemChange → _emit_state_changed → state_changed → on_canvas_state_changed`, que **grava a posição temporária em `editor_state.image_states`**. Só de apertar a crase, o enquadramento cuidadosamente ajustado da imagem é sobrescrito.
2. **Posição não restaurada:** em `restore_edit_preview`, a expressão
   ```python
   self.image_item.setPos(*self._current_size and (
       int(self.image_item.pos().x()), int(self.image_item.pos().y())
   ))
   ```
   avalia para *a posição atual do item* — que é a posição do modo "antes", não a posição editada. O item nunca volta ao lugar original.
3. **Crash potencial:** se `_current_size` for `None`, a expressão vira `setPos(*None)` → `TypeError`.

**Correção:** em `show_original_preview`, salvar `(pos, size)` em atributos próprios (`_saved_pos/_saved_size`) e **bloquear a emissão de `state_changed`** durante o modo antes/depois (flag `_before_after_active` já existe — basta checá-la em `_emit_state_changed`). Em `restore_edit_preview`, restaurar explicitamente `setPos(*self._saved_pos)` e `_apply_size_transform(self._saved_size)`.

---

### F3 — Atalhos de janela interceptam teclas dos campos de texto
**Arquivo:** [main_window.py:354-371](src/qt/main_window.py#L354-L371)

`Left`, `Right`, `Ctrl+V` e `Ctrl+Z` são registrados como `QAction` na janela com contexto padrão (`WindowShortcut`). Atalhos têm precedência sobre o widget focado, então **com o cursor em qualquer campo de texto** (busca Danbooru, hex da cor, nome do preset):

- ← / → navegam entre imagens em vez de mover o cursor;
- Ctrl+V cola *imagem da área de transferência na lista* em vez de colar texto no campo;
- Ctrl+Z desfaz a *imagem* em vez da digitação.

**Correção:** nos handlers desses quatro atalhos, verificar `QApplication.focusWidget()` — se for `QLineEdit`/`QTextEdit`/`QPlainTextEdit` (ou tiver edição de texto), reenviar o evento ao widget (ou simplesmente não tratar). Alternativa mais limpa: instalar os atalhos apenas no canvas/lista (`Qt.WidgetWithChildrenShortcut`) em vez da janela inteira.

---

### F4 — Exportação pula silenciosamente imagens sem enquadramento
**Arquivo:** [batch_controller.py:52-55](src/controllers/batch_controller.py#L52-L55) e chamadores (`save_all_images`, `save_zip`, `upload_to_imgchest`)

`_get_task_data` retorna `None` quando `image_states` não contém o path, e o chamador só faz `if data: tasks.append(data)`. Como o estado de enquadramento só é criado quando a imagem é **aberta no canvas** ou ajustada em lote, o fluxo "carregar pasta → salvar direto" exporta apenas as imagens visualizadas — as demais somem **sem nenhum aviso**. O diálogo mostra "Processadas: N" sem dizer que N < total da lista.

**Correção:**
1. Em `_get_task_data`, quando não houver estado, calcular um estado padrão com `ImageProcessor.calculate_auto_fit_pos` (mesmo fallback que `_ensure_state_for_current` usa no editor) em vez de retornar `None`.
2. No resumo pós-operação (`ExportMixin._show_result_summary`), comparar `len(tasks)` com `len(image_list)` e listar os nomes pulados quando houver diferença.

---

### F5 — Ordem dos resultados do lote é a ordem de conclusão, não a da lista
**Arquivo:** [batch_controller.py:148-189](src/controllers/batch_controller.py#L148-L189)

`_run_batch` coleta `future.result()` conforme os processos terminam (`concurrent.futures.wait`), então `batch["results"]` sai em **ordem aleatória**. Consequências:

- `upload_to_imgchest` monta `files` nessa ordem → os links do álbum ImgChest e o **comando Mudae copiado ficam fora de ordem** em relação à lista de imagens (para customs, a ordem importa).
- O ZIP também grava em ordem aleatória (menos grave).
- O download em lote do Danbooru ([online_tab.py:487](src/qt/tabs/online_tab.py#L487), `as_completed`) importa as imagens fora da ordem selecionada.

**Correção:** após o batch, reordenar `results` pela ordem de `tasks` (mapa `path → índice`) antes de montar `files`/ZIP. No download do Danbooru, ordenar `downloaded_paths` pela ordem de `selected_posts` antes de `add_images`.

---

## 2. Falhas médias

### F6 — Placeholder do `.env` aceito como token real
**Arquivos:** [app.py:24-30](src/qt/app.py#L24-L30), [settings.py:100](src/config/settings.py#L100), [uploader.py:59-60](src/core/uploader.py#L59-L60)

Na primeira execução o app cria `.env` com `IMG_CHEST_API_TOKEN=seu_token_aqui`. O uploader só checa `if not self.api_token` — a string placeholder é truthy, então o upload prossegue e falha com um HTTP 401 confuso em vez da mensagem clara "token não configurado".

**Correção:** tratar `"seu_token_aqui"` (e string vazia/whitespace) como ausência de token no `ImgChestUploader`; na UI, ao clicar em upload sem token válido, mostrar diálogo orientando a editar o `.env` (com botão para abrir o arquivo).

### F7 — Falha de rede na busca vira "0 resultados"
**Arquivo:** [danbooru.py:131-136](src/core/danbooru.py#L131-L136)

`search_posts` **lança** exceção para erros HTTP (bom — a UI mostra o aviso) mas **retorna `[]`** para `RequestException` (sem internet, timeout, DNS) e JSON inválido. O usuário vê "Sem resultados · pág. 1" quando na verdade a rede caiu.

**Correção:** propagar também esses erros como `RuntimeError("Danbooru: falha de conexão — verifique sua internet.")`; a UI da OnlineTab já tem o caminho `on_error` pronto para exibir.

### F8 — Um snapshot de undo por tick da roda do mouse
**Arquivo:** [image_canvas.py:227-242](src/qt/widgets/image_canvas.py#L227-L242)

`wheelEvent` emite `interaction_started` a cada tick, e cada emissão gera um snapshot de undo com **cópia integral da imagem** ([image_loader_mixin.py:349-365](src/qt/mixins/image_loader_mixin.py#L349-L365)). Um único gesto de scroll enche a pilha (limite 20) com estados quase idênticos: memória desperdiçada e Ctrl+Z que "não faz nada" perceptível.

**Correção:** debounce — só emitir `interaction_started` se o último tick ocorreu há mais de ~500 ms (guardar timestamp), tratando a sequência de ticks como um único gesto. Bônus: como pos/size ficam em `image_states` e a imagem não muda no zoom, o snapshot de zoom/movimento poderia guardar só `(pos, size)` sem copiar a imagem (economia grande de memória).

### F9 — Ajuste em lote lê/escreve estado compartilhado de uma worker thread
**Arquivo:** [adjustments_mixin.py:86-129](src/qt/mixins/adjustments_mixin.py#L86-L129)

`task_fn` roda no `QThreadPool` mas acessa diretamente `self.edited_images`, `self._preview_cache` (via `_get_preview_cache_copy`, que **muta** o `OrderedDict` no touch LRU) e escreve em `editor_state.image_states` — tudo compartilhado com a GUI thread. Trocar de imagem ou fechar o app durante o lote pode corromper o cache ou lançar `RuntimeError: OrderedDict mutated during iteration`.

**Correção:** antes de submeter a task, tirar um **snapshot imutável** na GUI thread (lista de paths + dict path→imagem já copiada ou path do arquivo); a task calcula os fits e devolve `{path: (pos, size)}`; o `on_done` (GUI thread) aplica em `editor_state`. Nenhum estado compartilhado é tocado pela worker.

### F10 — Rotação (e IA) usam a preview reduzida como fonte definitiva
**Arquivos:** [adjustments_mixin.py:56-65](src/qt/mixins/adjustments_mixin.py#L56-L65), [image_loader_mixin.py:219-233](src/qt/mixins/image_loader_mixin.py#L219-L233)

`get_active_image_copy` prioriza `edited_images`/cache de preview — imagens limitadas a ~2400px (ou menos). Ao rotacionar, essa versão reduzida vira a "fonte" em `edited_images`, e o export ([batch_controller.py:72-75](src/controllers/batch_controller.py#L72-L75)) passa a usá-la no lugar do arquivo original. Para a saída 225×350 o impacto visual é pequeno, mas é perda de qualidade encadeada e permanente (cada rotação re-encoda a preview).

**Correção:** rotação é uma transformação sem perdas que pode ser registrada como **metadado** (`rotation: 90/180/270` em `editor_state`), aplicada pelo canvas via transform e pelo `batch_worker` sobre o arquivo original no momento do export. `edited_images` ficaria reservado para edições de pixel reais (IA).

### F11 — `paste_image`: temp dir hardcoded e colisão de nomes
**Arquivo:** [main_window.py:579-594](src/qt/main_window.py#L579-L594)

- Caminho montado na mão: `~/AppData/Local/Temp/CustomMakerPaste` — quebra fora do Windows e ignora `%TEMP%` customizado. Usar `tempfile.gettempdir()`.
- Nome `pasted_{seq+len+1}.png` pode **repetir entre sessões** e sobrescrever um arquivo que ainda está na lista — como o path já existe em `image_list`, o `add_images` não recarrega e o preview em cache continua mostrando a imagem antiga (stale).

**Correção:** `filename = f"pasted_{time.strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}.png"`.

### F12 — Configurações exigem reinício sem avisar; blacklist com duas UIs dessincronizadas
**Arquivo:** [settings_dialog.py](src/qt/dialogs/settings_dialog.py), [online_tab.py:93-97](src/qt/tabs/online_tab.py#L93-L97)

- Timeouts do Danbooru, tamanhos de cache e `max_workers` são lidos na **construção** de `DanbooruClient`/grids/janela; salvar no diálogo não altera nada em runtime e nenhuma mensagem avisa que é preciso reiniciar.
- A blacklist existe no diálogo de configurações **e** na aba Online; salvar em um lugar não atualiza o outro (o campo da aba Online só carrega no construtor).
- `_spin_field` cria `QLineEdit` (apesar do nome) sem validação visual; texto inválido silenciosamente vira o default no save.
- Abrir e salvar o diálogo com `max_workers = None` (modo automático) força o valor 4 — o modo "auto" é perdido sem o usuário pedir.

**Correção:** usar `QSpinBox` de verdade; ao salvar, mostrar "algumas alterações têm efeito após reiniciar" (ou aplicar a quente onde possível — timeouts do client são triviais de reaplicar); remover a blacklist do diálogo (deixar só na aba Online) ou fazer o diálogo emitir um sinal que a aba escuta; adicionar checkbox "automático" para workers.

### F13 — Export animado distorce e desloca o conteúdo; estático não
**Arquivos:** [animation_processor.py](src/core/animation_processor.py) (todos os geradores), [batch_worker.py:37-44](src/core/batch_worker.py#L37-L44)

No caminho estático, `add_borda_to_image` desenha a borda **por cima** do conteúdo 225×350. No caminho animado, o conteúdo é `resize((inner_w, inner_h))` = 215×340 — um resize **não proporcional** (distorce levemente) e o resultado visual difere do estático e da prévia do editor (que também desenha a borda por cima).

**Correção:** nos geradores, colar o frame de cor como *overlay* (mesma técnica do `overlay_only` + alpha) sobre o conteúdo em tamanho original, em vez de redimensionar o conteúdo para dentro da borda. Isso unifica estático, animado e preview.

---

## 3. Falhas menores

### F14 — Persistência não atômica
**Arquivos:** [app_config.py:230-235](src/core/app_config.py#L230-L235), [preset_manager.py:28-33](src/core/preset_manager.py#L28-L33)
Crash/queda de energia durante `json.dump` deixa o arquivo truncado (o load até se recupera, mas zera tudo). **Correção:** escrever em `arquivo.tmp` + `os.replace()`.

### F15 — Undo sem redo; indicador "editada" nunca volta
**Arquivo:** [image_loader_mixin.py:367-388](src/qt/mixins/image_loader_mixin.py#L367-L388)
Não há redo (Ctrl+Y/Ctrl+Shift+Z). E ao desfazer até o estado original, o path permanece em `edited_images` — o indicador verde "pixels editados" da lista fica para sempre. **Correção:** pilha de redo simétrica; ao desfazer o último snapshot, remover de `edited_images` se a imagem voltou ao original.

### F16 — Off-by-one no overlay de animação
**Arquivo:** [animation_processor.py:10-16](src/core/animation_processor.py#L10-L16)
`draw.rectangle` do PIL inclui a coordenada final, então o miolo transparente invade 1px da borda direita/inferior — a prévia fica com borda assimétrica (ex.: 5px em cima, 4px embaixo). **Correção:** `(border_width, border_width, w - border_width - 1, h - border_width - 1)`.

### F17 — Atalho antes/depois inacessível em teclado ABNT
**Arquivo:** [main_window.py:598-610](src/qt/main_window.py#L598-L610)
A crase (`Qt.Key_QuoteLeft`) é *dead key* no layout ABNT2 — justamente o layout do público-alvo (app em pt-BR). **Correção:** aceitar também uma tecla alternativa (ex.: `B` ou `Espaço` mantido pressionado) e documentar no tooltip.

### F18 — Modelo Gemini defasado e slider sem efeito
**Arquivo:** [ai_pipeline.py:17](src/core/ai_pipeline.py#L17), [ai_tab.py:49-65](src/qt/tabs/ai_tab.py#L49-L65)
`models/gemini-1.5-flash` foi descontinuado pelo Google (migração para 2.x) — as chamadas tendem a falhar com 404. O slider "Intensidade" envia `strength` que o provider text-only ignora — UI que promete o que não faz. **Correção:** atualizar o modelo (ex.: `gemini-2.0-flash` ou tornar configurável no diálogo de configurações) e ocultar o slider enquanto `capabilities.image_edit == False`. A cópia da imagem passada à task nunca é fechada (`image.close()` após o `apply_uniform`).

### F19 — Estado espalhado no diretório de trabalho
**Arquivos:** [settings.py:103](src/config/settings.py#L103), [preset_manager.py:9](src/core/preset_manager.py#L9), [cache_manager.py:12](src/core/cache_manager.py#L12), [logging_config.py:6](src/core/logging_config.py#L6)
`custommaker_config.json`, `presets.json`, `.cache/` e `logs/` são criados no **cwd**. Rodando o `.exe` empacotado a partir de outro diretório (atalho, linha de comando), o app "perde" configurações e presets e espalha pastas de cache. **Correção:** centralizar em `%LOCALAPPDATA%/CustomMaker/` (com fallback para o diretório do projeto em modo dev), migrando os arquivos existentes na primeira execução.

### F20 — Filtro de `uploaded_links` sem sentido
**Arquivo:** [editor_state.py:61](src/core/editor_state.py#L61)
`[link for link in self.uploaded_links if path not in link]` — URLs do ImgChest nunca contêm o path local; o filtro nunca remove nada (e se removesse, seria por coincidência de substring). **Correção:** remover a linha ou mapear `path → link` explicitamente.

### F21 — Viewers e galerias anteriores ficam órfãos
**Arquivo:** [online_tab.py:559-563](src/qt/tabs/online_tab.py#L559-L563)
`open_image_viewer` guarda só a última referência; ao fechar o app, `close()` fecha apenas o último viewer — os demais continuam com `QtTaskRunner` e `CacheManager` próprios ativos. **Correção:** manter uma lista de viewers abertos (removendo em `destroyed`) e fechar todos.

### F22 — Heurística de "próxima página" falha na última página exata
**Arquivo:** [online_tab.py:377](src/qt/tabs/online_tab.py#L377)
`_has_next_page = len(posts) >= page_size` — quando a última página tem exatamente 20 itens, "→" leva a uma página vazia. Menor, mas a página vazia poderia voltar automaticamente com um aviso.

---

## 4. Melhorias de UX / Layout / Design

### M1 — Substituir modais informativos por toasts/status bar
"Pick Color" abre um `QMessageBox` modal só para dizer que a cor foi copiada ([main_window.py:497](src/qt/main_window.py#L497)); "Ajuste aplicado em N imagens" idem. Interrompem o fluxo. O projeto já tem [toast.py](src/ui/toast.py) na UI legada — portar para Qt e usar em confirmações não críticas, reservando modais para erros e decisões.

### M2 — Confirmação ao sair com trabalho não exportado
`closeEvent` fecha sem perguntar mesmo com `image_dirty` não vazio. Adicionar "Você tem N imagens ajustadas e não exportadas. Sair mesmo assim?" (com opção "não perguntar novamente").

### M3 — Estado vazio do canvas com orientação
Canvas inicial é um retângulo escuro mudo. Mostrar mensagem central: "Arraste uma pasta ou imagens aqui · Ctrl+O para abrir · Ctrl+V para colar" — reduz a curva de entrada.

### M4 — Feedback de progresso ao trocar de imagem rapidamente
Navegar com ←/→ em imagens grandes mostra brevemente a imagem anterior/cache. Um spinner discreto ou blur do placeholder no canvas enquanto `qt_image_load_*` está ativo comunicaria melhor.

### M5 — Indicador de rating por cor nos cards do Danbooru
Nos cards da grade, o rating aparece como letra (`g/s/q/e`). Um filete colorido (verde/amarelo/laranja/vermelho) na borda do card torna a triagem visual imediata.

### M6 — Consistência de idioma e acentuação
Strings misturam pt sem acento ("Ultima alteracao desfeita", "Busca concluida", "Paginacao"), pt correto e inglês ("Pick Color", "Auto Fit"). Padronizar pt-BR acentuado (há `ui_language` no config — hoje decorativo; ver M14).

### M7 — Tema claro
`ui_theme_variant` só aceita `editorial_dark_v1` ([app_config.py:114-115](src/core/app_config.py#L114-L115)). Os tokens em `UI_TOKENS` já centralizam as cores — criar variante clara é principalmente definir um segundo dicionário e regenerar o stylesheet.

### M8 — Zoom melhor no canvas
- Passo fixo de 5% é lento para grandes mudanças: aceitar `Ctrl+roda` com passo de 15–20%.
- Botões/atalhos "Ajustar à borda" (refazer auto fit visual) e "100%".
- O indicador de zoom hoje é uma mensagem de status efêmera; mover para um label permanente no canto do canvas.

### M9 — Lista de imagens mais operável
- Multi-seleção com Shift/Ctrl + "Remover selecionadas" e tecla Delete.
- Badge de cor da borda individual no item (hoje o toggle de borda individual é invisível na lista).
- Menu de contexto com "Revelar no Explorer".

### M10 — Aviso de fotossensibilidade no Strobe
"Strobe (Pisca)" alterna cores saturadas a 10 fps — risco real para usuários fotossensíveis. Exibir aviso único na primeira seleção e considerar reduzir a frequência padrão.

---

## 5. Melhorias de funcionalidade

### M11 — Presets mais completos
Hoje o preset salva borda/cor/animação. Incluir opcionalmente: blacklist do Danbooru e enquadramento padrão (auto fit vs inteligente). Mostrar swatch da cor no combo de presets.

### M12 — Exportar imagem única
Só existe exportação em lote. Botão/atalho "Exportar imagem atual" (Ctrl+Shift+S) para o fluxo de ajuste fino de uma imagem só.

### M13 — Cache de frames de animação da prévia
`start_preview_animation` regenera todos os frames a cada troca de imagem/cor, mas os frames dependem apenas de `(animation_type, border_color)`. Um dicionário `{(tipo, cor): (pixmaps, duration)}` com limite pequeno elimina o trabalho repetido e o flicker ao navegar.

### M14 — Ativar de fato `ui_language`
A chave existe no config mas não há infraestrutura de tradução. Ou remover a chave (honestidade), ou introduzir um dicionário de strings simples (pt-BR/en) — o app tem ~150 strings de UI, viável num arquivo único.

### M15 — Reusar o pool de processos do batch
`_run_batch` cria um `ProcessPoolExecutor` novo por operação — no Windows (spawn), isso adiciona segundos de aquecimento a cada export. Manter um pool preguiçoso e reutilizável no `BatchController` (com shutdown no `closeEvent`).

### M16 — Busca Danbooru: cancelamento e refinamentos
- Botão "Cancelar" durante a busca (a task suporta `cancel_event`, falta o botão — hoje só trocando de busca).
- Pular para página N (campo editável no `page_label`).
- Autocomplete: cachear sugestões por prefixo na sessão (evita repetir chamadas de rede ao apagar/redigitar).

### M17 — Detecção de rosto: fallback informativo
Quando `lbpcascade_animeface.xml` não está presente, `face_cascade = None` e o "Ajuste Inteligente" silenciosamente vira auto fit. Avisar uma vez na inicialização ("detecção de rosto indisponível — arquivo X não encontrado") e desabilitar/marcar o botão.

---

## 6. Melhorias técnicas / qualidade de código

### M18 — Testes para os fluxos de UI críticos
A suíte cobre bem o núcleo (82 testes), mas os bugs F1–F3 vivem em código sem teste (canvas, atalhos, thumbnails). Adicionar testes com `pytest-qt` para: antes/depois preserva estado; atalhos não roubam foco de QLineEdit; ordem estável dos resultados de batch (F5 é testável sem UI).

### M19 — Extrair helper comum de conversão PIL→QPixmap
`_pil_to_qpixmap` está duplicada em [image_canvas.py:24](src/qt/widgets/image_canvas.py#L24), [danbooru_image_viewer.py:33](src/qt/dialogs/danbooru_image_viewer.py#L33) e inline em [danbooru_grid.py:250-259](src/qt/widgets/danbooru_grid.py#L250-L259) e [image_list_panel.py:124-133](src/qt/widgets/image_list_panel.py#L124-L133). Mover para `src/qt/pixmap_utils.py`.

### M20 — Remover código morto
- `generate_marching_ants_frames` retorna `[]` e não é usado ([animation_processor.py:86-87](src/core/animation_processor.py#L86-L87)).
- `_update_recent_folders_menu` é um `pass` ([main_window.py:568-569](src/qt/main_window.py#L568-L569)).
- `BORDA_NAMES` e `CSS_FILE`/`bordas.css` parecem herança da UI legada — verificar e remover de `settings.py`.
- Imports não usados: `BytesIO` em image_list_panel, `QMenu` duplicado em main_window.
- Diretórios `src/ui/` (CustomTkinter) e `legacy/` duplicam conceitos — se `main_legacy.py` ainda é suportado, isolar; senão, arquivar.

### M21 — Logging de exceções no task runner
`_TaskRunnable.run` captura `Exception` e emite `error`, mas se nenhum slot estiver conectado o erro **desaparece** (caso do `start_preview_animation` quando `submit` retorna handle e o caller esquece o connect). Logar `logger.exception` dentro do `except` garante rastro no `logs/app.log`.

### M22 — `requirements.txt` com versões pinadas
Garantir pins (PySide6, Pillow, opencv, google-generativeai) para builds reprodutíveis do PyInstaller — especialmente após F18 (migração de modelo Gemini muda a versão mínima do SDK).

---

## 7. Plano de execução sugerido

**Fase 1 — Estabilidade (F1–F5)** · ~1 sessão
Corrigir os dois riscos de crash/corrupção (F1, F2), os atalhos (F3) e os dois bugs de exportação (F4, F5). São os itens com impacto direto no resultado que o usuário entrega (customs com imagens faltando/fora de ordem).

**Fase 2 — Robustez (F6–F13)** · 1–2 sessões
Token/erros de rede com mensagens honestas, undo saudável, thread-safety do lote, qualidade da rotação, consistência estático×animado.

**Fase 3 — Polimento (F14–F22 + M1–M10)** · contínuo
Persistência atômica, redo, toasts, estado vazio, tema claro, idioma consistente.

**Fase 4 — Funcionalidades novas (M11–M17)** · conforme demanda
Priorizar M13 (cache de frames — ganho perceptível imediato) e M12 (export único — pedido natural do fluxo).

**Transversal:** a cada fase, adicionar os testes correspondentes (M18) antes do refactor, e rodar `python -m pytest -q` + smoke test manual (`python main.py`) ao final.

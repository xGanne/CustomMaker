# Plano — Fase 3: cache de renderização, paridade prévia × export e modo linha de comando

> Origem: técnicas de engenharia do PhotoCraft (`storytold/photocraft`): cache de efeitos por
> estado, compositor de referência testado contra o de tela e um registro de comandos que
> roda sem interface. Escrito em 2026-10-28 sobre o commit `8790ed8`.
>
> Fases: [Fase 1](PLANO_FASE_1.md) → [Fase 2](PLANO_FASE_2.md) → **3 (este arquivo)**.

## ✅ Status (atualizado em 2026-10-31) — Fase 3 implementada

| Item | Situação |
|---|---|
| 9 — Paridade canvas × export | **Feito** `7261cb2`: geometria (±1 px pelos limites de quadrantes de cor), cor com tolerância, borda e transparência em auto fit, zoom 37/100/250%, área vazia, borda individual, janela redimensionada, paisagem/pequena/grande (JPEG com draft), rotação, estilos de borda, ajustes de tom e 1º quadro da animação; 9.d (Revisão == arquivo, pixel a pixel). **A suspeita 9.a se confirmou** e foi corrigida em `70d2d26`: a borda do canvas cobria só ~2,5 px por dentro — o canvas mostrava ~2 px a mais de imagem em cada lado do que o arquivo. |
| 8 — Cache de renderização | **Feito** `2492f43`, `f66525a`: chave por conteúdo (arquivo, posição relativa à borda, tamanho, cor, estilo, ajustes, versão da edição de pixels); LRU de 48 MB, limpo ao trocar de pasta/fechar; a Revisão mostra os cards conforme ficam prontos. 8.c (render em processos) não feito: com o cache não foi necessário. |
| 10 — Linha de comando | **Feito** `3c80faf` (extrações para o core), `c13ee65` (`--batch`), `f2bd939` (CI no exe + README). 10.f (`--danbooru`) não feito — opcional, fora da fase. |

Medições (máquina local, 50 imagens 800×1200 JPEG):
- Revisão: 1ª abertura **1,58 s**; reabertura **0,05 s** (50 do cache).
- `python main.py --batch ... --zip`: **3,1 s**. No exe, o CI valida o `--batch` a cada push
  (tempo do exe não medido localmente — gerar o exe aqui pesa na máquina).

## Visão geral

| # | Item | Ganho | Esforço | Commits previstos |
|---|------|-------|---------|-------------------|
| 8 | Cache de renderização por conteúdo | Revisão e tamanhos instantâneos ao reabrir | Médio | 2 |
| 9 | Teste de paridade canvas × export | Garantia automática de "o que vejo é o que sai" | Médio | 3 |
| 10 | Modo linha de comando (`--batch`) | Gerar customs de uma pasta sem abrir a janela | Médio/Alto | 4 |

**Pré-requisitos:** nenhum é obrigatório, mas o valor cresce com as fases anteriores:
- o item 8 serve à Revisão (já existe) e aos tamanhos da Fase 1 (item 2);
- o item 9 deve cobrir os estilos e ajustes da Fase 2 quando existirem;
- o item 10 reaproveita presets, estilos e ajustes.

**Ordem sugerida: 9 → 8 → 10.** O teste de paridade vem primeiro porque pode revelar
diferenças reais (ver a suspeita em 9.a) que mudariam o que o cache guarda.

---

## Item 8 — Cache de renderização por conteúdo

### Objetivo
Toda prévia de custom (Revisão em grade, tamanho estimado da Fase 1) passa a ser guardada
por uma **chave do conteúdo** que a gera. Reabrir a Revisão ou clicar **Atualizar** só
renderiza as customs que mudaram; as outras aparecem na hora.

### Estado atual
- [review_dialog.py](src/qt/dialogs/review_dialog.py) renderiza **todas** as customs a
  cada abertura e a cada "Atualizar" (`render()` → `render_custom_preview` em série numa
  task), mesmo que nada tenha mudado.
- Já há caches na janela, mas de outra natureza: `_preview_cache` (prévias da imagem
  inteira para o canvas) em
  [image_loader_mixin.py](src/qt/mixins/image_loader_mixin.py) e o `CacheManager` em disco
  das miniaturas/Danbooru ([cache_manager.py](src/core/cache_manager.py)).

### Passo a passo

**8.a — Chave de conteúdo**
1. Nova função pura `custom_cache_key(task_data, edit_version) -> str` em
   `src/core/render_cache.py`. Ela é um SHA-1 de um JSON canônico (`sort_keys=True`) com:
   | Campo | Por quê |
   |---|---|
   | caminho de origem + `st_mtime_ns` + `st_size` | o arquivo pode ser trocado no disco |
   | **posição relativa à borda** (`pos − borda_pos`) e `size` | redimensionar a janela desloca a borda e as posições absolutas sem mudar a custom; com posição absoluta o cache erraria sempre após um resize |
   | cor da borda resolvida | inclui borda individual |
   | estilo de borda e ajustes de cor (Fase 2), quando existirem | mudam o resultado |
   | `anim_type` **só para medição de tamanho** | a prévia estática ignora animação; incluir na chave da prévia causaria misses inúteis |
   | `edit_version` da imagem | edições de pixel (rotação, IA) mudam a fonte sem mudar o caminho |
   | `RENDER_VERSION` (constante) | subir quando o pipeline de render mudar, invalidando tudo |
2. `edit_version`: contador por caminho em `main_window._edit_versions[path]`,
   incrementado em `set_edited_image_for_current` e ao desfazer/refazer edições de pixel
   (`_apply_snapshot` quando muda `edited_images`). **Não** fazer hash dos pixels da imagem
   editada (custaria mais que renderizar).

**8.b — Cache em memória com limite**
1. `RenderCache` em `src/core/render_cache.py`: `OrderedDict` LRU com **limite em bytes**
   (padrão 48 MB; os cards da Revisão têm 150×233 RGBA ≈ 140 KB → ~350 cards), protegido
   por `threading.Lock` (lido e escrito pela task da Revisão).
   - `get(key) -> Image | None` devolve **cópia** (quem recebe fecha a imagem);
   - `put(key, image)` guarda uma cópia;
   - `get_size(key)` / `put_size(key, n)` para os tamanhos da Fase 1 (só inteiros).
2. Instância única na janela (`main_window.render_cache`), limpa em `_reset_workspace` e
   no fechamento (como o `_preview_cache`).
3. Na Revisão, dentro de `task_fn`: calcular a chave; hit → usar a cópia; miss →
   `render_custom_preview`, `thumbnail`, `put`. O `batch.frozen()` já garante que a chave
   e o render veem o mesmo estado.
4. **Exibição progressiva:** emitir progresso a cada card pronto (`on_progress`) e
   preencher a grade conforme chegam, em vez de esperar o lote inteiro. Os hits aparecem
   imediatamente.
5. Status: `"40 customs · 37 do cache, 3 renderizadas"` (útil para validar e depurar).

**8.c (opcional) — Render da Revisão no pool de processos**
- Hoje as prévias rodam em série numa thread. Com o cache cobrindo o caso comum, só
  paralelizar se a primeira abertura de lotes grandes (50+) continuar lenta. Medir antes:
  tempo da primeira Revisão com 50 imagens do Danbooru.

### Casos de borda
- Arquivo apagado entre abrir e renderizar: `os.stat` falha → sem chave → card de erro
  (como hoje).
- Duas imagens com o mesmo conteúdo e caminhos diferentes: chaves diferentes (o caminho
  está na chave). Correto, porque a lista as trata como customs separadas.
- Memória: o limite em bytes é respeitado mesmo com imagens de tamanhos diferentes
  (calcular `w × h × 4`).

### Testes (`tests/test_render_cache.py`)
- Mesma task → mesma chave; mudar cor, posição relativa, `size`, mtime ou `edit_version` →
  chave diferente; **deslocar a borda e a posição juntas → mesma chave**.
- LRU respeita o limite e descarta o mais antigo; `get` devolve cópia independente.
- Revisão: segunda abertura sem mudanças não chama `render_custom_preview` (patch com
  contador); mudar uma imagem re-renderiza só ela.

### Critérios de aceite
- [ ] Reabrir a Revisão sem mudanças é instantâneo.
- [ ] "Atualizar" renderiza só o que mudou.
- [ ] Redimensionar a janela não invalida o cache.
- [ ] Memória do cache limitada e liberada ao trocar de pasta.

### Commits
1. `perf: cache de renderizacao das customs por conteudo`
2. `perf(Revisao): usa o cache e mostra os cards conforme ficam prontos`

---

## Item 9 — Teste de paridade canvas × export

### Objetivo
Um conjunto de testes automáticos que prova que **o que o canvas mostra dentro da borda é
o que o export grava**, em vários cenários de enquadramento. Hoje isso depende de
verificação manual. Bugs desse tipo já aconteceram (o comentário de
`render_image_to_borda` cita "positional drift versus the editor preview"; o F13 corrigiu
outra divergência nas animações).

### Suspeita concreta a confirmar primeiro (9.a)
No canvas, a borda é um `QGraphicsRectItem` com `QPen` de 5 px
([image_canvas.py](src/qt/widgets/image_canvas.py), `_layout_border`). No Qt, a caneta é
**centrada na linha do retângulo**: 2,5 px ficam para fora e 2,5 px para dentro. No export,
`add_borda_to_image` desenha os 5 px **inteiros para dentro** de 225×350. Se isso se
confirmar, o canvas mostra ~2,5 px a mais de imagem em cada lado do que a custom final.
A diferença é pequena, mas é exatamente o tipo de coisa que este item existe para pegar.

**Correção, se confirmada:** desenhar a borda do canvas para dentro: retângulo ajustado
(`bx + 2.5, by + 2.5, W − 5, H − 5`) com a mesma caneta, ou caneta com
`setJoinStyle(Qt.MiterJoin)` sobre o retângulo recuado. O teste de paridade vira a
regressão.

### Estado atual
- Canvas: imagem como `QGraphicsPixmapItem` escalado por `QTransform`
  (`SmoothPixmapTransform`, reamostragem do Qt) a partir da **prévia** (até 2400 px).
- Export: `render_image_to_borda` redimensiona o **original** com `LANCZOS` e recorta.
- Logo, os pixels nunca serão idênticos (outro filtro, outra fonte). O teste precisa
  comparar **geometria** com exatidão e **cor** com tolerância.

### Passo a passo

**9.b — Infraestrutura do teste (`tests/test_preview_export_parity.py`)**
1. Janela real offscreen (padrão de [test_review.py](tests/test_review.py): config e
   presets em pasta temporária, `dispose_window` no cleanup).
2. **Imagens-padrão sintéticas** feitas no teste, desenhadas para facilitar a medição:
   - "alvo": fundo cinza com quadrantes de cores sólidas e uma grade de linhas de 1 px a
     cada 50 px (as bordas entre cores permitem medir deslocamento com precisão de 1 px);
   - tamanhos variados: retrato 800×1200, paisagem 1600×900, pequena 150×200 (menor que a
     borda), grande 4000×6000 (passa pelo `draft`/redução da prévia).
3. **Captura do canvas**: renderizar a cena só na área da borda, 1:1, sem fundo:
   ```python
   img = QImage(BORDA_WIDTH, BORDA_HEIGHT, QImage.Format_ARGB32_Premultiplied)
   img.fill(Qt.transparent)
   painter = QPainter(img)
   canvas.scene.render(painter, QRectF(0, 0, W, H), QRectF(bx, by, W, H))
   painter.end()
   ```
   Converter para PIL RGBA, sem multiplicação de alfa. Esconder antes o texto de dica
   vazia, a etiqueta de zoom e o carregamento (não fazem parte da cena ou ficam fora da
   área, mas garantir).
4. **Captura do export**: `batch = window.batch_controller.frozen()`;
   `data = batch._get_task_data(path, None, source_dir=tmp)`;
   `render_custom_preview(data)`. É o mesmo caminho do arquivo final (o teste 9.d prova
   isso).

**9.c — Métricas e cenários**
1. **Geometria (exata, ±1 px):** localizar nas duas imagens as transições entre os
   quadrantes e as linhas da grade (perfil de cor ao longo de uma linha/coluna) e comparar
   as posições. É isso que pega deslocamento e escala errados.
2. **Cor (tolerância):** diferença absoluta média por canal ≤ 3 e percentil 99 ≤ 40,
   **excluindo** uma faixa de 1 px em volta das transições (onde os filtros de
   reamostragem divergem legitimamente).
3. **Borda:** a faixa de 5 px na borda tem a cor da borda nas duas imagens (aqui entra a
   suspeita do 9.a).
4. **Área transparente:** quando a imagem não cobre a borda, as mesmas regiões são
   transparentes nas duas.
5. Cenários (parametrizados com `subTest`):
   - auto fit; ajuste inteligente (com patch de `detect_faces_ranked` para um rosto fixo);
   - zoom 37%, 100% (Ctrl+0), 250%; deslocada para fora da borda (área vazia);
   - **depois de redimensionar a janela** (a borda se desloca — já houve bug nisso);
   - imagem rotacionada (edição de pixels → `edited_images` / source override);
   - borda individual × global;
   - Fase 2, quando existir: cada estilo de borda; ajustes de tom (nitidez fora, ver a
     decisão 4 da Fase 2);
   - animação: comparar o **primeiro quadro** do overlay da prévia (`preview_item`) com o
     primeiro quadro do export.

**9.d — Paridade Revisão × arquivo final (exata)**
- `render_custom_preview(data)` e o PNG gravado por `process_image_task` com
  `output_path` têm que ser **pixel a pixel idênticos** (mesmo código; o teste protege
  contra alguém mudar um lado só).

### Casos de borda do próprio teste
- O CI roda em Windows com plataforma gráfica real; offscreen local
  (`QT_QPA_PLATFORM=offscreen`) também precisa passar — não depender de DPI: a cena é
  renderizada em coordenadas de cena, sem a view.
- Tempo: manter o conjunto abaixo de ~10 s (imagens sintéticas pequenas, exceto um caso
  grande).
- Se a suspeita do 9.a se confirmar, o primeiro commit é o teste marcado com
  `expectedFailure` **apenas para o cenário da borda**, seguido do commit de correção que
  remove a marcação — fica registrado que o teste pegou um bug real.

### Critérios de aceite
- [ ] Geometria idêntica (±1 px) entre canvas e export em todos os cenários.
- [ ] Cor dentro da tolerância; borda e transparência equivalentes.
- [ ] Revisão e arquivo final pixel a pixel iguais.
- [ ] Rodando no CI (job pytest) em menos de ~10 s.

### Commits
1. `test: paridade entre o canvas e o export (geometria, cor, borda, transparencia)`
2. `fix(canvas): borda desenhada para dentro, como no export` — **só se o 9.a se confirmar**
3. `test: revisao e arquivo exportado pixel a pixel iguais`

---

## Item 10 — Modo linha de comando (`--batch`)

### Objetivo
Gerar customs de uma pasta inteira sem abrir a janela:

```
python main.py --batch "C:\imagens\rem" --zip "C:\saida\rem.zip"
python main.py --batch pasta --out saida --preset "Anime padrão" --framing intelligent
python main.py --batch pasta --upload "Rem (Re:Zero)" --anim Rainbow
CustomMaker.exe --batch pasta --out saida --report relatorio.txt
```

Útil para lotes grandes, automação (agendar, scripts) e como **teste de ponta a ponta do
exe** no CI (como o `--self-test` já é).

### Estado atual (o que já ajuda)
- [main.py](main.py) já despacha `--self-test` antes de importar o Qt, depois de
  `multiprocessing.freeze_support()` — o `--batch` entra no mesmo lugar.
- `BatchController` aceita `editor_state`, `app_config`, `borda_hex`, `borda_pos` e
  **gera o enquadramento padrão sozinho** para imagens sem estado (`_default_state_for`,
  com cascade próprio e `default_framing`). Ou seja: com um `EditorState` só com a lista
  de imagens, `save_all_images` / `save_zip` / `upload_to_imgchest` já funcionam.
- Não importam Qt: `batch_controller`, `batch_worker`, `image_processor`, `editor_state`,
  `preset_manager`, `uploader`.
- **Ainda dentro de código Qt** (precisa ser extraído para reuso):
  - `mudae_command(s)` e `DISCORD_MESSAGE_LIMIT` em
    [export_mixin.py](src/qt/mixins/export_mixin.py);
  - a aplicação de preset em `apply_preset`
    ([adjustments_mixin.py](src/qt/mixins/adjustments_mixin.py)), que mistura estado e
    UI.
- O exe é gerado com `console=False` ([CustomMaker.spec](CustomMaker.spec)): **não tem
  stdout**. Ver 10.d.

### Passo a passo

**10.a — Extrações para o core (refatoração sem mudança de comportamento)**
1. `src/core/mudae.py` com `DISCORD_MESSAGE_LIMIT`, `mudae_command`, `mudae_commands`.
   `export_mixin.py` passa a importar de lá (manter os nomes antigos como alias para não
   quebrar testes: `ExportMixin.mudae_command = staticmethod(mudae.mudae_command)`).
2. `apply_preset_to_state(data, editor_state, app_config) -> dict` em
   [preset_manager.py](src/core/preset_manager.py): aplica borda, cor, animação,
   enquadramento padrão, blacklist (e, com a Fase 2, estilo e ajustes) e devolve o que
   mudou. `AdjustmentsMixin.apply_preset` chama essa função e só faz a parte de UI
   (refresh das abas, canvas, status).
3. Suíte inteira verde antes de seguir.

**10.b — `src/cli.py`**
1. `argparse` com:
   | Opção | Efeito |
   |---|---|
   | `--batch PASTA` (obrigatória) | imagens da pasta, não recursivo, na **mesma ordem do "Abrir pasta"** (`sorted(os.listdir)` filtrado por `SUPPORTED_EXTENSIONS`). Extrair essa listagem de `load_folder` ([image_loader_mixin.py](src/qt/mixins/image_loader_mixin.py)) para `list_folder_images(folder)` no core e usar nos dois lugares, para que a ordem nunca divirja |
   | `--out PASTA` \| `--zip ARQUIVO` \| `--upload TÍTULO` | destino (exatamente um; `--upload` imprime os comandos do Mudae) |
   | `--preset NOME` | aplica um preset salvo (`presets.json` do usuário) |
   | `--framing auto_fit\|intelligent` | sobrepõe o enquadramento padrão |
   | `--border NOME\|#RRGGBB` | borda (nome de `BORDA_HEX` ou hex → "Cor Personalizada") |
   | `--anim TIPO` | animação (Strobe exige `--allow-strobe`, espelhando o aviso de fotossensibilidade da interface) |
   | `--workers N` | sobrepõe `max_workers` |
   | `--report ARQUIVO` | grava o relatório (obrigatório no exe — ver 10.d) |
   | `--dry-run` | só lista o que seria feito (imagens, enquadramento, destino) |
2. Fluxo:
   1. validar argumentos (erro → mensagem clara + código 2);
   2. `AppConfig()` (lê a configuração do usuário, **sem gravar** nada nela);
   3. `EditorState(image_list=..., borda_pos=(0, 0))` + preset/flags;
   4. `BatchController(editor_state=..., app_config=..., borda_hex=BORDA_HEX, borda_pos=(0, 0), uploader=ImgChestUploader() se --upload)`;
   5. chamar o método do destino com `progress_callback` que imprime
      `[12/40] ok  nome_custom.png` / `[13/40] ERRO nome.jpg: motivo`;
   6. `Ctrl+C` → `cancel_event.set()` e sair com o que já foi feito (código 130);
   7. `batch_controller.shutdown()` no `finally` (encerra o pool).
3. Códigos de saída: `0` tudo ok; `1` parte falhou (relatório lista quais); `2` argumentos
   inválidos; `3` falha total (pasta vazia, sem token para upload etc.); `130` cancelado.
4. `--upload` sem token no `.env`: mensagem com o caminho do `.env`
   (`src/core/env_file.ENV_FILE`) e código 3 — nunca imprimir o token.
5. **Não** tocar em `session.json`, histórico de importação nem config: o modo CLI é
   somente leitura em relação ao estado do app.

**10.c — Ligação no `main.py`**
```python
if "--batch" in sys.argv:
    from src.cli import run_cli
    raise SystemExit(run_cli(sys.argv[1:]))
```
Depois de `freeze_support()` e antes de qualquer import de Qt (o pool usa spawn; o
guard `__main__` já existe).

**10.d — Saída no exe (`console=False`)**
1. No Windows, quando `--batch` é usado, tentar `ctypes.windll.kernel32.AttachConsole(-1)`
   (anexa ao terminal que chamou o exe) e reabrir `sys.stdout`/`sys.stderr` para `CONOUT$`.
   Se não houver terminal (duplo clique, agendador), seguir só com o `--report`.
2. Sempre gravar o relatório quando `--report` for passado (mesmo formato da saída, mais
   o resumo final), como o `--self-test` faz.
3. Documentar no README que, no exe, o terminal pode devolver o prompt antes do fim da
   execução (limitação de app GUI anexado a console); usar
   `start /wait CustomMaker.exe --batch ...` em scripts.

**10.e — CI**
- No job `exe` de [tests.yml](.github/workflows/tests.yml), depois do `--self-test`:
  gerar 3 imagens sintéticas numa pasta, rodar
  `CustomMaker.exe --batch pasta --zip out.zip --report batch-report.txt` com
  `start /wait`, e validar que o ZIP tem 3 PNGs de 225×350 (script Python pequeno).
  Anexar o relatório como annotation em caso de falha (mesmo padrão do self-test).

**10.f (opcional, depois) — `--danbooru "tags" --limit N`**
- Buscar e baixar do Danbooru direto no CLI. Exige extrair o download
  (`_download_post_files`, `_managed_import_directory` em
  [online_tab.py](src/qt/tabs/online_tab.py)) para o core, respeitando o histórico de
  importação, a blacklist e as credenciais (só nas chamadas de API, nunca nos downloads,
  como hoje). Fica fora desta fase pelo tamanho da extração.

### Casos de borda
- Pasta com nomes repetidos em extensões diferentes (`a.jpg`, `a.png`):
  `unique_output_names` já resolve.
- Imagem ilegível: entra como erro no relatório, o lote continua.
- `--out` inexistente: criar (`os.makedirs`); sem permissão → código 3.
- Preset inexistente: listar os presets disponíveis na mensagem de erro.
- Rodar o CLI com o app aberto: são processos separados, sem estado compartilhado. Só
  disputam CPU.

### Testes (`tests/test_cli.py`)
- Argumentos: combinações inválidas → código 2 (sem destino, dois destinos, `--anim
  Strobe` sem `--allow-strobe`, borda inexistente).
- `--out` com 3 imagens sintéticas → 3 PNGs 225×350; `--zip` → ZIP com 3 entradas.
- `--preset` aplica borda/animação (preset criado num `presets.json` temporário).
- `--dry-run` não grava nada.
- `--upload` com o uploader mockado imprime comandos do Mudae divididos em ≤ 2000
  caracteres; sem token → código 3 e nenhuma chamada de rede.
- O CLI **não** importa PySide6 (`"PySide6" not in sys.modules` depois de rodar, num
  subprocesso).
- `mudae.py` e `apply_preset_to_state`: os testes existentes de
  [test_mudae_command.py](tests/test_mudae_command.py) e presets passam apontando para o
  core.

### Critérios de aceite
- [ ] `python main.py --batch pasta --zip x.zip` gera as customs sem abrir janela.
- [ ] Preset, borda, animação e enquadramento funcionam pela linha de comando.
- [ ] O exe funciona com `--batch` e grava relatório; o CI valida isso.
- [ ] Nenhum arquivo de estado do usuário é alterado pelo CLI.

### Commits
1. `refactor: comandos do Mudae e aplicacao de preset movidos para o core`
2. `feat: modo linha de comando --batch (pasta, ZIP, upload)`
3. `feat(exe): saida no terminal e relatorio no modo --batch`
4. `ci: valida o --batch do exe com imagens sinteticas`

---

## Definição de pronto da Fase 3
- Suíte verde no CI, com os testes de paridade e de CLI.
- O job do exe valida `--self-test` **e** `--batch`.
- Medições registradas aqui: primeira Revisão × reabertura (cache) com 50 imagens; tempo
  do `--batch` com 50 imagens no exe.
- Este arquivo atualizado com o status de cada item.

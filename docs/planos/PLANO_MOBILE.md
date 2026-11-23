# Plano — CustomMaker no celular (app web instalável, versão 1)

> Status: **proposta, aguardando aprovação** (2026-11-22). Nada implementado.

## 1. Objetivo

Criar customs do Mudae pelo celular (Android e iPhone), com o mesmo resultado do app
de PC: buscar no Danbooru, escolher imagens, enquadrar com o dedo, aplicar a borda,
enviar ao ImgChest e copiar o comando `$ai` pronto para o Discord.

O PC continua sendo a ferramenta completa. O celular é a versão rápida, para quando
o PC não está à mão.

## 2. Decisões já tomadas

| Decisão | Escolha | Por quê |
|---|---|---|
| Tipo de app | **PWA**: site que vira ícone na tela inicial, abre em tela cheia | Funciona em Android e iPhone, sem loja nem conta paga |
| Hospedagem | **GitHub Pages** (grátis), publicado pelo CI | O repositório já é público e já tem CI |
| Servidor próprio | **Nenhum** | Testado em 2026-11-22: Danbooru, a CDN de imagens dele e o ImgChest aceitam chamadas direto do navegador (CORS liberado, inclusive o cabeçalho `Authorization` do upload) |
| Linguagem | **TypeScript** + Vite, sem framework de interface | Poucas telas; build pequeno e rápido no celular |
| Python no navegador (Pyodide) | **Não** | O primeiro acesso baixaria 30–40 MB e gerar GIF no celular ficaria lento |

Endereço previsto: `https://xganne.github.io/CustomMaker/`

## 3. Escopo

### Versão 1 (este plano)

1. **Buscar** no Danbooru por tags, com o filtro de classificação (padrão: **Geral**).
2. **★ Auto**: mesma regra do PC (sem questionável/explícito, tags sugestivas pesam
   contra, checagem de cor contra páginas de mangá, nota mínima, várias páginas).
   Também dá para escolher na mão, tocando nas miniaturas.
3. **Enquadrar** cada imagem: arrastar para mover, pinça para zoom, toque duplo para
   o auto fit.
4. **Borda**: as 20 cores do PC, cor personalizada e os 5 estilos (Simples, Dupla,
   Brilho, Degradê, Sombra).
5. **Gerar** as customs em PNG 225×350, iguais às do PC.
6. **Enviar ao ImgChest** (post oculto, na conta do token) e **copiar o comando `$ai`**,
   já dividido em mensagens de até 2000 caracteres.
7. **Configurações**: token do ImgChest, lista de tags que o Auto evita e resultados
   por página.
8. **Baixar** as customs para o celular, para quem não quiser usar o ImgChest.

### Fica para a versão 2

- Bordas animadas (GIF): Rainbow, Neon, Strobe etc.
- Ajustes de cor (brilho, contraste...) e presets.
- Ajuste inteligente pelo rosto. Precisa de um detector no navegador (opencv.js, ~8 MB),
  então fica fora até medirmos se vale o peso.
- Login do Danbooru (mais tags por busca), sessão salva e histórico de importados.

### Fora do celular

IA, modo `--batch`, lotes muito grandes e a Revisão com tamanhos de arquivo.

## 4. Telas

```
┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
│ 1. Buscar        │   │ 2. Escolher      │   │ 3. Enquadrar     │   │ 4. Enviar        │
│ [tags........] 🔍│   │ ▣ ▢ ▣ ▢         │   │   ┌────────┐     │   │ 5 customs ✓     │
│ Classif.: Geral  │ → │ ▢ ▣ ▢ ▣  ★ Auto │ → │   │ imagem │ ↔ ⤢ │ → │ [Enviar ImgChest]│
│ recentes...      │   │ 4 selecionadas   │   │   └────────┘     │   │ $ai Nome $ ...   │
│                  │   │ [Enquadrar →]    │   │ Borda ● ● ● Est. │   │ [Copiar comando] │
└──────────────────┘   └──────────────────┘   │ ◀ 2/4 ▶ [Gerar] │   │ [Baixar PNGs]    │
                                              └──────────────────┘   └──────────────────┘
```

- A borda fica fixa no centro da tela de enquadrar; a imagem se move por baixo, como
  no canvas do PC.
- O nome da custom (o `Nome` do `$ai`) é pedido na tela 4, já preenchido com o
  personagem da busca.
- Tudo em português, tema escuro como o do PC.

## 5. Fidelidade ao PC (a parte mais importante)

O risco de ter duas implementações é a custom do celular sair diferente da do PC. Regras:

1. **Mesma ordem de render do PC** (`ImageProcessor.render_image_to_borda`):
   redimensiona a imagem inteira para o tamanho enquadrado e depois recorta os
   225×350 da área da borda. Partes fora da imagem ficam transparentes.
2. **Mesmo redimensionamento**: o PC usa Lanczos (PIL `LANCZOS`, a=3). O canvas do
   navegador não oferece Lanczos, então o web usa a biblioteca **pica**, que
   implementa Lanczos3.
3. **Borda Simples idêntica**: retângulo de 5 px (`BORDER_THICKNESS`) nos 225×350
   (`add_borda_to_image`). Os outros estilos seguem `border_styles.py`: Dupla (3 px por
   fora, vão de 2 px, 1 px por dentro), Brilho (desfoque 6 a 55%), Sombra (faixa de 9 px,
   desfoque 5 a 40%) e Degradê (mesma matiz ±25% de luminosidade, de cima para baixo).
4. **Uma fonte só para as tabelas**: cores (`BORDA_HEX`), pesos do Auto
   (`custom_scorer.py`), tags evitadas e limites (225×350, 5 px, 2000 caracteres) são
   exportados do Python para `web/src/generated/rules.json` por um script. Um teste no
   Python confere que o JSON está em dia. Mudou o peso no PC, o celular acompanha.
5. **Testes de paridade**: um script Python gera customs de referência (`.png`) com o
   código do PC, cobrindo os 5 estilos, imagem maior e menor que a borda e imagem
   deslocada. Os testes do web geram as mesmas customs e comparam pixel a pixel. A
   tolerância precisa ser calibrada, porque o Lanczos do pica não é bit a bit igual ao
   do PIL: começar exigindo diferença média < 1/255 e máxima < 8/255. A borda Simples
   tem que sair exata.

## 6. Organização no repositório

```
web/                         ← app do celular (novo)
  index.html
  manifest.webmanifest       ← nome, ícone, tela cheia (instalável)
  sw.js                      ← service worker: abre rápido e sem internet
  src/
    core/                    ← lógica portada do Python, sem interface
      render.ts              ← resize + recorte (render_image_to_borda)
      borders.ts             ← os 5 estilos (border_styles.py)
      autofit.ts             ← auto fit (calculate_auto_fit_pos)
      scorer.ts              ← ★ Auto (custom_scorer.py)
      danbooru.ts            ← busca, filtro de blacklist, página seguinte
      imgchest.ts            ← upload (uploader.py)
      mudae.ts               ← comando $ai dividido (mudae.py)
    ui/                      ← as 4 telas e os gestos
    generated/rules.json     ← gerado do Python (não editar na mão)
  tests/                     ← Vitest (lógica e paridade)
scripts/export_web_rules.py  ← gera rules.json
scripts/web_fixtures.py      ← gera as customs de referência
.github/workflows/pages.yml  ← testa e publica o web no GitHub Pages
```

O código Python do PC não muda, exceto pelos dois scripts acima. O CI do PC continua
igual. O do web roda só quando algo em `web/` (ou nas regras) muda.

## 7. Dados e segurança

- **Token do ImgChest**: colado nas Configurações do app e guardado **só no
  navegador do celular** (`localStorage`). Nunca vai para o repositório nem para o
  site, e o app não manda para nenhum lugar além do `api.imgchest.com`. Botão
  "Esquecer token".
- **Danbooru**: anônimo na versão 1, com limite de 2 tags por busca; a classificação
  não conta no limite.
- **Memória do celular**: para enquadrar, usa a prévia grande do Danbooru
  (`large_file_url`). Só na hora de gerar a custom baixa o original, e já reduz no
  próprio download (`createImageBitmap` com `resizeWidth`), sem abrir a imagem inteira.
  Uma foto de 2900×4100 decodificada pesaria ~47 MB, e celulares fecham a aba com
  bem menos.
- **Conteúdo**: o filtro de classificação começa em **Geral**, e o ★ Auto segue as
  mesmas regras do PC.

## 8. Fases de implementação

Cada fase termina com testes passando e uma versão publicada que você pode abrir no
celular.

### M1 — Base e render (sem telas)
- Projeto `web/` (Vite + TypeScript + Vitest) e workflow do GitHub Pages.
- `scripts/export_web_rules.py` e o teste Python que confere o `rules.json`.
- `render.ts`, `borders.ts` e `autofit.ts`, com os **testes de paridade** contra as
  customs de referência do Python.
- **Pronto quando:** as customs do web batem com as do PC nos 5 estilos (Simples
  exata), e uma página de teste publicada mostra as cinco.

### M2 — Buscar e escolher
- `danbooru.ts` (busca, blacklist, paginação) e `scorer.ts` (★ Auto com checagem de
  cor e várias páginas), com testes reaproveitando os casos do PC (mangá sem a tag
  `comic`, explícito popular, já escolhidos).
- Telas 1 e 2: busca, grade de miniaturas, seleção por toque, ★ Auto.
- **Pronto quando:** a busca real `nihilux_(honkai:_star_rail)` escolhe as mesmas
  candidatas que o PC escolheria.

### M3 — Enquadrar
- Tela 3: borda fixa, arrastar, pinça, toque duplo (auto fit), cor e estilo da
  borda, navegação entre as escolhidas.
- **Pronto quando:** dá para enquadrar 5 imagens confortavelmente no seu celular, e a
  custom gerada é igual à prévia.

### M4 — Enviar e instalar
- `imgchest.ts`, `mudae.ts` e tela 4: gerar, enviar, copiar o comando, baixar os PNGs.
- Configurações (token, tags evitadas, resultados por página).
- Manifest + service worker: "Adicionar à tela inicial", tela cheia, abre sem internet.
- **Pronto quando:** você cria uma custom de verdade do começo ao fim no celular e
  o `$ai` funciona no Discord.

**Estimativa:** M1–M4 ≈ uma a duas fases do tamanho das Fases 1–3 do PC, mais rodadas
de ajuste com você testando no celular (gestos e desempenho eu não consigo testar
aqui).

## 9. Testes

- **Lógica** (Vitest, em segundos): render, bordas, auto fit, Auto, divisão do `$ai`,
  montagem do upload (`images[]`, `privacy=hidden`, sem `anonymous`).
- **Paridade com o PC**: customs de referência geradas pelo Python (seção 5).
- **Regras em dia**: teste Python garante que `rules.json` bate com o código do PC.
- **No celular, por você**: um roteiro curto por fase (o que tocar, o que deve
  acontecer). Os gestos e a memória só se validam no aparelho de verdade.

## 10. Riscos

| Risco | Impacto | Mitigação |
|---|---|---|
| Custom do celular diferente da do PC | Alto | Testes de paridade (seção 5) e tabelas geradas do Python |
| Celular sem memória com imagem grande | Médio | Prévia para enquadrar; original reduzido no download (seção 7) |
| Danbooru ou ImgChest mudarem o CORS | Alto (o app para) | Checagem no início do app com mensagem clara; plano B é um repassador grátis (Cloudflare Worker) |
| iPhone: limites de PWA (armazenamento pode ser limpo pelo sistema) | Baixo | Na versão 1 só o token e as preferências ficam salvos; colar de novo resolve |
| Safari (iPhone) sem a redução no download (`resizeWidth`) | Médio | Detectar e, sem ela, usar o `large_file_url` também para gerar (resolução menor, mas sem estourar a memória) |
| Gestos desconfortáveis | Médio | Rodadas de ajuste com você na fase M3 |

## 11. O que preciso que você decida

1. **Endereço público:** o app fica em `xganne.github.io/CustomMaker` e qualquer
   pessoa com o link consegue abrir (o token de cada um fica só no próprio celular).
   Tudo bem?
2. **Versão 1 só com PNG estático** (animações na versão 2): de acordo?
3. **Seu celular é Android ou iPhone?** Começo calibrando para ele.

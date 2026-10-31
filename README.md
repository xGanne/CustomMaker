# CustomMaker

[![Testes](https://github.com/xGanne/CustomMaker/actions/workflows/tests.yml/badge.svg)](https://github.com/xGanne/CustomMaker/actions/workflows/tests.yml)

CustomMaker é um editor desktop para criar customs do Mudae no formato 225x350. A interface principal usa Qt/PySide6 e reúne edição de borda, ajustes de enquadramento, processamento em lote, busca online, presets, exportação e upload.

## Recursos

- **Editor Qt**: carregue uma pasta, cole imagens da área de transferência, ajuste enquadramento, desfaça alterações e aplique bordas.
- **Bordas e animações**: escolha cores prontas, cor personalizada, conta-gotas e efeitos animados como rainbow, neon, strobe, glitch, spin e flow.
- **Processamento em lote**: aplique auto fit ou ajuste inteligente em todas as imagens e exporte tudo como imagens ou ZIP.
- **Busca Danbooru**: pesquise por tags, filtre rating/ordenação, visualize resultados e importe imagens para a lista.
- **Presets**: salve combinações de borda, cor e animação para reutilizar depois.
- **Upload ImgChest**: envie as imagens processadas e copie o comando pronto para usar no Mudae.
- **IA em modo seguro**: com Gemini configurado, a aba IA gera uma descrição textual da edição desejada quando edição real de imagem não está disponível.

## Requisitos

- Python 3.11
- Dependências:

```sh
pip install -r requirements.txt
```

Ou via metadata do projeto:

```sh
pip install .
pip install ".[dev]"
```

## Configuração

Crie um arquivo `.env` na raiz do projeto:

```sh
IMG_CHEST_API_TOKEN=seu_token_aqui
GEMINI_API_KEY=sua_chave_gemini_aqui
```

`IMG_CHEST_API_TOKEN` é necessário para upload. `GEMINI_API_KEY` é opcional e habilita a geração de descrições na aba IA.

As preferências locais ficam em `custommaker_config.json`. A chave `ai_base_prompt` controla a instrução base usada pela IA.

## Uso

Execute a aplicação principal:

```sh
python main.py
```

Fluxo básico:

1. Selecione uma pasta ou cole uma imagem.
2. Ajuste enquadramento, borda, cor e animação.
3. Exporte como imagens, ZIP ou envie para ImgChest.
4. Use a busca online para importar imagens quando quiser montar novos lotes.

## Linha de comando (`--batch`)

Gera as customs de uma pasta sem abrir a janela:

```sh
python main.py --batch "C:\imagens\rem" --zip "C:\saida\rem.zip"
python main.py --batch pasta --out saida --preset "Anime" --framing intelligent
python main.py --batch pasta --upload "Rem (Re:Zero)" --anim Rainbow   # imprime os comandos do Mudae
python main.py --batch pasta --out saida --dry-run                      # só mostra o que faria
```

Opções: `--preset NOME`, `--framing auto_fit|intelligent`, `--border NOME|#RRGGBB`,
`--style simples|dupla|brilho|degrade|sombra`, `--anim TIPO` (o Strobe exige
`--allow-strobe`), `--workers N`, `--report ARQUIVO`. Códigos de saída: `0` ok, `1` parte
falhou, `2` argumentos inválidos, `3` nada pôde ser feito, `130` cancelado (Ctrl+C). O modo
linha de comando só lê a configuração e os presets do app; não grava nada neles.

No `CustomMaker.exe` a saída aparece no terminal que o chamou, mas o prompt pode voltar
antes do fim (o exe é um app gráfico). Em scripts, use `start /wait` e o `--report`:

```bat
start /wait CustomMaker.exe --batch pasta --zip saida.zip --report relatorio.txt
```

## Testes

No dia a dia, rode só os testes ligados ao que você mudou — segundos, não a suíte inteira:

```sh
python scripts/test_changed.py              # mudanças ainda não commitadas
python scripts/test_changed.py --since main # + o que mudou desde um ref
python scripts/test_changed.py --list       # só mostra quais testes rodaria
```

O script escolhe os testes que citam o módulo alterado (import ou `patch`) ou têm nome
parecido com ele (`review_dialog.py` → `test_review.py`), e mostra o motivo de cada um.

A suíte inteira (`python scripts/test_changed.py --all`, ou `python -m pytest`) roda
sozinha no GitHub Actions a cada push e pull request (`.github/workflows/tests.yml`); o
selo no topo mostra o resultado do `main`. Localmente só é preciso em mudanças que afetam
tudo, como `tests/conftest.py`.

Nos testes, a exportação roda em threads dentro do próprio processo, e não no pool de
processos do app: cada processo do pool carrega numpy/OpenCV/PIL de novo. Só os testes
marcados com `@pytest.mark.real_pool` (autoteste do exe e o pool em si) usam processos.

## Sobre

O projeto existe para reduzir o trabalho repetitivo de criar customs para usuários do Mudae no Discord, mantendo o fluxo de edição, exportação e upload em uma única ferramenta.

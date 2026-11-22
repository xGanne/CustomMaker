# CustomMaker

[![Testes](https://github.com/xGanne/CustomMaker/actions/workflows/tests.yml/badge.svg)](https://github.com/xGanne/CustomMaker/actions/workflows/tests.yml)

CustomMaker é um editor desktop para criar customs do Mudae no formato 225x350. A interface principal usa Qt/PySide6 e reúne edição de borda, ajustes de enquadramento, processamento em lote, busca online, presets, exportação e upload.

## Baixar

Baixe o `CustomMaker.exe` da [última Release](https://github.com/xGanne/CustomMaker/releases/latest) — não precisa instalar nem ter Python.

Depois disso o app se atualiza sozinho: quando sai uma versão nova, ele baixa em segundo plano,
confere o arquivo (SHA-256) e mostra **Reiniciar para atualizar** na barra de status; nada é
trocado antes do clique, e se a versão nova não abrir, a anterior volta. Para isso o exe precisa
ficar numa pasta onde dá para gravar (não em Arquivos de Programas). Desligue em
Configurações › Aparência para só ser avisado.

## Recursos

- **Editor Qt**: carregue uma pasta, cole imagens da área de transferência, ajuste enquadramento, desfaça alterações (com histórico nomeado) e aplique bordas.
- **Bordas e animações**: cores prontas, cor personalizada, conta-gotas, estilos de borda e efeitos animados como rainbow, neon, strobe, glitch, spin e flow.
- **Ajustes de cor**: brilho, contraste, saturação e outros, com prévia ao vivo igual ao export.
- **Processamento em lote**: auto fit ou ajuste inteligente (rosto) em todas as imagens; exporte como imagens ou ZIP.
- **Revisão**: grade com todas as customs como sairão e o tamanho de cada arquivo antes do upload.
- **Busca Danbooru**: pesquise por tags, filtre rating/ordenação e importe imagens. O **★ Auto** pré-seleciona boas candidatas a custom (personagem único, colorida, boa resolução) em uma ou mais páginas — conteúdo questionável/explícito nunca entra, e tags sugestivas pesam contra.
- **Presets**: salve combinações de borda, cor, animação e ajustes para reutilizar depois.
- **Upload ImgChest**: envie as customs e copie o comando pronto para o Mudae.
- **Sessão**: lista, enquadramentos e edições são salvos sozinhos e oferecidos de volta ao reabrir.
- **Paleta de comandos** (`Ctrl+K`): encontre qualquer ação digitando.
- **IA em modo seguro**: com Gemini configurado, a aba IA gera uma descrição textual da edição desejada quando edição real de imagem não está disponível.

## Configuração

Crie um arquivo `.env` (no exe ele fica em `%LOCALAPPDATA%\CustomMaker\`; rodando pelo código,
na raiz do projeto):

```sh
IMG_CHEST_API_TOKEN=seu_token_aqui
GEMINI_API_KEY=sua_chave_gemini_aqui
```

`IMG_CHEST_API_TOKEN` é necessário para upload. `GEMINI_API_KEY` é opcional e habilita a
geração de descrições na aba IA. A conta do Danbooru (opcional, libera mais tags por busca) é
configurada em Configurações › Danbooru e também fica só no `.env`.

As preferências ficam em `custommaker_config.json`, na mesma pasta do `.env`.

## Logs e relato de bugs

`Ctrl+K` › **Abrir pasta de logs** abre a pasta com o `app.log` (erros, avisos do Qt) e o
`crash.log` (fechamentos inesperados). São esses os arquivos a anexar ao relatar um problema.

## Rodar pelo código-fonte

Requer Python 3.11:

```sh
pip install -r requirements.txt
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

## Lançar uma versão

1. Suba o número em `src/version.py` (ex.: `1.2.3`) e faça o commit.
2. Crie e envie a tag com o mesmo número:

   ```sh
   git tag -a v1.2.3 -m "Custom Maker 1.2.3"
   git push origin main
   git push origin v1.2.3
   ```

O CI roda os testes, gera o exe, testa a autoatualização nele de verdade e publica a Release
com o `CustomMaker.exe`. Se a tag não bater com `src/version.py`, nada é publicado. Quem já
tem o app recebe a versão nova pela autoatualização.

## Sobre

O projeto existe para reduzir o trabalho repetitivo de criar customs para usuários do Mudae no Discord, mantendo o fluxo de edição, exportação e upload em uma única ferramenta.

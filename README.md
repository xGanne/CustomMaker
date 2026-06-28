# CustomMaker

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

A interface CustomTkinter antiga continua disponível como fallback legado:

```sh
python main_legacy.py
```

Fluxo básico:

1. Selecione uma pasta ou cole uma imagem.
2. Ajuste enquadramento, borda, cor e animação.
3. Exporte como imagens, ZIP ou envie para ImgChest.
4. Use a busca online para importar imagens quando quiser montar novos lotes.

## Testes

Rode a suíte automatizada:

```sh
python -m pytest -q
```

Para uma checagem rápida de sintaxe:

```sh
python -m py_compile main.py main_qt.py main_legacy.py src/core/ai_pipeline.py src/core/app_config.py src/controllers/batch_controller.py src/qt/main_window.py src/qt/tabs/ai_tab.py src/qt/tabs/editor_tab.py src/qt/tabs/online_tab.py
```

## Sobre

O projeto existe para reduzir o trabalho repetitivo de criar customs para usuários do Mudae no Discord, mantendo o fluxo de edição, exportação e upload em uma única ferramenta.

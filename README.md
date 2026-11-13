# ETL de Covid-19: países com IDH próximo ao do Brasil

Projeto de estudo de ETL em Python. Extrai um dataset público de Covid-19, seleciona os países com IDH parecido com o do Brasil, limpa e padroniza os dados dos dois primeiros anos da pandemia e os carrega em um banco SQLite, sem duplicar registros ao rodar mais de uma vez.

**Status:** ETL concluído (extração, transformação, validação, carga e testes). Falta apenas a análise opcional com gráficos (veja [Pendências](#pendências)).

## Pergunta do projeto

> Como foi a incidência de Covid-19 nos países com IDH parecido com o do Brasil durante os dois primeiros anos da pandemia (2020 e 2021)?

## Estrutura do projeto

```
.
├── main.py            # roda o ETL completo, na ordem
├── config.py          # parâmetros: margem de IDH, período, colunas, caminho do banco
├── extract.py         # extração (lê o dataset do Kaggle)
├── transform.py       # seleção dos países, limpeza, correção e validação
├── load.py            # criação do banco, carga sem duplicar e conferência
├── tests/             # testes com dados sintéticos (pytest)
├── requirements.txt
└── data/              # banco SQLite gerado pelo ETL (fora do Git)
```

## Como rodar

Exemplo para o CMD do Windows. Use uma versão de Python estável (3.12 ou 3.13): em versões muito novas, algumas dependências ainda não têm pacotes prontos e o `pip` tenta compilá-las, o que falhou aqui com o `pyyaml`.

```
py -3.13 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
```

Rodar o ETL:

```
python main.py
```

Rodar de novo com os mesmos dados não duplica nada. Para apagar o banco e criar tudo de novo (necessário quando a margem de IDH, o período ou o esquema das tabelas mudam):

```
python main.py --recriar
```

Rodar os testes:

```
python -m pytest
```

Versão de Python usada neste projeto: _3.13_

## Definições

Estas escolhas determinam o resultado e podem ser mudadas em `config.py`.

| Termo | Definição adotada |
|---|---|
| Incidência | Casos por milhão de habitantes (colunas `*_per_million` do dataset). Casos absolutos não servem para comparar países de tamanhos diferentes. |
| IDH do Brasil | 0,76, lido do próprio dataset. |
| IDH parecido | IDH dentro de ±0,02 do IDH do Brasil. A diferença é arredondada em 4 casas decimais antes da comparação, para evitar erros de ponto flutuante nas bordas (sem o arredondamento, 21 países com IDH exatamente em 0,74 ou 0,78 ficavam de fora). |
| População mínima | 1.000.000 de habitantes. Em países muito pequenos, valores por milhão oscilam demais. |
| Período | De 01/01/2020 a 31/12/2021. |

Foram testadas duas margens: ±0,01 (10 países, contando o Brasil) e ±0,02 (31 países). Adotou-se ±0,02 com a população mínima, que resulta em 22 países.

## Fonte dos dados

- **Dataset:** [`aliahmadmphil/global-covid-19-pandemic-full-data-2020-2026`](https://www.kaggle.com/datasets/aliahmadmphil/global-covid-19-pandemic-full-data-2020-2026), no Kaggle.
- **Arquivo usado:** `COVID19_Complete_Dataset/covid19_complete_20260829.csv`.
- **Tamanho:** 429.435 linhas e 73 colunas, de 01/01/2020 a 14/08/2024. Cada linha é uma localidade em um dia.
- **Como é lido:** pela biblioteca `kagglehub`, com `dataset_load` e o adaptador do pandas.
- **Onde fica guardado:** no cache do `kagglehub`, fora da pasta do projeto (por padrão em `~/.cache/kagglehub/`; no Windows, `C:\Users\<usuário>\.cache\kagglehub\`). O download acontece só na primeira execução.
- **Data da última execução:** 12/11/2026

## O que o ETL faz

### Extração

O CSV é carregado em um DataFrame do pandas a partir do cache do `kagglehub` (`extract.py`).

### Transformação (`transform.py`)

| # | Etapa | Resultado |
|---|---|---|
| 1 | Remover linhas que não são países, identificadas por `continent` vazio | 255 localidades caem para 243. Foram removidas 12: seis continentes, quatro grupos de renda, a União Europeia e o mundo. |
| 2 | Remover países sem IDH (valor 0 no dataset) | 243 caem para 189. |
| 3 | Manter os países com IDH a até 0,02 do Brasil | 31 países, contando o Brasil. |
| 4 | Aplicar a população mínima de 1.000.000 | 22 países, contando o Brasil. |
| 5 | Filtrar as linhas diárias desses países e converter `date` de texto para data | |
| 6 | Filtrar o período de 2020 a 2021 | 15.999 linhas. |
| 7 | Selecionar as colunas mantidas | Veja a lista abaixo. |
| 8 | Corrigir zeros indevidos nos acumulados (zero depois de o acumulado já ter sido positivo) | 1 linha corrigida: Thailand, `total_deaths_per_million`, em 22/11/2020. O acumulado caiu de 0,84 para 0,0 e foi trocado pelo valor do dia anterior (0,84). |
| 9 | Validar o resultado antes da carga | `validar` falha se houver duplicatas, valores negativos nas colunas diárias, vazios, zeros indevidos, dias faltando no meio da série ou datas fora do período. |
| 10 | Separar nas duas tabelas do banco | A data vira texto `AAAA-MM-DD` e `location` fica só na tabela de países. |

### Países do grupo (22)

Algeria, Armenia, Azerbaijan, Bosnia and Herzegovina, Botswana, Brazil, China, Colombia, Cuba, Dominican Republic, Ecuador, Iran, Lebanon, Mexico, Moldova, Mongolia, North Macedonia, Peru, Sri Lanka, Thailand, Tunisia, Ukraine.

Lista obtida na execução de _02/11/2026_. O grupo é calculado pelo código a partir do IDH do dataset, então pode mudar se o dataset for atualizado.

### Colunas mantidas

| Grupo | Coluna |
|---|---|
| Identificação | `iso_code`, `location`, `continent`, `date` |
| Casos | `new_cases_smoothed_per_million`, `total_cases_per_million` |
| Mortes | `new_deaths_smoothed_per_million`, `total_deaths_per_million` |
| Critério do grupo | `human_development_index`, `population` |

As colunas "smoothed" são médias suavizadas, que reduzem a oscilação causada por atrasos de notificação.

### Carga (`load.py`)

- Os dados são gravados com *upsert* (`INSERT ... ON CONFLICT DO UPDATE`): se a chave já existe, a linha é atualizada em vez de duplicada. Assim, corrigir um dado e rodar de novo atualiza o banco.
- Países e medições são gravados em uma única transação, e os países primeiro (as medições dependem deles). Se algo falhar, nada é gravado.
- Os valores são convertidos para tipos nativos do Python antes de gravar, porque tipos do NumPy podem ser gravados pelo `sqlite3` como dado binário.
- Depois da carga, `conferir_banco` confirma que as contagens batem com os dados, que não há violação de chave estrangeira e que população foi gravada como inteiro e os demais valores como número decimal.
- Se o arquivo `.db` foi criado por uma versão antiga do esquema, o ETL avisa e pede `--recriar`, em vez de falhar no meio da carga.

## Banco de dados (SQLite)

Duas tabelas, para não repetir o IDH em milhares de linhas diárias.

**`paises`** (uma linha por país)

| Coluna | Tipo | Restrições |
|---|---|---|
| `iso_code` | TEXT | chave primária |
| `location` | TEXT | obrigatório |
| `continent` | TEXT | obrigatório |
| `human_development_index` | REAL | obrigatório, maior que 0 e até 1 |
| `population` | INTEGER | obrigatório, maior que 0 |

**`medicoes_diarias`** (uma linha por país e dia)

| Coluna | Tipo | Restrições |
|---|---|---|
| `iso_code` | TEXT | chave primária (com `date`) e chave estrangeira para `paises` (`ON DELETE CASCADE`) |
| `date` | TEXT | formato `AAAA-MM-DD` |
| `new_cases_smoothed_per_million` | REAL | obrigatório, maior ou igual a 0 |
| `new_deaths_smoothed_per_million` | REAL | obrigatório, maior ou igual a 0 |
| `total_cases_per_million` | REAL | obrigatório, maior ou igual a 0 |
| `total_deaths_per_million` | REAL | obrigatório, maior ou igual a 0 |

No SQLite, as chaves estrangeiras vêm desligadas por padrão, então o ETL liga `PRAGMA foreign_keys = ON` a cada conexão.

**Resultado esperado em uma execução com os dados reais:** 22 países, 15.999 medições, de 2020-01-01 a 2021-12-31, e os mesmos números ao rodar uma segunda vez.

## Verificações de qualidade feitas

- **Linhas duplicadas** para a mesma combinação de país e data: nenhuma (0). Isso permite usar país e data como chave primária.
- **Linhas por país no período:** Mexico tem 731 (série completa); Thailand, 728; os outros 20 países, 727. A diferença vem de séries que começam alguns dias depois de 01/01/2020.
- **Continuidade:** o teste de dias esperados contra linhas existentes não encontrou nenhum dia faltando no meio das séries. A validação do ETL repete esse teste a cada execução.
- **IDH fixo por país:** cada localidade tem um único valor de IDH no dataset.
- **Valores negativos:** nenhum em `new_cases_smoothed_per_million`. A validação cobre as duas colunas diárias.
- **Quedas em acumulados (3 ocorrências):**
  - Thailand, mortes, 22/11/2020: o acumulado foi de 0,84 para 0,0. Era dado faltante preenchido com zero, e foi **corrigido**.
  - Ecuador, casos, 13/09/2020: queda de 89,43 (cerca de 1,4% do acumulado). Parece revisão de contagem na origem. **Mantida.**
  - Thailand, casos, 26/01/2020: queda de 0,01, o menor passo possível nessa coluna. **Mantida.**
- **Primeiro valor positivo:** os primeiros casos de todos os países aparecem entre janeiro e abril de 2020, e as primeiras mortes vêm no mesmo dia ou depois, com uma exceção (Botswana, veja as limitações).
- **Testes automatizados:** 31 testes em `tests/`, com dados sintéticos de mesma estrutura do dataset. Cobrem a seleção dos países (incluindo a borda da margem), a correção de zeros, as verificações, a validação, a carga sem duplicar, o upsert, a transação única, as chaves e as restrições do banco.

## Limitações conhecidas

- **Dados faltantes viraram zero.** Quase nenhuma coluna do dataset tem valores vazios, mesmo as que em muitos países nunca foram registradas. Isso indica que o autor do dataset substituiu dados ausentes por 0. Um zero pode, portanto, significar tanto "nenhum caso" quanto "sem informação". O mesmo vale para o IDH, onde 0 foi tratado como ausência de dado.
- **IDH e população sem ano de referência.** O dataset não informa a que ano esses valores se referem, e a população foi lida de uma linha de cada país.
- **Notificação desigual entre países.** Países testam e registram casos e mortes de formas muito diferentes, então a comparação de incidência não é totalmente justa. Isso vale especialmente para a interpretação de "quem foi mais afetado".
- **Duas casas decimais nas colunas por milhão.** Valores muito pequenos viram 0,00, então o primeiro valor positivo de um país grande pode aparecer alguns dias depois do primeiro caso real.
- **Botswana registra mortes antes de casos.** A primeira morte (`new_deaths_smoothed_per_million`) aparece em 29/03/2020 e o primeiro caso em 05/04/2020. É uma inconsistência da origem, e os dados foram mantidos como estão. O ETL registra um aviso a cada execução.
- **Revisões de contagem na origem.** Duas quedas em acumulados de casos (Ecuador e Thailand) foram mantidas, porque parecem revisões e não erros de preenchimento.
- **Sem grupo de contraste.** Como só entram países da faixa de IDH escolhida, o projeto não permite concluir se o IDH em si influencia a incidência. Ele mostra como países parecidos se comportaram.
- **Exclusão de países pequenos.** A população mínima de 1 milhão remove 9 países da faixa de IDH, como Saint Lucia (cerca de 180 mil habitantes).
- **O upsert não apaga linhas antigas.** Se a margem de IDH ou o período mudar, países e datas que saíram do grupo continuariam no banco. A conferência pós-carga detecta isso (as contagens deixam de bater) e pede `--recriar`.
- **Dependência do dataset.** Os resultados dependem da versão do dataset no Kaggle e dos valores de IDH dele, e não de uma fonte oficial.
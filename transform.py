"""Transformação: seleciona o grupo de países, limpa as medições e valida o resultado."""
import pandas as pd

from config import (
    COLUNAS_ACUMULADAS,
    COLUNAS_DIARIAS,
    COLUNAS_MEDICOES,
    COLUNAS_MEDICOES_BANCO,
    COLUNAS_PAISES,
    DATA_FIM,
    DATA_INICIO,
    MARGEM_IDH,
    PAIS_REFERENCIA,
    POPULACAO_MINIMA,
    TOLERANCIA_QUEDA,
)


def selecionar_paises(df):
    """
    Devolve uma linha por país que atende aos critérios do projeto e o IDH de referência.

    Critérios, nesta ordem:
    1. É país (continent preenchido). Continentes, grupos de renda e "World" saem.
    2. Tem IDH informado (no dataset, IDH 0 significa "sem dado").
    3. IDH a no máximo MARGEM_IDH do país de referência.
    4. População acima de POPULACAO_MINIMA.
    """
    so_paises = df[df["continent"].notna()]
    um_por_pais = so_paises[COLUNAS_PAISES].drop_duplicates(subset="location")
    com_idh = um_por_pais[um_por_pais["human_development_index"] > 0]

    referencia = com_idh.loc[com_idh["location"] == PAIS_REFERENCIA, "human_development_index"]
    if referencia.empty:
        raise ValueError(f"País de referência não encontrado (ou sem IDH): {PAIS_REFERENCIA}")
    idh_referencia = referencia.iloc[0]

    # O arredondamento evita que erros de ponto flutuante (0.78 - 0.76 = 0.02000000000000002)
    # deixem de fora países que estão exatamente na borda da margem.
    distancia = (com_idh["human_development_index"] - idh_referencia).abs().round(4)

    perto_do_idh = distancia <= MARGEM_IDH
    populacao_suficiente = com_idh["population"] > POPULACAO_MINIMA

    paises = com_idh[perto_do_idh & populacao_suficiente]
    paises = paises.sort_values("location").reset_index(drop=True)
    return paises, idh_referencia


def verificar_valores_fixos(df, paises):
    """
    Lista países do grupo cujo IDH ou população varia entre as linhas.
    O ETL usa a primeira linha de cada país; se algo variar, vale decidir outra regra.
    """
    do_grupo = df[df["location"].isin(paises["location"])]
    valores_distintos = do_grupo.groupby("location")[["human_development_index", "population"]].nunique()
    return valores_distintos[(valores_distintos > 1).any(axis=1)]


def montar_medicoes(df, paises):
    """Filtra os países do grupo e o período, converte a data e mantém só as colunas do projeto."""
    medicoes = df[df["location"].isin(paises["location"])].copy()
    medicoes["date"] = pd.to_datetime(medicoes["date"])

    no_periodo = (medicoes["date"] >= DATA_INICIO) & (medicoes["date"] <= DATA_FIM)
    medicoes = medicoes[no_periodo]

    medicoes = medicoes[COLUNAS_MEDICOES].sort_values(["location", "date"])
    return medicoes.reset_index(drop=True)


def corrigir_zeros_indevidos(medicoes):
    """
    Corrige zeros no meio de um acumulado.

    Um acumulado não volta a zero depois de ter sido positivo. Quando isso acontece, o zero
    é dado faltante que o dataset preencheu com 0. O valor é trocado pelo do dia anterior.
    Zeros no início da série (antes do primeiro caso) são reais e não são alterados.

    Devolve a tabela corrigida e um registro de cada linha alterada.
    """
    medicoes = medicoes.copy()
    registros = []

    for coluna in COLUNAS_ACUMULADAS:
        maior_valor_ate_aqui = medicoes.groupby("location")[coluna].cummax()
        zero_indevido = (medicoes[coluna] == 0) & (maior_valor_ate_aqui > 0)

        if not zero_indevido.any():
            continue

        corrigido = medicoes[coluna].mask(zero_indevido)
        corrigido = corrigido.groupby(medicoes["location"]).ffill()

        alteradas = medicoes.loc[zero_indevido, ["location", "date"]].copy()
        alteradas["coluna"] = coluna
        alteradas["valor_original"] = medicoes.loc[zero_indevido, coluna]
        alteradas["valor_corrigido"] = corrigido[zero_indevido]
        registros.append(alteradas)

        medicoes[coluna] = corrigido

    colunas_registro = ["location", "date", "coluna", "valor_original", "valor_corrigido"]
    if registros:
        registro = pd.concat(registros).reset_index(drop=True)
    else:
        registro = pd.DataFrame(columns=colunas_registro)
    return medicoes, registro


def listar_quedas(medicoes, coluna):
    """Linhas em que um acumulado diminuiu (acima da tolerância de arredondamento)."""
    ordenado = medicoes.sort_values(["location", "date"])
    variacao = ordenado.groupby("location")[coluna].diff().round(4)
    caiu = variacao < -TOLERANCIA_QUEDA

    quedas = ordenado.loc[caiu, ["location", "date", coluna]].copy()
    quedas["variacao"] = variacao[caiu]
    return quedas


def verificar_continuidade(medicoes):
    """Por país: primeira data, última data, linhas existentes e dias que faltam no meio."""
    resumo = medicoes.groupby("location")["date"].agg(["min", "max", "count"])
    resumo["dias_esperados"] = (resumo["max"] - resumo["min"]).dt.days + 1
    resumo["faltando"] = resumo["dias_esperados"] - resumo["count"]
    return resumo


def mortes_antes_de_casos(medicoes):
    """Países em que a primeira morte aparece antes do primeiro caso (inconsistência de origem)."""
    primeiro_caso = (
        medicoes[medicoes["new_cases_smoothed_per_million"] > 0].groupby("location")["date"].min()
    )
    primeira_morte = (
        medicoes[medicoes["new_deaths_smoothed_per_million"] > 0].groupby("location")["date"].min()
    )
    comparacao = pd.DataFrame({"primeiro_caso": primeiro_caso, "primeira_morte": primeira_morte})
    return comparacao[comparacao["primeira_morte"] < comparacao["primeiro_caso"]]


def validar(paises, medicoes):
    """
    Confere o que não pode estar errado antes de gravar no banco.
    Se algo falhar, levanta um erro listando todos os problemas encontrados.
    """
    problemas = []

    if paises["iso_code"].isna().any() or paises["iso_code"].duplicated().any():
        problemas.append("iso_code vazio ou repetido na tabela de países")

    if set(medicoes["location"]) != set(paises["location"]):
        problemas.append("países das medições diferem dos países selecionados")

    duplicadas = medicoes.duplicated(subset=["location", "date"]).sum()
    if duplicadas:
        problemas.append(f"{duplicadas} linhas repetidas para o mesmo país e data")

    if medicoes["date"].min() < pd.Timestamp(DATA_INICIO) or medicoes["date"].max() > pd.Timestamp(DATA_FIM):
        problemas.append("há datas fora do período definido")

    negativos = int((medicoes[COLUNAS_DIARIAS] < 0).sum().sum())
    if negativos:
        problemas.append(f"{negativos} valores negativos nas colunas diárias")

    vazios = int(medicoes[COLUNAS_DIARIAS + COLUNAS_ACUMULADAS].isna().sum().sum())
    if vazios:
        problemas.append(f"{vazios} valores vazios nas colunas numéricas")

    for coluna in COLUNAS_ACUMULADAS:
        maior_valor_ate_aqui = medicoes.groupby("location")[coluna].cummax()
        restantes = int(((medicoes[coluna] == 0) & (maior_valor_ate_aqui > 0)).sum())
        if restantes:
            problemas.append(f"{restantes} zeros indevidos restantes em {coluna}")

    faltando = verificar_continuidade(medicoes)["faltando"]
    if (faltando != 0).any():
        problemas.append("há dias faltando no meio da série de algum país")

    if problemas:
        raise ValueError("Validação falhou:\n- " + "\n- ".join(problemas))


def preparar_para_carga(paises, medicoes):
    """
    Separa os dados nas duas tabelas do banco.

    A tabela de medições perde `location` (o nome fica só na tabela de países, ligado por
    `iso_code`). A data vira texto no formato AAAA-MM-DD, que é como o SQLite guarda datas.
    """
    tabela_paises = paises[COLUNAS_PAISES].copy()

    tabela_medicoes = medicoes[COLUNAS_MEDICOES_BANCO].copy()
    tabela_medicoes["date"] = tabela_medicoes["date"].dt.strftime("%Y-%m-%d")
    return tabela_paises, tabela_medicoes

"""Dados sintéticos com a mesma estrutura do dataset do Kaggle."""
import numpy as np
import pandas as pd
import pytest

DATAS = pd.date_range("2020-01-01", "2022-03-31")


def _pais(nome, iso, continente, idh, populacao, inicio_casos, inicio_mortes, ajuste=None, pular=0):
    """Série crescente: zeros no começo e acumulados que só sobem, a menos que `ajuste` mexa neles."""
    i = np.arange(len(DATAS))
    novos_casos = np.where(i >= inicio_casos, (i - inicio_casos + 1) * 0.5, 0.0)
    novas_mortes = np.where(i >= inicio_mortes, (i - inicio_mortes + 1) * 0.05, 0.0)

    d = pd.DataFrame({
        "iso_code": iso,
        "continent": continente,
        "location": nome,
        "date": DATAS.strftime("%Y-%m-%d"),
        "new_cases_smoothed_per_million": np.round(novos_casos, 2),
        "total_cases_per_million": np.round(np.cumsum(novos_casos), 2),
        "new_deaths_smoothed_per_million": np.round(novas_mortes, 2),
        "total_deaths_per_million": np.round(np.cumsum(novas_mortes), 2),
        "human_development_index": idh,
        "population": populacao,
    })
    if ajuste:
        ajuste(d)
    return d.iloc[pular:].reset_index(drop=True)


def _zero_em_mortes(d):
    d.loc[300, "total_deaths_per_million"] = 0.0


def _revisao_em_casos(d):
    d.loc[200, "total_cases_per_million"] = d.loc[199, "total_cases_per_million"] - 5


@pytest.fixture
def df_origem():
    """
    Grupo esperado: Border, Brazil, Mexico e Peru.
    Fora do grupo: Norway (IDH alto), Tinyland (população pequena), Noidh (IDH 0)
    e World (agregado, continent vazio).
    """
    return pd.concat([
        _pais("Brazil", "BRA", "South America", 0.76, 215e6, 20, 40, pular=4),
        _pais("Peru", "PER", "South America", 0.77, 33e6, 20, 40, ajuste=_zero_em_mortes),
        _pais("Mexico", "MEX", "North America", 0.75, 127e6, 30, 10, ajuste=_revisao_em_casos),
        _pais("Border", "BOR", "Europe", 0.78, 10e6, 20, 40),
        _pais("Norway", "NOR", "Europe", 0.95, 5e6, 20, 40),
        _pais("Tinyland", "TIN", "Oceania", 0.76, 1e5, 20, 40),
        _pais("Noidh", "NID", "Africa", 0.0, 5e6, 20, 40),
        _pais("World", "OWID_WRL", np.nan, 0.76, 8e9, 20, 40),
    ], ignore_index=True)

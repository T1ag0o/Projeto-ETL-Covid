import pandas as pd
import pytest

from config import COLUNAS_MEDICOES
from transform import (
    corrigir_zeros_indevidos,
    listar_quedas,
    montar_medicoes,
    mortes_antes_de_casos,
    preparar_para_carga,
    selecionar_paises,
    validar,
    verificar_continuidade,
)


def medicoes_exemplo(pais="A", datas=None, **colunas):
    """Medições de um país, com as colunas numéricas informadas (as demais ficam zeradas)."""
    n = len(next(iter(colunas.values())))
    datas = datas if datas is not None else pd.date_range("2020-01-01", periods=n)
    base = {c: [0.0] * n for c in COLUNAS_MEDICOES if c not in ("iso_code", "location", "date")}
    base.update(colunas)
    return pd.DataFrame({"iso_code": pais, "location": pais, "date": datas, **base})


# ---------- seleção dos países ----------

def test_selecionar_paises_aplica_os_criterios(df_origem):
    paises, idh_referencia = selecionar_paises(df_origem)

    assert idh_referencia == 0.76
    assert paises["location"].tolist() == ["Border", "Brazil", "Mexico", "Peru"]


def test_pais_na_borda_da_margem_entra_gracas_ao_arredondamento(df_origem):
    # 0.78 - 0.76 vale 0.02000000000000002 no computador; sem round, Border ficaria de fora
    assert 0.78 - 0.76 > 0.02
    paises, _ = selecionar_paises(df_origem)
    assert "Border" in paises["location"].tolist()


def test_agregados_e_paises_sem_idh_ou_pequenos_ficam_de_fora(df_origem):
    paises, _ = selecionar_paises(df_origem)
    for fora in ["World", "Noidh", "Tinyland", "Norway"]:
        assert fora not in paises["location"].tolist()


def test_pais_de_referencia_ausente_gera_erro(df_origem):
    sem_brasil = df_origem[df_origem["location"] != "Brazil"]
    with pytest.raises(ValueError):
        selecionar_paises(sem_brasil)


# ---------- medições ----------

def test_montar_medicoes_filtra_periodo_e_converte_data(df_origem):
    paises, _ = selecionar_paises(df_origem)
    medicoes = montar_medicoes(df_origem, paises)

    assert pd.api.types.is_datetime64_any_dtype(medicoes["date"])
    assert medicoes["date"].min() >= pd.Timestamp("2020-01-01")
    assert medicoes["date"].max() == pd.Timestamp("2021-12-31")
    assert medicoes.shape[0] == 727 + 731 * 3  # Brazil começa 4 dias depois
    assert list(medicoes.columns) == COLUNAS_MEDICOES


# ---------- correção de zeros ----------

def test_zero_no_meio_do_acumulado_e_corrigido():
    m = medicoes_exemplo(total_deaths_per_million=[0, 0, 2, 5, 0, 5, 6])
    corrigido, registro = corrigir_zeros_indevidos(m)

    assert corrigido["total_deaths_per_million"].tolist() == [0, 0, 2, 5, 5, 5, 6]
    assert len(registro) == 1
    assert registro.iloc[0]["valor_original"] == 0
    assert registro.iloc[0]["valor_corrigido"] == 5


def test_zeros_do_inicio_da_serie_nao_sao_alterados():
    m = medicoes_exemplo(total_deaths_per_million=[0, 0, 0, 1, 2])
    corrigido, registro = corrigir_zeros_indevidos(m)

    assert corrigido["total_deaths_per_million"].tolist() == [0, 0, 0, 1, 2]
    assert registro.empty


def test_correcao_nao_mistura_paises():
    a = medicoes_exemplo("A", total_deaths_per_million=[1, 2, 3])
    b = medicoes_exemplo("B", total_deaths_per_million=[0, 0, 1])
    corrigido, registro = corrigir_zeros_indevidos(pd.concat([a, b], ignore_index=True))

    assert registro.empty
    assert corrigido["total_deaths_per_million"].tolist() == [1, 2, 3, 0, 0, 1]


# ---------- verificações ----------

def test_listar_quedas_encontra_queda_real():
    m = medicoes_exemplo(total_cases_per_million=[1.0, 2.0, 1.5, 3.0])
    quedas = listar_quedas(m, "total_cases_per_million")

    assert len(quedas) == 1
    assert quedas.iloc[0]["variacao"] == pytest.approx(-0.5)


def test_listar_quedas_ignora_ruido_de_arredondamento():
    m = medicoes_exemplo(total_cases_per_million=[1.0, 0.9995, 2.0])
    assert listar_quedas(m, "total_cases_per_million").empty


def test_continuidade_detecta_dia_faltando():
    datas = pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-04"])
    m = medicoes_exemplo(datas=datas, total_cases_per_million=[0.0, 1.0, 2.0])

    assert verificar_continuidade(m).loc["A", "faltando"] == 1


def test_serie_que_comeca_depois_nao_e_buraco():
    datas = pd.date_range("2020-01-05", periods=4)
    m = medicoes_exemplo(datas=datas, total_cases_per_million=[0.0, 1.0, 2.0, 3.0])

    assert verificar_continuidade(m).loc["A", "faltando"] == 0


def test_mortes_antes_de_casos():
    m = medicoes_exemplo(
        new_cases_smoothed_per_million=[0, 0, 1, 1],
        new_deaths_smoothed_per_million=[0, 1, 1, 1],
    )
    resultado = mortes_antes_de_casos(m)

    assert resultado.index.tolist() == ["A"]


# ---------- validação ----------

@pytest.fixture
def grupo_limpo(df_origem):
    paises, _ = selecionar_paises(df_origem)
    medicoes, _ = corrigir_zeros_indevidos(montar_medicoes(df_origem, paises))
    return paises, medicoes


def test_validar_aceita_dados_limpos(grupo_limpo):
    validar(*grupo_limpo)  # não levanta erro


def test_validar_recusa_zero_indevido_nao_corrigido(df_origem):
    paises, _ = selecionar_paises(df_origem)
    sem_correcao = montar_medicoes(df_origem, paises)
    with pytest.raises(ValueError, match="zeros indevidos"):
        validar(paises, sem_correcao)


def test_validar_recusa_duplicatas(grupo_limpo):
    paises, medicoes = grupo_limpo
    com_duplicata = pd.concat([medicoes, medicoes.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="repetidas"):
        validar(paises, com_duplicata)


def test_validar_recusa_valores_negativos(grupo_limpo):
    paises, medicoes = grupo_limpo
    medicoes = medicoes.copy()
    medicoes.loc[10, "new_cases_smoothed_per_million"] = -1.0
    with pytest.raises(ValueError, match="negativos"):
        validar(paises, medicoes)


def test_validar_recusa_dia_faltando(grupo_limpo):
    paises, medicoes = grupo_limpo
    com_buraco = medicoes.drop(index=100).reset_index(drop=True)
    with pytest.raises(ValueError, match="faltando"):
        validar(paises, com_buraco)


# ---------- preparação para a carga ----------

def test_preparar_para_carga_separa_as_tabelas(grupo_limpo):
    paises, medicoes = grupo_limpo
    tabela_paises, tabela_medicoes = preparar_para_carga(paises, medicoes)

    assert list(tabela_paises.columns) == [
        "iso_code", "location", "continent", "human_development_index", "population",
    ]
    assert "location" not in tabela_medicoes.columns
    assert tabela_medicoes["date"].str.fullmatch(r"\d{4}-\d{2}-\d{2}").all()
    assert len(tabela_medicoes) == len(medicoes)

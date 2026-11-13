import sqlite3

import pytest

from load import (
    abrir_conexao,
    carregar,
    conferir_banco,
    criar_esquema,
    verificar_esquema,
)
from transform import (
    corrigir_zeros_indevidos,
    montar_medicoes,
    preparar_para_carga,
    selecionar_paises,
)


@pytest.fixture
def tabelas(df_origem):
    paises, _ = selecionar_paises(df_origem)
    medicoes, _ = corrigir_zeros_indevidos(montar_medicoes(df_origem, paises))
    return preparar_para_carga(paises, medicoes)


@pytest.fixture
def conexao(tmp_path):
    conn = abrir_conexao(tmp_path / "teste.db")
    criar_esquema(conn)
    yield conn
    conn.close()


def contar(conn):
    paises = conn.execute("SELECT COUNT(*) FROM paises").fetchone()[0]
    medicoes = conn.execute("SELECT COUNT(*) FROM medicoes_diarias").fetchone()[0]
    return paises, medicoes


def test_criar_esquema_pode_ser_repetido(conexao):
    criar_esquema(conexao)
    verificar_esquema(conexao)


def test_carga_e_conferencia(conexao, tabelas):
    tabela_paises, tabela_medicoes = tabelas
    carregar(conexao, tabela_paises, tabela_medicoes)
    resumo = conferir_banco(conexao, tabela_paises, tabela_medicoes)

    assert resumo["paises"] == 4
    assert resumo["medicoes"] == len(tabela_medicoes)
    assert resumo["menor_data"] == "2020-01-01"
    assert resumo["maior_data"] == "2021-12-31"


def test_rodar_duas_vezes_nao_duplica(conexao, tabelas):
    tabela_paises, tabela_medicoes = tabelas
    carregar(conexao, tabela_paises, tabela_medicoes)
    depois_da_primeira = contar(conexao)

    carregar(conexao, tabela_paises, tabela_medicoes)

    assert contar(conexao) == depois_da_primeira


def test_carga_repetida_atualiza_valor_alterado(conexao, tabelas):
    tabela_paises, tabela_medicoes = tabelas
    carregar(conexao, tabela_paises, tabela_medicoes)
    antes = contar(conexao)

    alterada = tabela_medicoes.copy()
    alterada.loc[0, "total_cases_per_million"] = 999.0
    carregar(conexao, tabela_paises, alterada)

    iso, data = alterada.loc[0, "iso_code"], alterada.loc[0, "date"]
    valor = conexao.execute(
        "SELECT total_cases_per_million FROM medicoes_diarias WHERE iso_code = ? AND date = ?",
        (iso, data),
    ).fetchone()[0]
    assert valor == 999.0
    assert contar(conexao) == antes


def test_tipos_gravados_sao_numeros_e_nao_binarios(conexao, tabelas):
    carregar(conexao, *tabelas)

    assert conexao.execute("SELECT DISTINCT typeof(population) FROM paises").fetchall() == [("integer",)]
    assert conexao.execute(
        "SELECT DISTINCT typeof(total_cases_per_million) FROM medicoes_diarias"
    ).fetchall() == [("real",)]


def test_chave_estrangeira_recusa_pais_inexistente(conexao):
    with pytest.raises(sqlite3.IntegrityError):
        conexao.execute(
            "INSERT INTO medicoes_diarias VALUES ('XXX', '2020-01-01', 0, 0, 0, 0)"
        )


def test_check_recusa_populacao_negativa(conexao):
    with pytest.raises(sqlite3.IntegrityError):
        conexao.execute("INSERT INTO paises VALUES ('XXX', 'Xland', 'Asia', 0.7, -5)")


def test_check_recusa_data_fora_do_formato(conexao):
    conexao.execute("INSERT INTO paises VALUES ('XXX', 'Xland', 'Asia', 0.7, 100)")
    with pytest.raises(sqlite3.IntegrityError):
        conexao.execute("INSERT INTO medicoes_diarias VALUES ('XXX', '01/01/2020', 0, 0, 0, 0)")


def test_chave_primaria_recusa_linha_repetida(conexao):
    conexao.execute("INSERT INTO paises VALUES ('XXX', 'Xland', 'Asia', 0.7, 100)")
    conexao.execute("INSERT INTO medicoes_diarias VALUES ('XXX', '2020-01-01', 0, 0, 0, 0)")
    with pytest.raises(sqlite3.IntegrityError):
        conexao.execute("INSERT INTO medicoes_diarias VALUES ('XXX', '2020-01-01', 1, 1, 1, 1)")


def test_carga_falha_inteira_se_uma_medicao_for_invalida(conexao, tabelas):
    tabela_paises, tabela_medicoes = tabelas
    invalida = tabela_medicoes.copy()
    invalida.loc[len(invalida) - 1, "new_cases_smoothed_per_million"] = -1.0

    with pytest.raises(sqlite3.IntegrityError):
        carregar(conexao, tabela_paises, invalida)

    assert contar(conexao) == (0, 0)  # nem os países foram gravados


def test_conferir_banco_detecta_linhas_que_nao_estao_nos_dados_atuais(conexao, tabelas):
    tabela_paises, tabela_medicoes = tabelas
    carregar(conexao, tabela_paises, tabela_medicoes)

    menos_paises = tabela_paises.iloc[:3]
    menos_medicoes = tabela_medicoes[tabela_medicoes["iso_code"].isin(menos_paises["iso_code"])]
    with pytest.raises(ValueError, match="contagens"):
        conferir_banco(conexao, menos_paises, menos_medicoes)


def test_esquema_antigo_e_detectado(tmp_path):
    conn = abrir_conexao(tmp_path / "antigo.db")
    conn.execute("CREATE TABLE paises (iso_code TEXT PRIMARY KEY, location TEXT NOT NULL, "
                 "continent TEXT NOT NULL, human_development_index REAL NOT NULL, population INTEGER NOT NULL)")
    conn.execute("CREATE TABLE medicoes_diarias (iso_code TEXT NOT NULL, date TEXT NOT NULL, "
                 "new_cases_smoothed_per_million REAL NOT NULL, new_deaths_smoothed_per_million REAL NOT NULL, "
                 "total_cases_per_million REAL NOT NULL, total_deaths_per_million REAL NOT NULL, "
                 "PRIMARY KEY (iso_code, date), "
                 "FOREIGN KEY (iso_code) REFERENCES tabela_paises(iso_code) ON DELETE CASCADE)")
    criar_esquema(conn)  # não altera tabelas que já existem

    with pytest.raises(RuntimeError, match="--recriar"):
        verificar_esquema(conn)
    conn.close()

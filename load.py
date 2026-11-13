"""Carga: cria o banco SQLite, grava os dados sem duplicar e confere o resultado."""
import sqlite3
from pathlib import Path

from config import (
    COLUNAS_ACUMULADAS,
    COLUNAS_DIARIAS,
    COLUNAS_MEDICOES_BANCO,
    COLUNAS_PAISES,
)

CRIAR_PAISES = """
CREATE TABLE IF NOT EXISTS paises (
    iso_code TEXT PRIMARY KEY,
    location TEXT NOT NULL,
    continent TEXT NOT NULL,
    human_development_index REAL NOT NULL
        CHECK (human_development_index > 0 AND human_development_index <= 1),
    population INTEGER NOT NULL CHECK (population > 0)
)
"""

CRIAR_MEDICOES = """
CREATE TABLE IF NOT EXISTS medicoes_diarias (
    iso_code TEXT NOT NULL,
    date TEXT NOT NULL
        CHECK (date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    new_cases_smoothed_per_million REAL NOT NULL CHECK (new_cases_smoothed_per_million >= 0),
    new_deaths_smoothed_per_million REAL NOT NULL CHECK (new_deaths_smoothed_per_million >= 0),
    total_cases_per_million REAL NOT NULL CHECK (total_cases_per_million >= 0),
    total_deaths_per_million REAL NOT NULL CHECK (total_deaths_per_million >= 0),
    PRIMARY KEY (iso_code, date),
    FOREIGN KEY (iso_code) REFERENCES paises(iso_code) ON DELETE CASCADE
)
"""


def abrir_conexao(caminho):
    """Abre o banco (criando a pasta, se preciso) e liga as chaves estrangeiras."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conexao = sqlite3.connect(caminho)
    # No SQLite, as chaves estrangeiras vêm desligadas e precisam ser ligadas a cada conexão.
    conexao.execute("PRAGMA foreign_keys = ON")
    return conexao


def criar_esquema(conexao):
    """Cria as tabelas se ainda não existirem. Pode ser chamada quantas vezes quiser."""
    with conexao:
        conexao.execute(CRIAR_PAISES)
        conexao.execute(CRIAR_MEDICOES)


def verificar_esquema(conexao):
    """
    `CREATE TABLE IF NOT EXISTS` não altera uma tabela que já existe. Se o arquivo .db foi criado
    por uma versão antiga do esquema, esta função avisa em vez de deixar o erro aparecer só na carga.
    """
    colunas_paises = [linha[1] for linha in conexao.execute("PRAGMA table_info(paises)")]
    colunas_medicoes = [linha[1] for linha in conexao.execute("PRAGMA table_info(medicoes_diarias)")]
    # Linhas de foreign_key_list: (id, seq, tabela_referenciada, coluna, coluna_referenciada, ...)
    referencias = {linha[2] for linha in conexao.execute("PRAGMA foreign_key_list(medicoes_diarias)")}

    atualizado = (
        colunas_paises == COLUNAS_PAISES
        and colunas_medicoes == COLUNAS_MEDICOES_BANCO
        and referencias == {"paises"}
    )
    if not atualizado:
        raise RuntimeError(
            "O banco existente tem um esquema diferente do atual. "
            "Rode com --recriar para apagar o arquivo .db e criá-lo de novo."
        )


def _linhas(tabela, colunas):
    """
    Converte o DataFrame em listas com tipos nativos do Python (int, float, str).
    Tipos do NumPy podem ser gravados pelo sqlite3 como dado binário em vez de número.
    """
    return tabela[colunas].astype(object).values.tolist()


def _comando_upsert(tabela, colunas, chave):
    """
    Monta o INSERT com ON CONFLICT (upsert): insere a linha nova e, se a chave já existir,
    atualiza as demais colunas com os valores novos.
    """
    marcadores = ", ".join("?" for _ in colunas)
    atualizar = ", ".join(f"{c} = excluded.{c}" for c in colunas if c not in chave)
    return (
        f"INSERT INTO {tabela} ({', '.join(colunas)}) VALUES ({marcadores}) "
        f"ON CONFLICT ({', '.join(chave)}) DO UPDATE SET {atualizar}"
    )


def carregar(conexao, tabela_paises, tabela_medicoes):
    """
    Grava países e medições em uma única transação: se algo falhar, nada é gravado.
    Os países vão primeiro, porque as medições dependem deles (chave estrangeira).
    Rodar de novo com os mesmos dados não duplica nada.
    """
    paises = tabela_paises.copy()
    paises["population"] = paises["population"].round().astype("int64")

    comando_paises = _comando_upsert("paises", COLUNAS_PAISES, chave=["iso_code"])
    comando_medicoes = _comando_upsert(
        "medicoes_diarias", COLUNAS_MEDICOES_BANCO, chave=["iso_code", "date"]
    )

    with conexao:
        conexao.executemany(comando_paises, _linhas(paises, COLUNAS_PAISES))
        conexao.executemany(comando_medicoes, _linhas(tabela_medicoes, COLUNAS_MEDICOES_BANCO))


def conferir_banco(conexao, tabela_paises, tabela_medicoes):
    """
    Confere o banco depois da carga e devolve um resumo.
    Levanta erro se as contagens não batem, se há violação de chave estrangeira
    ou se algum valor foi gravado com o tipo errado.
    """
    consulta = conexao.execute
    resumo = {
        "paises": consulta("SELECT COUNT(*) FROM paises").fetchone()[0],
        "medicoes": consulta("SELECT COUNT(*) FROM medicoes_diarias").fetchone()[0],
        "menor_data": consulta("SELECT MIN(date) FROM medicoes_diarias").fetchone()[0],
        "maior_data": consulta("SELECT MAX(date) FROM medicoes_diarias").fetchone()[0],
        "linhas_por_pais": consulta(
            "SELECT p.location, COUNT(*) FROM medicoes_diarias m "
            "JOIN paises p ON p.iso_code = m.iso_code GROUP BY p.location ORDER BY p.location"
        ).fetchall(),
    }

    problemas = []

    if resumo["paises"] != len(tabela_paises) or resumo["medicoes"] != len(tabela_medicoes):
        problemas.append(
            f"contagens diferentes dos dados atuais: banco tem {resumo['paises']} países e "
            f"{resumo['medicoes']} medições; esperado {len(tabela_paises)} e {len(tabela_medicoes)}. "
            "Se a margem de IDH ou o período mudou, rode com --recriar"
        )

    violacoes = consulta("PRAGMA foreign_key_check").fetchall()
    if violacoes:
        problemas.append(f"{len(violacoes)} violações de chave estrangeira")

    tipos_esperados = {
        "paises": {"population": "integer", "human_development_index": "real"},
        "medicoes_diarias": {c: "real" for c in COLUNAS_DIARIAS + COLUNAS_ACUMULADAS},
    }
    for tabela, colunas in tipos_esperados.items():
        for coluna, esperado in colunas.items():
            tipos = {linha[0] for linha in consulta(f"SELECT DISTINCT typeof({coluna}) FROM {tabela}")}
            if tipos - {esperado}:
                problemas.append(f"{tabela}.{coluna} tem valores do tipo {sorted(tipos)}, esperado {esperado}")

    if problemas:
        raise ValueError("Conferência do banco falhou:\n- " + "\n- ".join(problemas))
    return resumo

"""Executa o ETL completo: extrai, transforma, valida e carrega no SQLite.

Uso:
    python main.py              roda o ETL (pode ser repetido sem duplicar dados)
    python main.py --recriar    apaga o banco antes e cria tudo de novo
"""
import argparse
import logging
from contextlib import closing
from pathlib import Path

from config import CAMINHO_BANCO, COLUNAS_ACUMULADAS, PAIS_REFERENCIA
from extract import extrair
from load import abrir_conexao, carregar, conferir_banco, criar_esquema, verificar_esquema
from transform import (
    corrigir_zeros_indevidos,
    listar_quedas,
    montar_medicoes,
    mortes_antes_de_casos,
    preparar_para_carga,
    selecionar_paises,
    validar,
    verificar_valores_fixos,
)

logger = logging.getLogger("etl_covid")


def executar(caminho_banco=CAMINHO_BANCO, recriar=False):
    caminho_banco = Path(caminho_banco)
    if recriar and caminho_banco.exists():
        caminho_banco.unlink()
        logger.info("Banco anterior removido: %s", caminho_banco)

    # Extração
    logger.info("Extraindo dados do Kaggle")
    df = extrair()
    logger.info("Dados extraídos: %d linhas e %d colunas", *df.shape)

    # Transformação
    paises, idh_referencia = selecionar_paises(df)
    logger.info(
        "IDH de %s: %s | países no grupo (incluindo %s): %d",
        PAIS_REFERENCIA, idh_referencia, PAIS_REFERENCIA, len(paises),
    )
    logger.info("Países: %s", ", ".join(paises["location"]))

    variam = verificar_valores_fixos(df, paises)
    if not variam.empty:
        logger.warning("IDH ou população variam entre linhas em: %s", ", ".join(variam.index))

    medicoes_brutas = montar_medicoes(df, paises)
    logger.info("Medições no período: %d linhas", len(medicoes_brutas))

    medicoes, correcoes = corrigir_zeros_indevidos(medicoes_brutas)
    for _, c in correcoes.iterrows():
        logger.info(
            "Zero indevido corrigido: %s em %s (%s): %s -> %s",
            c["location"], c["date"].date(), c["coluna"], c["valor_original"], c["valor_corrigido"],
        )

    for coluna in COLUNAS_ACUMULADAS:
        for _, q in listar_quedas(medicoes, coluna).iterrows():
            logger.info(
                "Queda mantida (revisão na origem): %s em %s (%s): %s",
                q["location"], q["date"].date(), coluna, q["variacao"],
            )

    for local, linha in mortes_antes_de_casos(medicoes).iterrows():
        logger.warning(
            "Inconsistência na origem: %s tem a primeira morte (%s) antes do primeiro caso (%s)",
            local, linha["primeira_morte"].date(), linha["primeiro_caso"].date(),
        )

    validar(paises, medicoes)
    logger.info("Validação OK")

    tabela_paises, tabela_medicoes = preparar_para_carga(paises, medicoes)

    # Carga
    with closing(abrir_conexao(caminho_banco)) as conexao:
        criar_esquema(conexao)
        verificar_esquema(conexao)
        carregar(conexao, tabela_paises, tabela_medicoes)
        resumo = conferir_banco(conexao, tabela_paises, tabela_medicoes)

    logger.info(
        "Banco conferido: %d países, %d medições, de %s a %s",
        resumo["paises"], resumo["medicoes"], resumo["menor_data"], resumo["maior_data"],
    )
    return resumo


def main():
    parser = argparse.ArgumentParser(description="ETL de Covid-19 em países com IDH próximo ao do Brasil")
    parser.add_argument("--recriar", action="store_true", help="apaga o banco e cria tudo de novo")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    executar(recriar=args.recriar)


if __name__ == "__main__":
    main()

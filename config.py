"""Parâmetros do projeto. Tudo que é decisão de análise fica aqui."""
from pathlib import Path

DATASET = "aliahmadmphil/global-covid-19-pandemic-full-data-2020-2026"
ARQUIVO = "COVID19_Complete_Dataset/covid19_complete_20260829.csv"

PAIS_REFERENCIA = "Brazil"
MARGEM_IDH = 0.02
POPULACAO_MINIMA = 1_000_000
DATA_INICIO = "2020-01-01"
DATA_FIM = "2021-12-31"

# Colunas que descrevem o país (valores que não mudam ao longo dos dias)
COLUNAS_PAISES = [
    "iso_code",
    "location",
    "continent",
    "human_development_index",
    "population",
]

# Valores do dia (médias suavizadas): não podem ser negativos
COLUNAS_DIARIAS = ["new_cases_smoothed_per_million", "new_deaths_smoothed_per_million"]

# Acumulados: só podem subir ou ficar iguais
COLUNAS_ACUMULADAS = ["total_cases_per_million", "total_deaths_per_million"]

# Colunas das medições durante a transformação (ainda com o nome do país)
COLUNAS_MEDICOES = ["iso_code", "location", "date"] + COLUNAS_DIARIAS + COLUNAS_ACUMULADAS

# Colunas da tabela de medições no banco (o nome do país fica só na tabela de países)
COLUNAS_MEDICOES_BANCO = ["iso_code", "date"] + COLUNAS_DIARIAS + COLUNAS_ACUMULADAS

# Quedas menores que isso em um acumulado são tratadas como ruído de arredondamento
TOLERANCIA_QUEDA = 0.001

PASTA_PROJETO = Path(__file__).resolve().parent
CAMINHO_BANCO = PASTA_PROJETO / "data" / "banco_etl_covid.db"

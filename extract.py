"""Extração: lê o dataset do Kaggle."""
import kagglehub
from kagglehub import KaggleDatasetAdapter

from config import ARQUIVO, DATASET


def extrair():
    """Lê o CSV do Kaggle (usa o cache local se já tiver sido baixado)."""
    return kagglehub.dataset_load(KaggleDatasetAdapter.PANDAS, DATASET, ARQUIVO)

"""
model_lock.py — Serializa o CARREGAMENTO de modelos (Transformers/Docling) entre threads.

Durante o from_pretrained, o Transformers inicializa pesos num dispositivo "meta" usando um
contexto que altera o PyTorch globalmente. Dois carregamentos simultâneos em threads diferentes
(ex.: aquecimento do reranker + worker do Docling) se atrapalham e falham com
"Cannot copy out of meta tensor". A inferência em si pode rodar em paralelo; só a carga é serial.
"""

import threading

LOAD_LOCK = threading.RLock()

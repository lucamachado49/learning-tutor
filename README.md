# 🌍 AI Learning Tutor

> Tutor inteligente de idiomas com chat por **texto e voz**, sem internet e sem APIs pagas.  
> Stack: **React + FastAPI** · **Whisper** (STT) · **Ollama** (LLM) · **Piper TTS** (TTS)

---

## 📦 Pré-requisitos de Sistema

| Requisito | Versão Mínima | Notas |
|-----------|--------------|-------|
| Python | 3.10+ | 3.11 recomendado |
| Ollama | 0.3+ | [ollama.com/download](https://ollama.com/download) |
| CUDA *(opcional)* | 11.8+ | Para aceleração GPU no Whisper |
| RAM | 8 GB | 16 GB recomendado para modelos 7B |
| Espaço em disco | ~10 GB | Modelos LLM + TTS + Whisper |

---

## 🚀 Instalação Passo a Passo

### Passo 1 — Clone / Extraia o projeto

```powershell
# Navegue até a pasta do projeto
cd C:\Users\Lucas\Downloads\language
```

### Passo 2 — Crie e ative o ambiente virtual

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

> **Nota Windows:** Se der erro de política de execução, rode primeiro:  
> `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

### Passo 3 — Instale as dependências Python

```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

> **GPU (NVIDIA):** Para usar CUDA com o Whisper, instale o PyTorch com CUDA antes:
> ```powershell
> pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
> ```

### Passo 4 — Instale e configure o Ollama

1. Baixe o instalador em **[ollama.com/download](https://ollama.com/download)**
2. Após instalar, abra um **novo terminal** e inicie o servidor:

```powershell
ollama serve
```

3. Em outro terminal, baixe o modelo de linguagem:

```powershell
# Modelo principal (recomendado — ~4.7 GB)
ollama pull qwen2.5:7b

# Alternativa menor (~2 GB, menos preciso)
ollama pull llama3.2:3b
```

### Passo 5 — Baixe os modelos de voz (Piper TTS)

```powershell
# Todos os idiomas (Espanhol, Inglês, Italiano, Russo)
python download_models.py

# Ou apenas um idioma específico:
python download_models.py --lang es   # Espanhol
python download_models.py --lang en   # Inglês
python download_models.py --lang it   # Italiano
python download_models.py --lang ru   # Russo

# Verificar quais modelos já estão instalados:
python download_models.py --check
```

> Os modelos são salvos em `./models/piper/<lang>/` (~50–150 MB por idioma)

### Passo 5b — Voz principal (Kokoro) e chaves gratuitas

```powershell
python download_models.py --kokoro   # voz natural en/es/pt (~340 MB)
copy .env.example .env               # depois preencha as chaves
```

No `.env`, adicione chaves gratuitas (opcional, mas recomendado para domínios técnicos):
- `GEMINI_API_KEY` — https://aistudio.google.com/apikey
- `GROQ_API_KEY` — https://console.groq.com/keys

Sem chaves, o app usa o Ollama local. No modo "Automático" a ordem é Gemini → Groq → Ollama.

### Domínios e modos
Inglês · Espanhol (níveis CEFR) · Matemática p/ ML · ML Engineering · CTO Skills.
Modos: conversação livre, roleplay, aula guiada e quiz. O tutor guarda seus erros
recorrentes ("Memória" em Configurações) e os retoma nas próximas sessões.

### Passo 6 — Execute a aplicação

Certifique-se de que o **Ollama está rodando** (`ollama serve`) e então:

```powershell
# Terminal 1 — backend
.\start_backend.ps1

# Terminal 2 — frontend
cd frontend
npm install
npm run dev
```

Abra `http://localhost:5173` no navegador 🎉

---

## ⚡ Setup Automático (Alternativa)

Para Windows, um script PowerShell faz tudo automaticamente:

```powershell
.\setup.ps1
```

Flags disponíveis:
```powershell
.\setup.ps1 -SkipOllama    # pula instalação do Ollama
.\setup.ps1 -SkipModels    # pula download dos modelos Piper
```

---

## 🗂️ Estrutura do Projeto

```
language/
├── backend/main.py         # API FastAPI (chat, STT, TTS)
├── frontend/               # Interface React (Vite)
├── download_models.py      # Gerenciador de modelos Piper TTS
├── requirements.txt        # Dependências Python
├── setup.ps1               # Setup automático (Windows)
├── README.md               # Esta documentação
└── models/
    └── piper/
        ├── es/             # Modelos Espanhol
        ├── en/             # Modelos Inglês
        ├── it/             # Modelos Italiano
        └── ru/             # Modelos Russo
```

---

## 🎮 Funcionalidades

### Idiomas Suportados
| Idioma | Código | Voz Piper |
|--------|--------|-----------|
| Espanhol 🇪🇸 | `es` | es_ES-davefx-medium |
| Inglês 🇺🇸 | `en` | en_US-lessac-medium |
| Italiano 🇮🇹 | `it` | it_IT-riccardo-x_low |
| Russo 🇷🇺 | `ru` | ru_RU-denis-medium |

### Modos de Prática
- **💬 Conversação Livre** — Bate-papo e roleplay em situações do dia a dia
- **📝 Gramática & Exercícios** — Exercícios interativos com feedback pedagógico
- **📖 Leitura & Vocabulário** — Textos curtos com glossário e perguntas de interpretação

### Níveis CEFR
`A1` · `A2` · `B1` · `B2` · `C1` · `C2`

---

## 🔧 Solução de Problemas

### ❌ "Ollama não detectado"
```powershell
# Verifique se o Ollama está rodando:
ollama serve

# Teste a conexão:
curl http://localhost:11434/api/tags
```

### ❌ Erro ao carregar Whisper / CUDA
```
# Use apenas CPU (mais lento, mas funciona em qualquer máquina):
# O app detecta automaticamente e usa CPU como fallback.
# Para forçar CPU, instale sem CUDA:
pip install faster-whisper
```

### ❌ Modelo de voz não encontrado
```powershell
# Verifique os modelos instalados:
python download_models.py --check

# Baixe o modelo necessário:
python download_models.py --lang es
```

### ❌ Microfone não aparece
```
O componente de microfone requer acesso ao microfone pelo navegador.
- Acesse em http://localhost:5173 (não 127.0.0.1)
- Permita o acesso ao microfone quando o navegador solicitar
```

### ❌ Piper TTS não instala (piper-tts)
```powershell
# Em alguns sistemas é necessário instalar via pip com extras:
pip install piper-tts

# Alternativa: use o executável piper diretamente
# Baixe em: https://github.com/rhasspy/piper/releases
# E adicione ao PATH do sistema
```

---

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────────┐
│                   React UI                           │
│  ┌──────────┐  ┌────────────┐  ┌─────────────────┐  │
│  │ Sidebar  │  │  Chat Area  │  │  Audio Input    │  │
│  │ Config   │  │  Messages  │  │  (Mic Recorder) │  │
│  └──────────┘  └────────────┘  └─────────────────┘  │
└─────────────────┬──────────────────┬────────────────┘
                  │                  │
        ┌─────────▼────┐    ┌────────▼──────────┐
        │   LLM Layer  │    │    STT Layer       │
        │   (Ollama)   │    │  (faster-whisper)  │
        │  qwen2.5:7b  │    │  small/base model  │
        └─────────┬────┘    └────────────────────┘
                  │
        ┌─────────▼────┐
        │   TTS Layer  │
        │  (Piper TTS) │
        │  ONNX Neural │
        └──────────────┘
```

---

## 📄 Licença

MIT — Livre para uso pessoal e educacional.

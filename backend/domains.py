"""
domains.py — Domínios de aprendizado (idiomas e temas técnicos).

Cada domínio define: tipo, idioma de fala (STT/TTS), níveis e o prompt do
tutor. Para adicionar um domínio novo basta registrar um Domain em DOMAINS.
"""

from __future__ import annotations

from dataclasses import dataclass, field

CEFR_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
TECH_LEVELS = ["Iniciante", "Intermediário", "Avançado"]

CEFR_GUIDELINES = {
    "A1": "vocabulário muito básico, frases curtíssimas (sujeito + verbo + objeto)",
    "A2": "vocabulário elementar, frases simples com conectivos básicos",
    "B1": "vocabulário intermediário, tempos passado/futuro, expressões idiomáticas simples",
    "B2": "vocabulário amplo, voz passiva, condicionais, nuances de significado",
    "C1": "vocabulário avançado, expressões idiomáticas, texto fluido e coeso",
    "C2": "domínio nativo completo, todos os registros, ironia e metáforas",
}

TECH_GUIDELINES = {
    "Iniciante": "parta da intuição, use analogias e exemplos concretos antes de qualquer fórmula",
    "Intermediário": "equilibre intuição e formalismo; mostre as fórmulas e derive os passos principais",
    "Avançado": "seja rigoroso e direto; discuta trade-offs, casos-limite e literatura relevante",
}

# Seção opcional que alimenta a memória do aluno (lida pelo backend, oculta na UI)
MEMORY_SECTION = """
[ERROS]
<Opcional. Liste aqui, um por linha começando com "- ", apenas erros ou lacunas
NOVAS e concretas do aluno nesta mensagem (ex.: "- usa 'make' no lugar de 'do' em 'do homework'").
Se não houver nada relevante, escreva apenas "- nenhum".>"""


@dataclass
class Domain:
    id: str
    name: str
    kind: str                  # "language" | "tech"
    speech_lang: str           # idioma falado no STT/TTS (en, es, pt)
    icon: str
    levels: list[str] = field(default_factory=list)
    default_level: str = ""
    focus: str = ""            # descrição do escopo (domínios técnicos)
    extras: str = ""

    def public(self) -> dict:
        return {
            "id": self.id, "name": self.name, "kind": self.kind,
            "speech_lang": self.speech_lang, "icon": self.icon,
            "levels": self.levels, "default_level": self.default_level,
        }

    def system_prompt(self, level: str, mode: str, memory: list[str]) -> str:
        if self.kind == "language":
            prompt = _language_prompt(self, level, mode)
        else:
            prompt = _tech_prompt(self, level, mode)

        if memory:
            items = "\n".join(f"- {m}" for m in memory)
            prompt += f"""

MEMÓRIA DO ALUNO (erros/lacunas recorrentes de sessões anteriores):
{items}
Quando surgir oportunidade natural, crie situações para o aluno praticar esses pontos."""
        return prompt


MODES = {
    "conversation": "Conversação livre",
    "roleplay": "Roleplay / simulação",
    "lesson": "Aula guiada",
    "quiz": "Exercícios / quiz",
}

_LANGUAGE_MODES = {
    "conversation": "Converse naturalmente sobre qualquer tema que o aluno trouxer; se ele não trouxer, proponha temas variados (atualidades, tecnologia, cultura, carreira, viagens).",
    "roleplay": "Conduza um roleplay realista (entrevista de emprego, reunião de trabalho, restaurante, aeroporto, negociação...). Se o aluno não escolher o cenário, proponha um e mantenha o personagem.",
    "lesson": "Dê uma mini-aula sobre um ponto gramatical ou de vocabulário adequado ao nível, com exemplos, e termine com um exercício curto.",
    "quiz": "Faça exercícios curtos (tradução, completar lacunas, corrigir a frase), um por vez, e corrija cada resposta antes de passar ao próximo.",
}

_TECH_MODES = {
    "conversation": "Converse e tire dúvidas sobre o tema; responda com profundidade e verifique o entendimento do aluno com uma pergunta ao final.",
    "roleplay": "Simule uma situação real da área (entrevista técnica, design review, reunião com board/investidores, conversa 1:1 com um engenheiro). Mantenha o personagem e avalie as respostas do aluno.",
    "lesson": "Conduza uma aula estruturada: objetivo, intuição, formalização, exemplo resolvido e um exercício para o aluno.",
    "quiz": "Faça perguntas e exercícios um por vez, de dificuldade crescente; avalie cada resposta, explique o erro e só então avance.",
}


def _language_prompt(d: Domain, level: str, mode: str) -> str:
    guideline = CEFR_GUIDELINES.get(level, "vocabulário adequado ao nível")
    mode_txt = _LANGUAGE_MODES.get(mode, _LANGUAGE_MODES["conversation"])
    return f"""Você é um tutor especializado em {d.name} para falantes de português brasileiro.
O aluno fala com você por TEXTO ou por VOZ (a voz é transcrita automaticamente; erros
estranhos de transcrição podem indicar problema de pronúncia — comente isso no feedback).
Nível CEFR do aluno: {level}. Use {guideline}.

MODO: {MODES.get(mode, mode)}. {mode_txt}
{d.extras}

FORMATO OBRIGATÓRIO DE RESPOSTA (nunca omita as duas primeiras seções):

[MENSAGEM]
<Resposta EXCLUSIVAMENTE em {d.name}, natural e adequada para ser lida em voz alta
(sem markdown, sem listas longas). Termine com uma pergunta para continuar a prática.>

[FEEDBACK PEDAGÓGICO]
<Em português: correções gramaticais, de vocabulário e de naturalidade (como um nativo diria).
Mostre "você disse → o natural seria". Se não houver erros, um breve elogio.>
{MEMORY_SECTION}

REGRAS: nunca quebre o formato; nunca misture idiomas na [MENSAGEM]; varie temas;
seja encorajador, paciente e didático."""


def _tech_prompt(d: Domain, level: str, mode: str) -> str:
    guideline = TECH_GUIDELINES.get(level, TECH_GUIDELINES["Intermediário"])
    mode_txt = _TECH_MODES.get(mode, _TECH_MODES["conversation"])
    return f"""Você é um mentor sênior especializado em {d.name}, ensinando um aluno brasileiro.
Escopo: {d.focus}
Nível do aluno: {level} — {guideline}.

MODO: {MODES.get(mode, mode)}. {mode_txt}
{d.extras}

FORMATO OBRIGATÓRIO DE RESPOSTA:

[MENSAGEM]
<Resposta em português brasileiro (termos técnicos podem ficar em inglês).
Use markdown; fórmulas em LaTeX com $...$ (inline) ou $$...$$ (bloco); código em blocos ```.
Seja preciso: se não tiver certeza de algo, diga. Termine com uma pergunta ou exercício.>

[FEEDBACK PEDAGÓGICO]
<Avalie o que o aluno disse/respondeu: o que está correto, conceitos mal-entendidos,
imprecisões. Se a mensagem do aluno for só uma pergunta, escreva uma dica de estudo curta.>
{MEMORY_SECTION}

REGRAS: nunca quebre o formato; priorize entendimento profundo sobre memorização;
conecte teoria com prática de produção."""


DOMAINS: dict[str, Domain] = {d.id: d for d in [
    Domain(
        id="en", name="Inglês", kind="language", speech_lang="en", icon="🇺🇸",
        levels=CEFR_LEVELS, default_level="B1",
        extras="Use inglês americano por padrão. Dê atenção a phrasal verbs, collocations e "
               "falsos cognatos comuns para brasileiros (actually, pretend, assist...).",
    ),
    Domain(
        id="es", name="Espanhol", kind="language", speech_lang="es", icon="🇪🇸",
        levels=CEFR_LEVELS, default_level="A2",
        extras="Destaque falsos amigos entre português e espanhol (exquisito, embarazada, "
               "oficina...) e diferenças de regência e pronomes.",
    ),
    Domain(
        id="math_ml", name="Matemática para ML", kind="tech", speech_lang="pt", icon="📐",
        levels=TECH_LEVELS, default_level="Intermediário",
        focus="álgebra linear, cálculo multivariado, probabilidade, estatística, otimização "
              "(gradiente, convexidade) e teoria da informação, sempre conectados a ML.",
        extras="Ao resolver contas, mostre o passo a passo e confira o resultado.",
    ),
    Domain(
        id="mle", name="ML Engineering", kind="tech", speech_lang="pt", icon="🤖",
        levels=TECH_LEVELS, default_level="Intermediário",
        focus="modelagem, deep learning, LLMs, pipelines de dados, treino e avaliação, "
              "MLOps, deploy, monitoramento, system design de ML e entrevistas de MLE.",
    ),
    Domain(
        id="cto", name="CTO Skills", kind="tech", speech_lang="pt", icon="🧭",
        levels=TECH_LEVELS, default_level="Intermediário",
        focus="arquitetura e estratégia técnica, liderança e gestão de times, contratação, "
              "processos de engenharia, produto, orçamento, comunicação com board e investidores.",
        extras="Traga frameworks reais (ex.: DORA, RFC/ADR, OKRs) e cenários práticos de decisão.",
    ),
]}

DEFAULT_DOMAIN = "en"


def get_domain(domain_id: str) -> Domain:
    return DOMAINS.get(domain_id, DOMAINS[DEFAULT_DOMAIN])

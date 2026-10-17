"""
review.py — Revisão espaçada (estilo SM-2) e progresso.

De onde vêm os itens de revisão (criados automaticamente):
  • erros recorrentes que o tutor anotou            → kind "mistake"
  • conceitos do mapa de domínio com nota < 80      → kind "concept"
  • sons de pronúncia com nota < 80 ("pronúncia /θ/") → kind "sound"

Cada revisão recebe uma qualidade: 0 = errou, 1 = difícil, 2 = acertou.
Acertos aumentam o intervalo (1 → 3 → ~8 → ~20 dias…); erros trazem o item de volta amanhã.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import ConceptMastery, MasteryHistory, Mistake, ReviewItem, ReviewLog, utcnow

WEAK_SCORE = 80          # conceitos/sons abaixo disso entram na revisão
MIN_EASE = 1.3
SOUND_RE = re.compile(r"^pronúncia /(.+)/$")


def normalize(text: str) -> str:
    return " ".join(text.lower().split())[:200]


# ---------------------------------------------------------------------------
# Agendamento (função pura)
# ---------------------------------------------------------------------------
@dataclass
class Schedule:
    ease: float
    interval_days: float
    reps: int
    lapses: int


def next_schedule(cur: Schedule, quality: int) -> Schedule:
    """SM-2 simplificado com 3 respostas (0 errou, 1 difícil, 2 acertou)."""
    if quality <= 0:
        return Schedule(max(MIN_EASE, cur.ease - 0.2), 1.0, 0, cur.lapses + 1)
    if quality == 1:
        interval = max(1.0, cur.interval_days * 1.2) if cur.reps else 1.0
        return Schedule(max(MIN_EASE, cur.ease - 0.15), interval, cur.reps + 1, cur.lapses)
    if cur.reps == 0:
        interval = 1.0
    elif cur.reps == 1:
        interval = 3.0
    else:
        interval = cur.interval_days * cur.ease
    return Schedule(cur.ease + 0.05, interval, cur.reps + 1, cur.lapses)


def quality_from_score(score: float) -> int:
    return 2 if score >= 80 else 1 if score >= 50 else 0


def kind_of(label: str) -> str:
    return "sound" if SOUND_RE.match(label) else "concept"


# ---------------------------------------------------------------------------
# Itens (usados dentro de uma sessão do banco — chamados por db.py)
# ---------------------------------------------------------------------------
def ensure_item(s: Session, domain: str, kind: str, label: str, due_in_days: float = 0.0) -> ReviewItem:
    norm = normalize(label)
    item = s.scalar(select(ReviewItem).where(ReviewItem.domain == domain, ReviewItem.norm == norm))
    if item is None:
        item = ReviewItem(domain=domain, kind=kind, label=label[:500], norm=norm,
                          due_at=utcnow() + timedelta(days=due_in_days))
        s.add(item)
        s.flush()
    return item


def grade_item(s: Session, item: ReviewItem, quality: int, now: Optional[datetime] = None) -> None:
    now = now or utcnow()
    nxt = next_schedule(Schedule(item.ease, item.interval_days, item.reps, item.lapses), quality)
    item.ease, item.interval_days, item.reps, item.lapses = nxt.ease, nxt.interval_days, nxt.reps, nxt.lapses
    item.due_at = now + timedelta(days=nxt.interval_days)
    item.last_reviewed = now
    s.add(ReviewLog(item_id=item.id, domain=item.domain, quality=quality, reviewed_at=now))


def on_mastery_update(s: Session, domain: str, concept: str, norm: str, new_score: float) -> None:
    """Gancho do mapa de domínio: guarda histórico e agenda conceitos fracos."""
    s.add(MasteryHistory(domain=domain, norm=norm, concept=concept[:200], score=new_score))
    if new_score < WEAK_SCORE:
        ensure_item(s, domain, kind_of(concept), concept, due_in_days=1.0)


def on_new_mistake(s: Session, domain: str, text: str) -> None:
    ensure_item(s, domain, "mistake", text, due_in_days=1.0)


def grade_by_label(s: Session, domain: str, label: str, quality: int) -> bool:
    item = s.scalar(select(ReviewItem).where(ReviewItem.domain == domain, ReviewItem.norm == normalize(label)))
    if item is None:
        return False
    grade_item(s, item, quality)
    return True


def sync_existing(s: Session, domain: str) -> None:
    """Cria itens para erros/conceitos anteriores à revisão espaçada (vencem já)."""
    # Histórico começa com o estado atual do mapa (dados anteriores à revisão espaçada)
    if s.scalar(select(func.count()).select_from(MasteryHistory).where(MasteryHistory.domain == domain)) == 0:
        for c in s.scalars(select(ConceptMastery).where(ConceptMastery.domain == domain)):
            s.add(MasteryHistory(domain=domain, norm=c.norm, concept=c.concept, score=c.score, at=c.updated_at))

    known = set(s.scalars(select(ReviewItem.norm).where(ReviewItem.domain == domain)))
    for m in s.scalars(select(Mistake).where(Mistake.domain == domain)):
        if normalize(m.text) not in known:
            ensure_item(s, domain, "mistake", m.text)
    for c in s.scalars(select(ConceptMastery).where(ConceptMastery.domain == domain,
                                                    ConceptMastery.score < WEAK_SCORE)):
        if normalize(c.concept) not in known:
            ensure_item(s, domain, kind_of(c.concept), c.concept)


# ---------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------
def _item_dict(i: ReviewItem) -> dict:
    sound = SOUND_RE.match(i.label)
    return {
        "id": i.id, "kind": i.kind, "label": i.label, "sound": sound.group(1) if sound else None,
        "due_at": i.due_at.isoformat(), "reps": i.reps, "lapses": i.lapses,
        "interval_days": round(i.interval_days, 1),
    }


def _streak(days: set) -> int:
    """Dias seguidos com pelo menos uma revisão, terminando hoje (ou ontem)."""
    today = datetime.now(timezone.utc).date()
    day = today if today in days else today - timedelta(days=1)
    n = 0
    while day in days:
        n += 1
        day -= timedelta(days=1)
    return n


def today(s: Session, domain: str, limit: int = 20) -> dict:
    sync_existing(s, domain)
    now = utcnow()
    end_of_day = now.replace(hour=23, minute=59, second=59)
    due = list(s.scalars(
        select(ReviewItem).where(ReviewItem.domain == domain, ReviewItem.due_at <= end_of_day)
        .order_by(ReviewItem.due_at).limit(limit)
    ))
    total_due = s.scalar(select(func.count()).select_from(ReviewItem).where(
        ReviewItem.domain == domain, ReviewItem.due_at <= end_of_day)) or 0
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    done_today = s.scalar(select(func.count()).select_from(ReviewLog).where(
        ReviewLog.domain == domain, ReviewLog.reviewed_at >= start_of_day)) or 0
    next_due = s.scalar(select(func.min(ReviewItem.due_at)).where(
        ReviewItem.domain == domain, ReviewItem.due_at > end_of_day))
    days = {d.date() for d in s.scalars(select(ReviewLog.reviewed_at).where(ReviewLog.domain == domain))}
    return {
        "due": [_item_dict(i) for i in due],
        "total_due": total_due,
        "done_today": done_today,
        "streak": _streak(days),
        "next_due": next_due.isoformat() if next_due else None,
        "total_items": s.scalar(select(func.count()).select_from(ReviewItem).where(ReviewItem.domain == domain)) or 0,
    }


def progress(s: Session, domain: str, days: int = 30) -> dict:
    """Série diária: domínio médio (último valor de cada conceito até o dia) e revisões feitas."""
    since = utcnow() - timedelta(days=days)
    history = list(s.scalars(select(MasteryHistory).where(MasteryHistory.domain == domain)
                             .order_by(MasteryHistory.at)))
    logs = list(s.scalars(select(ReviewLog).where(ReviewLog.domain == domain, ReviewLog.reviewed_at >= since)))

    today_d = datetime.now(timezone.utc).date()
    day_list = [today_d - timedelta(days=k) for k in range(days - 1, -1, -1)]

    latest: dict[str, float] = {}
    idx = 0
    series = []
    for day in day_list:
        while idx < len(history) and history[idx].at.date() <= day:
            latest[history[idx].norm] = history[idx].score
            idx += 1
        avg = round(sum(latest.values()) / len(latest), 1) if latest else None
        series.append({"date": day.isoformat(), "avg_mastery": avg, "concepts": len(latest)})

    per_day: dict = defaultdict(lambda: [0, 0])  # [total, acertos]
    for lg in logs:
        d = lg.reviewed_at.date()
        per_day[d][0] += 1
        per_day[d][1] += lg.quality == 2
    for point in series:
        total, good = per_day.get(datetime.fromisoformat(point["date"]).date(), (0, 0))
        point["reviews"], point["correct"] = total, good

    weakest = list(s.scalars(select(ConceptMastery).where(ConceptMastery.domain == domain)
                             .order_by(ConceptMastery.score).limit(5)))
    return {
        "series": series,
        "weakest": [{"concept": c.concept, "score": round(c.score)} for c in weakest],
        "total_reviews": sum(p["reviews"] for p in series),
    }

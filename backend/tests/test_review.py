from datetime import timedelta

import db
import review
from review import Schedule, next_schedule


def test_schedule_grows_on_success_and_resets_on_failure():
    s = Schedule(2.5, 0, 0, 0)
    s = next_schedule(s, 2); assert s.interval_days == 1
    s = next_schedule(s, 2); assert s.interval_days == 3
    s = next_schedule(s, 2); assert s.interval_days > 7          # 3 × ease
    s = next_schedule(s, 0)
    assert s.interval_days == 1 and s.reps == 0 and s.lapses == 1 and s.ease < 2.6
    assert next_schedule(Schedule(1.3, 5, 3, 0), 0).ease == review.MIN_EASE


def test_quality_from_score():
    assert [review.quality_from_score(x) for x in (90, 80, 60, 10)] == [2, 2, 1, 0]


def test_new_mistake_creates_review_item_due_tomorrow():
    db.record_mistakes("en", ["usa 'go' no passado"])
    t = db.review_today("en")
    assert t["total_items"] == 1 and t["total_due"] == 0     # vence amanhã
    assert t["next_due"] is not None


def test_weak_concepts_and_sounds_are_scheduled_strong_ones_are_not():
    db.record_mastery("en", [("pronúncia /θ/", 0), ("past simple", 95)])
    with db.session_scope() as s:
        items = {i.label: i for i in s.scalars(review.select(review.ReviewItem))}
    assert set(items) == {"pronúncia /θ/"} and items["pronúncia /θ/"].kind == "sound"


def test_existing_data_is_synced_and_due_now():
    with db.session_scope() as s:
        s.add(review.Mistake(domain="es", text="exquisito ≠ esquisito", norm="exquisito ≠ esquisito",
                             first_seen=review.utcnow(), last_seen=review.utcnow()))
    t = db.review_today("es")
    assert t["total_due"] == 1 and t["due"][0]["kind"] == "mistake"


def test_grading_moves_due_date_and_counts_streak():
    db.record_mastery("math_ml", [("regra da cadeia", 30)])
    with db.session_scope() as s:
        item = s.scalars(review.select(review.ReviewItem)).one()
        item.due_at = review.utcnow() - timedelta(hours=1)
        item_id = item.id
    assert db.review_today("math_ml")["total_due"] == 1

    assert db.grade_review(item_id, 2)
    t = db.review_today("math_ml")
    assert t["total_due"] == 0 and t["done_today"] == 1 and t["streak"] == 1


def test_grade_by_label_and_progress_series():
    db.record_mastery("en", [("pronúncia /ð/", 20)])
    assert db.grade_review_by_label("en", "Pronúncia /ð/", 0)
    db.record_mastery("en", [("pronúncia /ð/", 100)])
    p = db.review_progress("en", days=7)
    assert len(p["series"]) == 7
    last = p["series"][-1]
    assert last["reviews"] == 1 and last["correct"] == 0
    assert last["avg_mastery"] == 52.0                          # 0.6×20 + 0.4×100
    assert p["weakest"][0]["concept"] == "pronúncia /ð/"

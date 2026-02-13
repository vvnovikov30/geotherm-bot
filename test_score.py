"""
Self-check для проверки скоринга статей.
Проверяет, что score_item работает корректно и reasons правильно формируются.
"""
from config import SCORE_THRESHOLD
from editorial import is_relevant, score_item


def test_score_item():
    """Тестирует функцию score_item на различных примерах."""
    print("=" * 70)
    print("SELF-CHECK: Тестирование score_item()")
    print("=" * 70)
    
    test_cases = [
        {
            "name": "RCT (Randomized Controlled Trial)",
            "item": {
                "title": "Randomized Controlled Trial of Mineral Water for Constipation",
                "summary": "This randomized controlled trial evaluates the effects of mineral water on constipation in adults.",
                "pub_types": ["Randomized Controlled Trial"]
            },
            "expected_min_score": 8,  # +8 за RCT
            "should_have_reason": "high-priority"
        },
        {
            "name": "Clinical Trial",
            "item": {
                "title": "Clinical Trial of Thermal Mineral Water Therapy",
                "summary": "A clinical trial investigating the benefits of thermal mineral water therapy.",
                "pub_types": ["Clinical Trial"]
            },
            "expected_min_score": 8,  # +8 за Clinical Trial
            "should_have_reason": "high-priority"
        },
        {
            "name": "Systematic Review",
            "item": {
                "title": "Systematic Review of Balneotherapy Effects",
                "summary": "A systematic review of balneotherapy and spa therapy effects on health outcomes.",
                "pub_types": ["Systematic Review"]
            },
            "expected_min_score": 8,  # +8 за Systematic Review
            "should_have_reason": "high-priority"
        },
        {
            "name": "Review (обычный)",
            "item": {
                "title": "Review of Mineral Water Benefits",
                "summary": "A review article about mineral water and its health benefits.",
                "pub_types": ["Review"]
            },
            "expected_min_score": 5,  # +5 за Review
            "should_have_reason": "review"
        },
        {
            "name": "LOW_SCORE: Letter to Editor",
            "item": {
                "title": "Letter to the Editor: Mineral Water Study",
                "summary": "A letter commenting on mineral water research.",
                "pub_types": ["Letter"]
            },
            "expected_max_score": -6,  # -6 за letter в title, -8 за Letter в pub_types
            "should_have_reason": "letter"
        },
        {
            "name": "LOW_SCORE: Preprint",
            "item": {
                "title": "Mineral Water and Health Outcomes",
                "summary": "A study about mineral water effects.",
                "pub_types": ["Preprint"]
            },
            "expected_max_score": -3,  # -3 за Preprint
            "should_have_reason": "preprint"
        },
        {
            "name": "LOW_SCORE: Erratum",
            "item": {
                "title": "Corrigendum: Mineral Water Study",
                "summary": "Correction to previous publication.",
                "pub_types": ["Erratum"]
            },
            "expected_max_score": -6,  # -6 за corrigendum в title, -8 за Erratum в pub_types
            "should_have_reason": "erratum"
        },
        {
            "name": "RCT + Randomized в тексте",
            "item": {
                "title": "Randomized Controlled Trial of Mineral Water",
                "summary": "This randomized study evaluates mineral water effects.",
                "pub_types": ["Randomized Controlled Trial"]
            },
            "expected_min_score": 8,  # +8 за RCT, +5 за randomized в тексте = 13
            "should_have_reason": "high-priority"
        },
    ]
    
    passed = 0
    failed = 0
    
    for i, test in enumerate(test_cases, 1):
        print(f"\n[{i}] Тест: {test['name']}")
        print("-" * 70)
        
        # Проверяем релевантность (должна быть True для тестов)
        is_rel = is_relevant(test["item"])
        print(f"  Релевантность: {'OK' if is_rel else 'FAIL'} ({is_rel})")
        
        # Вызываем score_item
        score, reasons = score_item(test["item"])
        
        print(f"  Score: {score}")
        print(f"  Reasons: {', '.join(reasons) if reasons else 'none'}")
        print(f"  Threshold: {SCORE_THRESHOLD}")
        print(f"  Status: {'PASS' if score >= SCORE_THRESHOLD else 'FAIL (LOW_SCORE)'}")
        
        # Проверяем формат возвращаемого значения
        assert isinstance(score, int), f"❌ Score должен быть int, получен {type(score)}"
        assert isinstance(reasons, list), f"❌ Reasons должен быть list, получен {type(reasons)}"
        assert all(isinstance(r, str) for r in reasons), "❌ Все reasons должны быть str"
        
        # Проверяем ожидаемый score
        if "expected_min_score" in test:
            if score >= test["expected_min_score"]:
                print(f"  [OK] Score >= {test['expected_min_score']}")
                passed += 1
            else:
                print(f"  [FAIL] Score {score} < {test['expected_min_score']}")
                failed += 1
        elif "expected_max_score" in test:
            if score <= test["expected_max_score"]:
                print(f"  [OK] Score <= {test['expected_max_score']}")
                passed += 1
            else:
                print(f"  [FAIL] Score {score} > {test['expected_max_score']}")
                failed += 1
        
        # Проверяем наличие причины
        if test["should_have_reason"]:
            has_reason = any(test["should_have_reason"] in r.lower() for r in reasons)
            if has_reason:
                print(f"  [OK] Причина '{test['should_have_reason']}' найдена в reasons")
            else:
                print(f"  [FAIL] Причина '{test['should_have_reason']}' НЕ найдена в reasons")
                failed += 1
                if "expected_min_score" in test or "expected_max_score" in test:
                    passed -= 1  # Откатываем счетчик, если был увеличен выше
        
        # Проверяем, что reasons не пустые для LOW_SCORE
        if score < SCORE_THRESHOLD:
            if reasons:
                print("  [OK] Reasons присутствуют для LOW_SCORE")
            else:
                print("  [FAIL] Reasons отсутствуют для LOW_SCORE")
                failed += 1
                if "expected_min_score" in test or "expected_max_score" in test:
                    passed -= 1
    
    print("\n" + "=" * 70)
    print(f"РЕЗУЛЬТАТЫ: {passed} тестов пройдено, {failed} тестов провалено")
    print("=" * 70)
    
    if failed == 0:
        print("[SUCCESS] Все тесты пройдены успешно!")
        return True
    else:
        print("[FAILED] Некоторые тесты провалены. Проверьте логику скоринга.")
        return False


if __name__ == "__main__":
    success = test_score_item()
    exit(0 if success else 1)

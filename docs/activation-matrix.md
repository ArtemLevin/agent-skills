# Матрица активации навыков

| Событие или риск | Обязательные навыки | Условные навыки |
|---|---|---|
| Документационная правка | task-triage, repository-context, delivery-summary | intent-documentation |
| Локальный bugfix | requirements-contract, implementation, verification-router, adversarial-review | risk-based-testing |
| Новая бизнес-логика | change-planner, risk-based-testing, adversarial-review | architecture-guard |
| Рефакторинг без смены поведения | repository-context, change-planner, verification-router | engineering-balance |
| Публичный API | requirements-contract, adversarial-review | architecture-guard, security-review |
| Аутентификация/авторизация | security-review, risk-based-testing, adversarial-review | database-review |
| SQL, ORM, миграции, транзакции | database-review, risk-based-testing | concurrency-review |
| Async, workers, очереди, retry | concurrency-review, risk-based-testing | database-review, security-review |
| Docker, CI/CD, production config | architecture-guard, verification-router | security-review |
| Новая зависимость или абстракция | engineering-balance, architecture-guard | security-review |
| Неочевидное ограничение или компромисс | intent-documentation | architecture-guard |

## Правило маршрутизации

Навык активируется, если выполняется хотя бы одно из условий:

1. он указан в `required_skills` результатом triage;
2. новый факт повысил риск до порога навыка;
3. проверка или ревью выявили проблему его класса.

Навык не активируется только потому, что он доступен.

## Fast mode

Обычно активны 3–4 навыка:

- `task-triage`;
- `repository-context`;
- `implementation`;
- `delivery-summary`.

## Standard mode

Обычно активны 6–9 навыков:

- базовые четыре;
- `requirements-contract`;
- `change-planner`;
- `verification-router`;
- `risk-based-testing`;
- `adversarial-review`.

## Deep mode

К standard-набору добавляются только релевантные specialist reviews. Одновременная активация всех специалистов считается ошибкой маршрутизации.

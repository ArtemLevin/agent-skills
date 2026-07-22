# Пошаговое внедрение

## Этап 1. Минимальный контур

Подключите:

- `AGENT.md`;
- `task-triage`;
- `repository-context`;
- `requirements-contract`;
- `implementation`;
- `verification-router`;
- `adversarial-review`;
- `delivery-summary`.

На этом этапе измеряйте:

- среднее число прочитанных файлов;
- размер diff;
- число итераций;
- долю задач, прошедших тесты с первого раза;
- долю несвязанных изменений.

## Этап 2. Калибровка тестирования

Подключите `risk-based-testing`. Возьмите 20–30 реальных задач и сравните:

- какие тесты агент добавлял до внедрения;
- какие из них реально падали до исправления;
- какие ловили последующие регрессии;
- сколько времени занимал полный test suite.

Скорректируйте пороги риска под проект.

## Этап 3. Баланс архитектуры

Добавьте `engineering-balance` и `architecture-guard`. Активируйте их только для изменений границ модулей, зависимостей, публичных контрактов и новых абстракций.

## Этап 4. Specialist reviews

Добавляйте `security-review`, `concurrency-review` и `database-review` по статистике дефектов. Не подключайте их глобально.

## Этап 5. Интеграция с CI

CI должен проверять результат агента обычными проектными инструментами:

- formatter/linter;
- type checker;
- targeted tests;
- интеграционные тесты по затронутому компоненту;
- security scanner при изменениях зависимостей или security-sensitive кода.

Сам агент не заменяет CI и не должен интерпретировать отсутствие запуска как успех.

## Этап 6. Метрики

Рекомендуемые метрики:

```yaml
quality:
  acceptance_pass_rate: percent
  first_pass_test_success: percent
  review_escape_rate: percent
  regression_rate: percent

efficiency:
  tokens_per_completed_task: number
  files_read_per_changed_file: ratio
  implementation_iterations: number
  skills_loaded_per_task: number
  repeated_context_ratio: percent

maintainability:
  average_diff_size: lines
  unrelated_files_changed: number
  speculative_abstractions: number
  duplicated_tests: number
```

Оптимизируйте не минимальное число токенов, а стоимость подтверждённо корректной задачи.

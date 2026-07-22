# AgentKit: мини-гайд

## Что делает модуль

AgentKit связывает инженерные навыки, Graphify и CLI coding-агента в один повторяемый процесс. Пользователь передаёт задачу, а runner:

1. проверяет Git;
2. определяет риск;
3. обновляет граф проекта;
4. выбирает только нужные навыки;
5. запускает агента;
6. выполняет проверки;
7. запускает критическое ревью;
8. допускает ограниченное исправление;
9. формирует итоговый completion report.

## Установка

```powershell
uv tool install "git+https://github.com/ArtemLevin/agent-skills.git"
```

Проверка:

```powershell
agentkit --help
```

## Подключение к проекту

```powershell
cd C:\Users\Артем\IdeaProjects\tutor-assistant
agentkit init --platform agents
```

После установки обязательно зафиксируйте служебные файлы:

```powershell
git add .agent .agents Makefile .gitignore
git commit -m "chore: install AgentKit"
```

Иначе `agentkit run` остановится из-за грязного рабочего дерева.

## Диагностика

```powershell
agentkit doctor
```

Проверьте четыре признака:

```text
git_repository: true
config_ok: true
graphify.installed: true
agent.installed: true
```

## Первая безопасная задача

Сначала выполните dry run:

```powershell
agentkit run `
  --dry-run `
  --task "Исправить опечатку в README"
```

Runner создаст `.agent/state/runs/<id>/task-packet.json`, но не запустит нейросеть.

Затем выполните полный цикл:

```powershell
make ai TASK="Исправить опечатку в README"
```

## Обычная задача

```powershell
make ai TASK="Добавить ограниченный retry при временной ошибке записи JSON"
```

Ожидаемый маршрут:

```text
standard
→ Graphify query
→ repository context
→ requirements contract
→ implementation
→ targeted tests
→ adversarial review
→ completion gate
```

## Опасная задача

```powershell
agentkit run `
  --task "Добавить миграцию PostgreSQL для lessons"
```

AgentKit выберет `deep` и остановится. После изучения `task-packet.json` запустите:

```powershell
agentkit run `
  --approve-deep `
  --task "Добавить миграцию PostgreSQL для lessons"
```

Флаг разрешает выполнение кода, но не разрешает merge, production deploy или необратимые операции.

## Настройка тестов

Откройте `.agent/agentkit.toml`:

```toml
[verification]
commands = [
  ["uv", "run", "pytest", "tests/recording", "-q"],
  ["uv", "run", "ruff", "check", "src", "tests"]
]
```

Команды задаются массивами, а не одной строкой. Так runner избегает небезопасной передачи через shell.

## Где смотреть результат

```powershell
make ai-status
```

Или откройте:

```text
.agent/state/runs/<run-id>/completion.json
```

Готовая задача имеет:

```json
{
  "status": "ready_for_review",
  "checks_passed": true,
  "review_passed": true,
  "blocking_findings": 0,
  "scope_passed": true,
  "ready": true
}
```

## Что остаётся ручным

После `ready_for_review` человек должен:

1. просмотреть diff;
2. убедиться, что требования поняты правильно;
3. создать commit;
4. открыть PR;
5. принять решение о merge и deployment.

Это не недостаток, а предохранитель первого релиза.

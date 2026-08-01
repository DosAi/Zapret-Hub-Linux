# Установка Zapret Hub Linux

> **Статус совместимости:** разработка и тестирование выполнялись только на
> Kali Linux. Другие Debian-подобные системы пока считаются экспериментальными.
>
> **Windows не поддерживается.** В этом форке нет Windows-сборок и
> инструкций по их использованию.

Основное описание форка, благодарности и ссылки на исходные проекты находятся
в [README.md](README.md).

## Автоматическая установка

```bash
./scripts/install_linux.sh
```

Установщик:

- устанавливает Python, Node.js/npm, PolicyKit, nftables и другие зависимости;
- устанавливает встроенный Zapret 2 в `/opt/zapret2`;
- регистрирует `zapret2.service`, не перезапуская текущие сетевые службы;
- добавляет ограниченное PolicyKit-правило для управления только сервисами
  Zapret;
- создаёт `.venv`, собирает Web UI и добавляет ярлык приложения;
- запускает Zapret Hub от имени текущего пользователя.

Telegram Desktop по умолчанию **не устанавливается**. Опциональная установка:

```bash
./scripts/install_linux.sh --with-telegram
```

Дополнительные режимы:

```bash
./scripts/install_linux.sh --no-launch
./scripts/install_linux.sh --dry-run
```

Повторный запуск обновляет управляемую копию приложения. Сторонняя установка
`/opt/zapret2` и её конфигурация сохраняются.

## Запуск и диагностика

```bash
~/.local/bin/zapret-hub
```

```bash
.venv/bin/zapret-hub-linux diagnose
.venv/bin/zapret-hub-linux start --dry-run
```

## Поддержка

Telegram: [@dosai_main](https://t.me/dosai_main)

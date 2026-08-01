<div align="center">

# Zapret Hub Linux

Графическая панель для Zapret, Zapret2 и TG WS Proxy на Kali Linux.

**Автор Linux-форка: [DosAi](https://github.com/DosAi)**<br>
[Репозиторий](https://github.com/DosAi/Zapret-Hub-Linux) · [Telegram: @dosai_main](https://t.me/dosai_main)

</div>

> [!IMPORTANT]
> Это Linux-only форк, разрабатываемый и тестируемый **только на Kali Linux**.
> **Windows не поддерживается:** мы не выпускаем `.exe`, Windows-инсталляторы
> или Windows-инструкции. Другие Linux-дистрибутивы пока не проверены.

## Что это

Zapret Hub Linux — отдельный экспериментальный форк с Linux-бэкендами,
`systemd`, `nftables` и PolicyKit. Он даёт единое окно для выбора стратегии
обхода и управления дополнительными компонентами.

Портирование, отладка, подготовка установщика и тестов выполнены DosAi
при помощи **ChatGPT от OpenAI**.

## Возможности

- Zapret2 через `nfqws2`, `nftables` и `zapret2.service`;
- автоматическая установка классического Zapret для Linux;
- локальный TG WS Proxy на `127.0.0.1:1443`;
- общая кнопка питания и отдельные переключатели компонентов;
- свободное листание стратегий без их автоматического запуска;
- ограниченное PolicyKit-правило для управления Zapret-сервисами;
- автозапуск и ярлык в меню приложений Kali.

Встроенный legacy VPN из upstream-версии в Linux-интерфейсе скрыт и не
поддерживается. В будущем его место планируется использовать для
[Happ](https://github.com/Happ-proxy/happ-desktop).

## Установка на Kali Linux

Клонируйте репозиторий и запустите установщик:

```bash
git clone https://github.com/DosAi/Zapret-Hub-Linux.git
cd Zapret-Hub-Linux
./scripts/install_linux.sh
```

Установщик подготовит зависимости, классический Zapret, Zapret2, TG WS Proxy,
Python-окружение, Web UI, PolicyKit-правило и ярлык. После установки приложение доступно в меню
Kali или по команде:

```bash
~/.local/bin/zapret-hub
```

**Telegram Desktop не устанавливается автоматически.** Если нужно явно
установить его вместе с Zapret Hub:

```bash
./scripts/install_linux.sh --with-telegram
```

Предварительный просмотр без изменений системы:

```bash
./scripts/install_linux.sh --dry-run --no-launch
```

Установщик не запускает, не останавливает и не перезапускает сетевые службы,
а также не меняет их автозапуск. Текущий VPN остаётся нетронутым. Сторонние
установки Zapret и `/opt/zapret2` не перезаписываются.

Подробности: [README_LINUX.md](README_LINUX.md).

## TG WS Proxy

Прокси работает локально и не открывает порт во внешную сеть. Его можно
включать отдельно на главной странице либо запускать вместе с обходом.
Для подключения Telegram Desktop используйте кнопку **«Подключить Telegram»** в
карточке компонента.

Быстрая проверка порта:

```bash
ss -ltn | grep ':1443'
```

## Ограничения

- реальное тестирование проводилось только на Kali Linux;
- форк не является VPN и не отправляет трафик на серверы DosAi;
- результат обхода зависит от провайдера, региона и выбранной стратегии;
- поддержка Happ пока находится в планах.

## Диагностика и тесты

```bash
.venv/bin/zapret-hub-linux diagnose
.venv/bin/zapret-hub-linux start --dry-run
.venv/bin/pytest -q
```

Журнал TG WS Proxy: `logs/tg_ws_proxy.log`.

## Исходные проекты и благодарности

Этот форк не претендует на авторство встроенных open-source компонентов.

- [Zapret Hub — upstream, от которого был создан Linux-форк](https://github.com/goshkow/Zapret-Hub)
- [zapret](https://github.com/bol-van/zapret) и [zapret2](https://github.com/bol-van/zapret2) — **bol-van**
- [zapret-discord-youtube-linux](https://github.com/Sergeydigl3/zapret-discord-youtube-linux) — **Sergeydigl3**
- [tg-ws-proxy](https://github.com/Flowseal/tg-ws-proxy) — **Flowseal** и участники
- [zapret-discord-youtube](https://github.com/Flowseal/zapret-discord-youtube) — **Flowseal** и участники

Ссылка на upstream сохранена только для атрибуции и соблюдения лицензии; этот
Linux-форк не является официальным релизом upstream-проекта.

## Связь

Ошибки, идеи и результаты тесирования: [@dosai_main](https://t.me/dosai_main).

## Лицензия

Изменения Linux-форка распространяются на условиях [MIT License](LICENSE).
Встроенные проекты сохраняют свои лицензии и авторские уведомления.

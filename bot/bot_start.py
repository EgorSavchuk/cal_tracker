import asyncio
import os
import random
from string import ascii_letters

from aiogram import Bot
from aiogram.types import BotCommand
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from config import DEBUG, BASE_WEBHOOK_URL, WEBAPP_HOST, WEBAPP_PORT, ADMIN_USER_ID
from handlers import router as main_router
from loader import bot as main_bot, dp as main_dp, log
from services.database import get_db, close_db
from services.middleware import AccessControlMiddleware, AlbumMiddleware

# Register handlers router
main_dp.include_router(main_router)

# Register middlewares
main_dp.message.middleware(AccessControlMiddleware())
main_dp.callback_query.middleware(AccessControlMiddleware())
main_dp.message.middleware(AlbumMiddleware())

BOT_COMMANDS = [
    BotCommand(command="day", description="Итоги дня"),
    BotCommand(command="close", description="Закрыть день"),
    BotCommand(command="undo", description="Отменить последнюю запись"),
    BotCommand(command="products", description="Известные продукты"),
    BotCommand(command="dashboard", description="Дашборд"),
    BotCommand(command="help", description="Помощь"),
]


async def on_startup(bot: Bot) -> None:
    await get_db()
    await bot.set_my_commands(BOT_COMMANDS)
    log.info("Database initialized, commands set")


async def on_shutdown(bot: Bot) -> None:
    await close_db()
    log.info("Database closed")


main_dp.startup.register(on_startup)
main_dp.shutdown.register(on_shutdown)


def start_polling() -> None:
    """Start in long polling mode (DEBUG=True). Also runs API server."""
    from webapp.server import create_webapp

    async def _run():
        await main_bot.delete_webhook(drop_pending_updates=False)
        log.info("Bot started in polling mode")

        # Start API server in background
        webapp = create_webapp()
        runner = web.AppRunner(webapp)
        await runner.setup()
        site = web.TCPSite(runner, WEBAPP_HOST, WEBAPP_PORT)
        await site.start()
        log.info(f"API server started on {WEBAPP_HOST}:{WEBAPP_PORT}")

        try:
            await main_dp.start_polling(main_bot)
        finally:
            await runner.cleanup()

    asyncio.run(_run())


def start_webhook() -> None:
    """Start in webhook mode (DEBUG=False)."""
    from webapp.server import routes as api_routes, auth_middleware

    path = f"/webhook/{''.join(random.choice(ascii_letters) for _ in range(16))}"
    secret = "".join(random.choice(ascii_letters) for _ in range(32))

    async def _set_webhook(bot: Bot):
        await bot.set_webhook(f"{BASE_WEBHOOK_URL}{path}", secret_token=secret)
        log.info("Webhook set")

    async def _delete_webhook(bot: Bot):
        await bot.delete_webhook()
        log.info("Webhook deleted")

    main_dp.startup.register(_set_webhook)
    main_dp.shutdown.register(_delete_webhook)

    app = web.Application(middlewares=[auth_middleware])
    webhook_handler = SimpleRequestHandler(
        dispatcher=main_dp, bot=main_bot, secret_token=secret
    )
    webhook_handler.register(app, path=path)
    app.add_routes(api_routes)
    setup_application(app, main_dp, bot=main_bot)

    web.run_app(app, host=WEBAPP_HOST, port=WEBAPP_PORT)


if __name__ == "__main__":
    if DEBUG:
        start_polling()
    else:
        start_webhook()

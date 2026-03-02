import asyncio
import os
import random
from string import ascii_letters

from aiogram import Bot
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from loguru import logger

from config import DEBUG
from handlers import dp as main_dp
from loader import bot as main_bot


class BotMode:
    def __init__(self, bot: Bot, dp):
        self.bot = bot
        self.dp = dp
        self.dp.startup.register(self._on_startup)
        self.dp.shutdown.register(self._on_shutdown)

    async def _on_startup(self):
        raise NotImplementedError

    async def _on_shutdown(self):
        raise NotImplementedError

    def start(self):
        raise NotImplementedError


class LongPollingMode(BotMode):
    HOST = "127.0.0.1"
    PORT = 8080

    async def _on_startup(self):
        await self.bot.delete_webhook(drop_pending_updates=False)
        mes = "Bot started in long polling mode!"
        print(mes)
        logger.info(mes)

    async def _on_shutdown(self):
        mes = "Bot stopped!"
        print(mes)
        logger.info(mes)

    def start(self):
        asyncio.run(self.dp.start_polling(self.bot))


class WebHookMode(BotMode):
    HOST = "127.0.0.1"
    PORT = 8080
    PATH = f"/webhook/{''.join(random.choice(ascii_letters) for _ in range(16))}"
    SECRET = "".join(random.choice(ascii_letters) for _ in range(32))
    BASE_URL = os.getenv("BASE_WEBHOOK_URL")

    async def _on_startup(self):
        await self.bot.set_webhook(
            f"{self.BASE_URL}{self.PATH}", secret_token=self.SECRET
        )
        logger.info("Bot started with webhook!")

    async def _on_shutdown(self):
        await self.bot.delete_webhook()
        logger.info("Webhook deleted and bot stopped!")

    def start(self):
        app = web.Application()
        webhook_handler = SimpleRequestHandler(
            dispatcher=self.dp, bot=self.bot, secret_token=self.SECRET
        )
        webhook_handler.register(app, path=self.PATH)
        setup_application(app, self.dp, bot=self.bot)

        web.run_app(app, host=self.HOST, port=self.PORT)


if __name__ == "__main__":
    if DEBUG:
        mode = LongPollingMode(main_bot, main_dp)
    else:
        mode = WebHookMode(main_bot, main_dp)
    mode.start()

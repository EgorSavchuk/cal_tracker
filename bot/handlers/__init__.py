from aiogram import Router

from . import commands, callbacks, intake, error

router = Router()
router.include_router(error.router)
router.include_router(commands.router)
router.include_router(callbacks.router)
router.include_router(intake.router)  # catch-all must be last
